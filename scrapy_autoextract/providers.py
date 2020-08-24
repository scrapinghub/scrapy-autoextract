from typing import ClassVar, Type

from autoextract.aio import request_raw
from autoextract.request import Request as AutoExtractRequest
from autoextract_poet.page_inputs import (
    AutoExtractArticleData,
    AutoExtractProductData,
)
from scrapy import Request
from scrapy.settings import Settings
from scrapy.statscollectors import StatsCollector
from scrapy_poet.page_input_providers import (
    PageObjectInputProvider,
    register,
)


class QueryLevelError(Exception):

    pass


class _Provider(PageObjectInputProvider):
    """An interface that describes a generic AutoExtract Provider.

    It should not be used publicly as it serves the purpose of being a base
    class for more specific providers such as Article and Product providers.
    """

    provided_class: ClassVar[Type]  # needs item_key attr and to_item method

    def __init__(
            self,
            request: Request,
            settings: Settings,
            stats: StatsCollector,
    ):
        """Initialize provider storing its dependencies as attributes."""
        self.request = request
        self.stats = stats
        self.settings = settings

    async def __call__(self):
        """Make an AutoExtract request and build a Page Input of provided class
        based on API response data.
        """
        page_type = self.get_page_type()
        self.stats.inc_value(f"autoextract/{page_type}/total")

        request = AutoExtractRequest(
            url=self.request.url,
            pageType=page_type,
        )
        api_key = self.settings.get("AUTOEXTRACT_USER")
        endpoint = self.settings.get("AUTOEXTRACT_URL")
        max_query_error_retries = self.settings.getint(
            "AUTOEXTRACT_MAX_QUERY_ERROR_RETRIES", 3
        )

        try:
            response = await request_raw(
                [request],
                api_key=api_key,
                endpoint=endpoint,
                max_query_error_retries=max_query_error_retries
            )
        except Exception:
            self.stats.inc_value(f"autoextract/{page_type}/error/request")
            raise

        data = response[0]

        if "error" in data:
            self.stats.inc_value(f"autoextract/{page_type}/error/query")
            raise QueryLevelError(
                f"Error '{data['error']}' while processing {self.request}"
            )

        self.stats.inc_value(f"autoextract/{page_type}/success")
        return self.provided_class(data=data)

    @classmethod
    def register(cls):
        """Register this provider for its provided class on scrapy-poet
        registry. This will make it possible to declare provided class as
        a callback dependency when writing Scrapy spiders.
        """
        register(cls, cls.provided_class)

    @classmethod
    def get_page_type(cls) -> str:
        """Page type is defined by the class attribute `item_key` available on
        `autoextract_poet.page_inputs` classes.
        """
        return cls.provided_class.item_key


class ArticleDataProvider(_Provider):

    provided_class = AutoExtractArticleData


class ProductDataProvider(_Provider):

    provided_class = AutoExtractProductData


def install():
    """Register all providers for their respective provided classes."""
    ArticleDataProvider.register()
    ProductDataProvider.register()
