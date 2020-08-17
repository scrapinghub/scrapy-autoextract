from typing import ClassVar, Optional, Type

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


class _Provider(PageObjectInputProvider):
    """An interface that describes a generic AutoExtract Provider.

    It should not be used publicly as it serves the purpose of being a base
    class for more specific providers such as Article and Product providers.
    """

    page_type: ClassVar[str]
    provided_class: ClassVar[Optional[Type]]

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
        self.stats.inc_value(f"autoextract/{self.page_type}/total")

        request = AutoExtractRequest(
            url=self.request.url,
            pageType=self.page_type,
        )

        try:
            data = await request_raw(
                [request.as_dict()],
                api_key=self.settings.get('AUTOEXTRACT_USER'),
                max_query_error_retries=3
            )[0]
        except Exception:
            self.stats.inc_value(f"autoextract/{self.page_type}/error")
            raise

        self.stats.inc_value(f"autoextract/{self.page_type}/success")
        return self.provided_class(data=data)

    @classmethod
    def register(cls):
        """Register this provider for its provided class on scrapy-poet
        registry. This will make it possible to declare provided class as
        a callback dependency when writing Scrapy spiders.
        """
        register(cls, cls.provided_class)


class ArticleDataProvider(_Provider):

    page_type = "article"
    provided_class = AutoExtractArticleData


class ProductDataProvider(_Provider):

    page_type = "product"
    provided_class = AutoExtractProductData


def install():
    """Register all providers for their respective provided classes."""
    ArticleDataProvider.register()
    ProductDataProvider.register()
