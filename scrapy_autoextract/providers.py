import inspect
from asyncio import CancelledError
from typing import Callable, Set, ClassVar, Type, List, Any

import aiohttp


from autoextract.aio import request_raw, create_session
from autoextract.aio.errors import RequestError, \
    ACCOUNT_DISABLED_ERROR_TYPE
from autoextract.aio.retry import RetryFactory
from autoextract.request import Request as AutoExtractRequest
from autoextract.stats import AggStats
from autoextract_poet.page_inputs import (
    AutoExtractProductData, AutoExtractData, AutoExtractHtml,
)
from scrapy import Request as ScrapyRequest
from scrapy.crawler import Crawler
from scrapy.statscollectors import StatsCollector
from .errors import QueryError, summarize_exception
from .task_manager import TaskManager
from scrapy_poet.page_input_providers import PageObjectInputProvider

_TASK_MANAGER = "_autoextract_task_manager"


def get_autoextract_task_manager(crawler: Crawler) -> TaskManager:
    """
    Return the configured :class:`scrapy_autoextract.TaskManager` that controls
    AutoExtract ongoing requests.
    Handy to cancel all of them to stop fast when cancelling a spider
    """
    if not hasattr(crawler, _TASK_MANAGER):
        setattr(crawler, _TASK_MANAGER, TaskManager())
    return getattr(crawler, _TASK_MANAGER)


def _stop_if_account_disabled(exception: Exception, crawler: Crawler):
    if not isinstance(exception, RequestError):
        return

    logger = crawler.spider.logger
    if exception.error_data().get("type") == ACCOUNT_DISABLED_ERROR_TYPE:
        logger.info(
            "'Account disabled' request error received. Shutting down the spider"
        )
        crawler.engine.close_spider(crawler.spider, "account_disabled")


class AutoExtractProvider(PageObjectInputProvider):
    """Provider for AutoExtract data"""
    page_type_class: ClassVar[Type]

    # pageType requested when only html is required
    page_type_class_for_html: ClassVar[AutoExtractData] = AutoExtractProductData
    html_query_attribute: ClassVar[str] = "fullHtml"

    @classmethod
    def provided_classes(cls, type_: Callable) -> bool:
        return (inspect.isclass(type_)
                and issubclass(type_, (AutoExtractData, AutoExtractHtml)))

    def __init__(self, crawler: Crawler):
        """Initialize provider storing its dependencies as attributes."""
        self.crawler = crawler
        self.settings = crawler.spider.settings
        self.task_manager = get_autoextract_task_manager(crawler)
        self.aiohttp_session = self.create_aiohttp_session()
        self.common_request_kwargs = dict(
            api_key=self.settings.get("AUTOEXTRACT_USER"),
            endpoint=self.settings.get("AUTOEXTRACT_URL"),
            max_query_error_retries=self.settings.getint(
                "AUTOEXTRACT_MAX_QUERY_ERROR_RETRIES", 3),
            session=self.aiohttp_session
        )

    def create_aiohttp_session(self) -> aiohttp.ClientSession:
        concurrent_connections = self.settings.get("CONCURRENT_REQUESTS", 16)
        return create_session(connection_pool_size=concurrent_connections)

    def create_retry_wrapper(self):
        return RetryFactory().build()

    async def do_request(self, *args, **kwargs):
        return await request_raw(*args, **kwargs)

    def pre_process_item_data(self, data) -> Any:
        """
        Hook for transforming data before any further processing, just after
        receive the content
        """
        return data

    async def __call__(self,
                       to_provide: Set[Callable],
                       request: ScrapyRequest,
                       stats: StatsCollector
                       ) -> List:
        """Make an AutoExtract request and build a Page Input of provided class
        based on API response data.
        """
        is_html_required = AutoExtractHtml in to_provide
        to_provide -= {AutoExtractHtml}
        is_extraction_required = bool(to_provide)
        if is_html_required and not is_extraction_required:
            # At least one request is required to get html
            to_provide = {self.page_type_class_for_html}

        instances = []
        for idx, provided_cls in enumerate(to_provide):
            if not issubclass(provided_cls, AutoExtractData):
                raise RuntimeError(
                    f"Unexpected {provided_cls} requested. Probably a bug in the provider "
                    "or in scrapy-poet itself")
            request_stats = AggStats()
            is_first_request = idx == 0
            page_type = provided_cls.page_type

            def inc_stats(suffix, value=1, both=False):
                stats.inc_value(f"autoextract/total{suffix}", value)
                if both:
                    stats.inc_value(f"autoextract/{page_type}{suffix}", value)

            try:
                # html is requested only a single time to save resources
                should_request_html = is_html_required and is_first_request
                ae_request = self.get_filled_request(
                    request,
                    provided_cls,
                    should_request_html
                )
                awaitable = self.do_request(**{
                    'query': [ae_request],
                    'agg_stats': request_stats,
                    **self.common_request_kwargs,
                })
                response = await self.task_manager.run(awaitable)
                data = response[0]
                data = self.pre_process_item_data(data)
                if "error" in data:
                    raise QueryError(data["query"], data["error"])

            except CancelledError:
                inc_stats("/pages/cancelled", both=True)
                raise
            except Exception as e:
                inc_stats("/pages/error", both=True)
                inc_stats(f"/pages/error{summarize_exception(e)}")
                _stop_if_account_disabled(e, self.crawler)
                raise
            finally:
                inc_stats("/pages/count", both=True)
                inc_stats("/attempts/count", request_stats.n_attempts)
                inc_stats("/attempts/billable", request_stats.n_billable_query_responses)

            if should_request_html:
                instances.append(AutoExtractHtml(url=data[page_type]['url'],
                                                 html=data['html']))
                inc_stats("/pages/html", both=True)

            if is_extraction_required:
                data.pop("html", None)
                instances.append(provided_cls(data=data))

            inc_stats("/pages/success", both=True)

        return instances

    def get_filled_request(self,
                           request: ScrapyRequest,
                           provided_cls: AutoExtractData,
                           should_request_html: bool) -> AutoExtractRequest:
        """Return a filled request for AutoExtract"""
        ae_request = AutoExtractRequest(
            url=request.url,
            pageType=provided_cls.page_type,
        )
        if should_request_html:
            ae_request.extra = {self.html_query_attribute: True}
        return ae_request
