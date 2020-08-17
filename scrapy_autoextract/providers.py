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

    page_type: ClassVar[str]
    provided_class: ClassVar[Optional[Type]]

    def __init__(
            self,
            request: Request,
            settings: Settings,
            stats: StatsCollector,
    ):
        self.request = request
        self.stats = stats
        self.settings = settings

    async def __call__(self):
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


class ArticleDataProvider(_Provider):

    page_type = "article"


class ProductDataProvider(_Provider):

    page_type = "product"


def install():
    register(ArticleDataProvider, AutoExtractArticleData)
    register(ProductDataProvider, AutoExtractProductData)
