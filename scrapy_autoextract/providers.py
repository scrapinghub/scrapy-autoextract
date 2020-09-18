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
        providers = self.request.meta.get("_autoextract_providers", [])
        self.request.meta["_autoextract_providers"] = providers + [self]

    async def __call__(self):
        """Make an AutoExtract request and build a Page Input of provided class
        based on API response data.
        """
        data = await self._fetch_data()
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

    async def _fetch_data(self):
        page_type = self.provided_class.item_key

        # When the backend includes support for multiple page types in a single
        # request, we'll be able to remove this condition and always try to
        # return the cached data on request's meta.
        if page_type == "html":
            # Retrieve cached data on request's meta
            data = self.request.meta.get("_autoextract_data")
            if data is not None:
                return data

        # When backend includes support for "html" page type, we'll be able to
        # remove this condition.
        if page_type == "html":
            # There's no support on the backed for an "html" page type yet,
            # so let's use a dummy page type here
            page_type = "article"

        self.stats.inc_value("autoextract/total")

        request = AutoExtractRequest(
            url=self.request.url,
            pageType=page_type,
            extra=self.request.meta.get("_autoextract_extra"),
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

        data = response[0]
        self.stats.inc_value("autoextract/success")
        self.request.meta["_autoextract_data"] = data
        return data


class HTMLDataProvider(_Provider):

    provided_class = AutoExtractHTMLData

    def __before__(self):
        super().__before__()
        extra = self.request.meta.get("_autoextract_extra", {})
        extra.update({
            self.html_argument: True,
        })
        self.request.meta["_autoextract_extra"] = extra

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
