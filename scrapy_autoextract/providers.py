import inspect
import json
import logging
import os
from asyncio import CancelledError
from dataclasses import dataclass
from typing import Callable, Set, ClassVar, List, Any, Hashable, Sequence, Type, TypeVar

import aiohttp
import attr
from scrapy import Request as ScrapyRequest, signals, Request
from scrapy.crawler import Crawler
from scrapy.settings import Settings
from autoextract.aio import request_raw, create_session
from autoextract.aio.errors import RequestError, \
    ACCOUNT_DISABLED_ERROR_TYPE
from autoextract.aio.retry import RetryFactory
from autoextract.request import Request as AutoExtractRequest
from autoextract.stats import AggStats
from autoextract_poet.page_inputs import (
    AutoExtractProductData, AutoExtractData, AutoExtractHtml,
)
from scrapy_poet.page_input_providers import PageObjectInputProvider
from .errors import QueryError, summarize_exception
from .slot_semaphore import SlotsSemaphore
from .task_manager import TaskManager
from .utils import get_domain, get_scrapy_data_path
from .cache import AutoExtractCache, DummyCache

logger = logging.getLogger(__name__)


_TASK_MANAGER = "_autoextract_task_manager"


AEDataType = TypeVar('AEDataType', bound=AutoExtractData, covariant=True)


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

    if exception.error_data().get("type") == ACCOUNT_DISABLED_ERROR_TYPE:
        logger.info(
            "'Account disabled' request error received. Shutting down the spider"
        )
        crawler.engine.close_spider(crawler.spider, "account_disabled")


def get_concurrent_requests_per_domain(settings: Settings):
    """Return the configured AutoExtract concurrent request per domain from settings"""
    limit_name = "AUTOEXTRACT_CONCURRENT_REQUESTS_PER_DOMAIN"
    concurrency = settings.getint(limit_name, -1)
    # If no AutoExtract-specific limit is provided - use the default one
    if concurrency == -1:
        limit_name = "CONCURRENT_REQUESTS_PER_DOMAIN"
        concurrency = settings.getint(limit_name)
    if concurrency < 1:
        raise ValueError(f"Invalid '{limit_name}' "
                         f"value: {concurrency}")
    return concurrency


@attr.define()
class AERequestSpec:
    query: List[AutoExtractRequest]
    should_request_html: bool
    is_extraction_required: bool
    provided_cls: Callable


class AutoExtractProvider(PageObjectInputProvider):
    """Provider for AutoExtract data"""
    # pageType requested when only html is required
    page_type_class_for_html: ClassVar[AutoExtractData] = AutoExtractProductData
    html_query_attribute: ClassVar[str] = "fullHtml"
    name = "autoextract"

    @classmethod
    def provided_classes(cls, type_: Callable) -> bool:
        return (inspect.isclass(type_)
                and issubclass(type_, (AutoExtractData, AutoExtractHtml)))

    def __init__(self, crawler: Crawler):
        """Initialize provider storing its dependencies as attributes."""
        self.crawler = crawler
        self.settings = crawler.spider.settings
        self.stats = crawler.stats
        self.task_manager = get_autoextract_task_manager(crawler)
        self.aiohttp_session = None
        self.crawler.signals.connect(self.on_spider_closed,
                                     signal=signals.spider_closed)
        self.retries_count = self.settings.getint(
                "AUTOEXTRACT_MAX_QUERY_ERROR_RETRIES", 0)

        per_domain_concurrency = get_concurrent_requests_per_domain(self.settings)
        self.per_domain_semaphore = SlotsSemaphore(per_domain_concurrency)

        cache_filename = self.settings.get('AUTOEXTRACT_CACHE_FILENAME')
        if cache_filename:
            cache_filename = os.path.join(get_scrapy_data_path(createdir=True),
                                          cache_filename)
            compressed = self.settings.getbool('AUTOEXTRACT_CACHE_GZIP', True)
            self.cache = AutoExtractCache(cache_filename, compressed=compressed)
        else:
            self.cache = DummyCache()

        logger.info(
            f"AutoExtractProvider started. Retries: {self.retries_count}, "
            f"per domain concurrency: {per_domain_concurrency}, "
            f"cache: {self.cache}"
        )

    # @property to get actual aiohttp_session, instead of predefined None in `__init__`,
    # so we can use the same session instead of creating/killing new sessions for each request
    @property
    def common_request_kwargs(self):
        return dict(
            api_key=self.settings.get("AUTOEXTRACT_USER"),
            endpoint=self.settings.get("AUTOEXTRACT_URL"),
            max_query_error_retries=self.retries_count,
            session=self.aiohttp_session
        )

    async def create_aiohttp_session(self) -> aiohttp.ClientSession:
        concurrent_connections = self.settings.getint("CONCURRENT_REQUESTS", 16)
        logger.info(
            f"AutoExtractProvider concurrent requests: {concurrent_connections}"
        )
        return create_session(connection_pool_size=concurrent_connections)

    async def on_spider_closed(self):
        if self.aiohttp_session:
            await self.aiohttp_session.close()
        self.cache.close()

    def create_retry_wrapper(self):
        return RetryFactory().build()

    async def do_request_cached(self, query, *args, **kwargs):
        assert len(query) == 1  # batches are not supported
        fp = self.cache.fingerprint(query[0])
        try:
            response = self.cache[fp]
            self.stats.inc_value("autoextract/cache/hit")
        except KeyError:
            self.stats.inc_value("autoextract/cache/miss")
            response = await self.do_request(query, *args, **kwargs)
            if "error" not in response[0]:  # don't cache errors
                self.cache[fp] = response
                self.stats.inc_value("autoextract/cache/firsthand")
            else:
                self.stats.inc_value("autoextract/cache/uncacheable")
        return response

    async def do_request(self, *args, **kwargs):
        return await request_raw(*args, **kwargs)

    def pre_process_item_data(self, data) -> Any:
        """
        Hook for transforming data before any further processing, just after
        receive the content
        """
        return data

    def get_per_domain_concurrency_slot(self, request: ScrapyRequest) -> Hashable:
        """
        Return the key that will be used to identify the domain of this request.
        This key is used to modulate the per request concurrency that can be
        set using the setting `AUTOEXTRACT_CONCURRENT_REQUESTS_PER_DOMAIN`.

        By default the key is the request domain. Override it to change
        the behavior.
        """
        return get_domain(request.url)

    def get_filled_request(self,
                           request: ScrapyRequest,
                           provided_cls: Type[AEDataType],
                           should_request_html: bool) -> AutoExtractRequest:
        """Return a filled request for AutoExtract"""
        ae_request = AutoExtractRequest(
            url=request.url,
            pageType=provided_cls.page_type,
        )
        if should_request_html:
            ae_request.extra = {self.html_query_attribute: True}
        return ae_request

    def list_required_requests(self, to_provide: Set[Callable], request: ScrapyRequest):
        is_html_required = AutoExtractHtml in to_provide
        to_provide -= {AutoExtractHtml}
        is_extraction_required = bool(to_provide)
        if is_html_required and not is_extraction_required:
            # At least one request is required to get html
            to_provide = {self.page_type_class_for_html}
        if not to_provide:
            return []
        # Use the recommended type for html request, otherwise use the first one
        class_for_html = (self.page_type_class_for_html
                          if self.page_type_class_for_html in to_provide
                          else next(iter(to_provide)))
        specs = []
        for idx, provided_cls in enumerate(to_provide):
            if not issubclass(provided_cls, AutoExtractData):
                raise RuntimeError(
                    f"Unexpected {provided_cls} requested. Probably a bug in the provider "
                    "or in scrapy-poet itself")

            # html is requested only a single time to save resources
            should_request_html = is_html_required and provided_cls is class_for_html
            ae_request = self.get_filled_request(
                request,
                provided_cls,
                should_request_html
            )
            specs.append(AERequestSpec(
                [ae_request],
                should_request_html,
                is_extraction_required,
                provided_cls
            ))
        return specs

    async def __call__(self,
                       to_provide: Set[Callable],
                       request: ScrapyRequest
                       ) -> List:
        """Make an AutoExtract request and build a Page Input of provided class
        based on API response data.
        """
        if not self.aiohttp_session:
            self.aiohttp_session = await self.create_aiohttp_session()

        instances = []
        for spec in self.list_required_requests(to_provide, request):
            request_stats = AggStats()
            page_type = spec.provided_cls.page_type

            def inc_stats(suffix, value=1, both=False):
                self.stats.inc_value(f"autoextract/total{suffix}", value)
                if both:
                    self.stats.inc_value(f"autoextract/{page_type}{suffix}", value)

            try:
                slot = self.get_per_domain_concurrency_slot(request)
                # When providing same-name arguments in both call and `__init__`
                # this implementation will not cause any errors (while name=value implementation would),
                # so predefined `__init__` arguments would override the same arguments in the call
                awaitable = self.do_request_cached(**{
                    'query': spec.query,
                    'agg_stats': request_stats,
                    **self.common_request_kwargs,
                })
                awaitable = self.per_domain_semaphore.run(awaitable, slot)
                response = await self.task_manager.run(awaitable)
                data = response[0]
                data = self.pre_process_item_data(data)
                if "error" in data:
                    raise QueryError(data["query"], data["error"])

            except CancelledError:
                inc_stats("/pages/cancelled", both=True)
                raise
            except Exception as e:
                inc_stats("/pages/errors", both=True)
                inc_stats(f"/pages/errors{summarize_exception(e)}")
                _stop_if_account_disabled(e, self.crawler)
                raise
            finally:
                inc_stats("/pages/count", both=True)
                inc_stats("/attempts/count", request_stats.n_attempts)
                inc_stats("/attempts/billable", request_stats.n_billable_query_responses)

            if spec.should_request_html:
                instances.append(AutoExtractHtml(url=data[page_type]['url'],
                                                 html=data['html']))
                inc_stats("/pages/html", both=True)

            if spec.is_extraction_required:
                without_html = {k: v for k, v in data.items() if k != "html"}
                instances.append(spec.provided_cls(data=without_html))

            inc_stats("/pages/success", both=True)

        return instances

    def fingerprint(self, to_provide: Set[Callable], request: Request) -> str:
        queries = [spec.query[0].as_dict() for spec in self.list_required_requests(to_provide, request)]
        # pageType is the key to sort by it
        by_page_type = {query['pageType']: query for query in queries}
        for query in by_page_type.values():
            query.pop("pageType")
        return json.dumps(by_page_type, sort_keys=True)

    def serialize(self, result: Sequence[Any]) -> Any:
        return result

    def deserialize(self, data: Any) -> Sequence[Any]:
        return data
