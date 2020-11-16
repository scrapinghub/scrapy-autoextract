from typing import Callable, Dict, Set, Any, ClassVar, Type

from autoextract.aio import request_raw
from autoextract.request import Request as AutoExtractRequest
from autoextract_poet.page_inputs import (
    AutoExtractArticleData,
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


class _Provider(PageObjectInputProvider):
    """An interface that describes a generic AutoExtract Provider.
    It should not be used publicly as it serves the purpose of being a base
    class for more specific providers such as Article and Product providers.
    """
    page_type_class: ClassVar[Type]

    @classmethod
    def provided_classes(cls, type_ :Callable) -> bool:
        return type_ in (cls.page_type_class, AutoExtractHtml)

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
                       ) -> Dict[Callable, Any]:
        """Make an AutoExtract request and build a Page Input of provided class
        based on API response data.
        """
        for cls in to_provide:
            if issubclass(cls, AutoExtractData):
                page_type = cls.item_key
                stats.inc_value(f"autoextract/{page_type}/total")

                request = AutoExtractRequest(
                    url=request.url,
                    pageType=page_type,
                )
                try:
                    response = await self.do_request(**{
                        'query': [request],
                        **self.common_request_kwargs
                    })
                except Exception:
                    stats.inc_value(f"autoextract/{page_type}/error/request")
                    raise

                data = response[0]

                if "error" in data:
                    stats.inc_value(f"autoextract/{page_type}/error/query")
                    raise QueryError(data["query"], data["error"])

                stats.inc_value(f"autoextract/{page_type}/success")
                return {cls: cls(data=data)}
            elif cls is AutoExtractHtml:
                raise NotImplemented()
            else:
                raise RuntimeError(
                    f"Unexpected {cls} requested. Probably a bug in the provider "
                    f"or in scrapy-poet itself")


class ArticleDataProvider(_Provider):
    page_type_class = AutoExtractArticleData


class ProductDataProvider(_Provider):
    page_type_class = AutoExtractProductData
