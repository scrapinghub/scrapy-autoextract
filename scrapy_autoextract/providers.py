import asyncio
from typing import ClassVar, Type

from autoextract.aio import request_raw
from autoextract.request import Request as AutoExtractRequest
from autoextract_poet.page_inputs import (
    AutoExtractHTMLData,
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

AUTOEXTRACT_EXTRA_KEY = "__autoextract_extra"
AUTOEXTRACT_PROVIDERS_KEY = "__autoextract_providers"
AUTOEXTRACT_RESPONSE_KEY = "__autoextract_response"


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

    def __before__(self):
        self.providers.append(self)

    async def __call__(self):
        """Make an AutoExtract request and build a Page Input of provided class
        based on API response data.
        """
        try:
            if self.providers[-1] is self:
                await self._fetch_data()
        except IndexError:
            # FIXME: it's not possible to use this alone yet
            raise Exception("AutoExtractHTMLData should not be used alone")

        data = await self._await_data()

        if "error" in data:
            self.stats.inc_value("autoextract/error/query")
            raise QueryError(data["query"], data["error"])

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

    @property
    def extra(self):
        """Get AutoExtract extra parameters stored on Scrapy's Request."""
        return getattr(self.request, AUTOEXTRACT_EXTRA_KEY, {})

    @extra.setter
    def extra(self, value):
        """Set AutoExtract extra parameters on Scrapy's Request.

        This value can be shared across different AutoExtract providers.
        """
        setattr(self.request, AUTOEXTRACT_EXTRA_KEY, value)

    @property
    def providers(self):
        """Get AutoExtract providers stored on Scrapy's Request."""
        providers = getattr(self.request, AUTOEXTRACT_PROVIDERS_KEY, None)
        if providers is None:
            providers = list()
            setattr(self.request, AUTOEXTRACT_PROVIDERS_KEY, providers)

        return providers

    @property
    def response(self):
        """Get AutoExtract response stored on Scrapy's Request."""
        return getattr(self.request, AUTOEXTRACT_RESPONSE_KEY, None)

    @response.setter
    def response(self, value):
        """Set AutoExtract response on Scrapy's Request.

        This value can be shared across different AutoExtract providers.
        """
        setattr(self.request, AUTOEXTRACT_RESPONSE_KEY, value)

    async def _fetch_data(self):
        self.stats.inc_value("autoextract/total")

        request = AutoExtractRequest(
            url=self.request.url,
            pageType=self.get_page_type(),
            extra=self.extra,
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
            self.stats.inc_value("autoextract/error/request")
            raise

        self.stats.inc_value("autoextract/success")
        self.response = response

    async def _await_data(self):
        response = None
        while response is None:
            response = self.response
            await asyncio.sleep(0.2)

        data = response[0]
        return data


class HTMLDataProvider(_Provider):

    provided_class = AutoExtractHTMLData

    def __before__(self):
        self.extra = {
            self.html_argument: True,
        }

    @property
    def html_argument(self):
        """Argument name used by AutoExtract to specify if a request should
        also return HTML data on its response.

        By default, AutoExtract names this argument as "fullHtml".

        You can override this argument name by defining the
        ``AUTOEXTRACT_HTML_ARGUMENT`` string in your Scrapy settings.

        Why would you like to change this argument name?

        Currently, production servers are supposed to work with the "fullHtml"
        argument only. You might want to change this argument name when
        experimenting with stating/development servers, when a custom argument
        could be used to force a certain browser stack to be used when
        rendering HTML content and stuff like that.
        """
        return self.settings.get("AUTOEXTRACT_HTML_ARGUMENT", "fullHtml")


class ArticleDataProvider(_Provider):

    provided_class = AutoExtractArticleData


class ProductDataProvider(_Provider):

    provided_class = AutoExtractProductData


def install():
    """Register all providers for their respective provided classes."""
    HTMLDataProvider.register()
    ArticleDataProvider.register()
    ProductDataProvider.register()
