import inspect
from typing import Callable, Set, ClassVar, Type, List, Any

import attr

from autoextract.aio import request_raw
from autoextract.request import Request as AutoExtractRequest
from autoextract_poet.items import Item
from autoextract_poet.page_inputs import (
    AutoExtractProductData, AutoExtractData, AutoExtractHtml,
)
from scrapy import Request as ScrapyRequest
from scrapy.crawler import Crawler
from scrapy.statscollectors import StatsCollector
from scrapy_poet.page_input_providers import PageObjectInputProvider


class QueryError(Exception):

    def __init__(self, query: dict, message: str):
        self.query = query
        self.message = message

    def __str__(self):
        return f"QueryError: query={self.query}, message='{self.message}'"


class AutoExtractProvider(PageObjectInputProvider):
    """An interface that describes a generic AutoExtract Provider.
    It should not be used publicly as it serves the purpose of being a base
    class for more specific providers such as Article and Product providers.
    """
    page_type_class: ClassVar[Type]

    # pageType requested when only html is required
    page_type_for_html: ClassVar[AutoExtractData] = AutoExtractProductData
    html_query_attribute: ClassVar[str] = "fullHtml"

    @classmethod
    def provided_classes(cls, type_ :Callable) -> bool:
        return (inspect.isclass(type_) and
                issubclass(type_, (AutoExtractData, AutoExtractHtml)))

    def __init__(self, crawler: Crawler):
        """Initialize provider storing its dependencies as attributes."""
        settings = crawler.spider.settings
        self.common_request_kwargs = dict(
            api_key=settings.get("AUTOEXTRACT_USER"),
            endpoint = settings.get("AUTOEXTRACT_URL"),
            max_query_error_retries = settings.getint(
                "AUTOEXTRACT_MAX_QUERY_ERROR_RETRIES", 3)
        )

    async def do_request(self, *args, **kwargs):
        return await request_raw(*args, **kwargs)

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
            to_provide = {self.page_type_for_html}

        instances = []
        for idx, provided_cls in enumerate(to_provide):

            if not issubclass(provided_cls, AutoExtractData):
                raise RuntimeError(
                    f"Unexpected {provided_cls} requested. Probably a bug in the provider "
                    "or in scrapy-poet itself")

            is_first_request = idx == 0
            page_type = provided_cls.page_type
            stats.inc_value(f"autoextract/{page_type}/total")

            try:
                # html is requested only a single time to save resources
                should_request_html = is_html_required and is_first_request
                ae_request = self.get_filled_request(
                    request,
                    provided_cls,
                    should_request_html
                )
                response = await self.do_request(**{
                    'query': [ae_request],
                    **self.common_request_kwargs,
                })
                data = response[0]

            except Exception:
                stats.inc_value(f"autoextract/{page_type}/error/request")
                raise

            if "error" in data:
                stats.inc_value(f"autoextract/{page_type}/error/query")
                raise QueryError(data["query"], data["error"])

            provided_cls.item_class
            instances.append(provided_cls(data=data))
            stats.inc_value(f"autoextract/{page_type}/success")

            if should_request_html:
                instances.append(AutoExtractHtml(url=data['url'], html=data['html']))
                stats.inc_value(f"autoextract/html")

        return instances

    def get_filled_request(self,
                           request: ScrapyRequest,
                           provided_cls : AutoExtractData,
                           should_request_html: bool) -> AutoExtractRequest:
        """Return a filled request for AutoExtract"""
        ae_request = AutoExtractRequest(
            url=request.url,
            pageType=provided_cls.page_type,
        )
        if should_request_html:
            ae_request.extra = {self.html_query_attribute: True}
        return ae_request
