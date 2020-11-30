import pytest

from autoextract_poet import AutoExtractArticleData, AutoExtractProductData, \
    AutoExtractHtml
from autoextract_poet.page_inputs import AutoExtractData
from scrapy_autoextract.providers import (
    QueryError, AutoExtractProvider,
)
from scrapy_poet.injection import get_injector_for_testing, \
    get_response_for_testing

DATA_INPUTS = (
    AutoExtractArticleData,
    AutoExtractProductData,
)


def test_query_error():
    exc = QueryError({"foo": "bar"}, "sample error")
    assert str(exc) == "QueryError: query={'foo': 'bar'}, message='sample error'"


class TestProviders:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("provided_cls", DATA_INPUTS)
    async def test_providers(self, provided_cls: AutoExtractProductData):
        page_type = provided_cls.page_type
        data = {page_type: {"url": "http://example.com", "html": "html_content"}}

        class Provider(AutoExtractProvider):
            async def do_request(self, *args, **kwargs):
                assert kwargs['api_key'] == "key"
                assert kwargs['endpoint'] == "url"
                assert kwargs['max_query_error_retries'] == 31415
                return [data]

        def callback(item: provided_cls):
            pass

        def callback_with_html(item: provided_cls, html: AutoExtractHtml):
            pass

        def callback_only_html(html: AutoExtractHtml):
            pass

        settings = {
            "AUTOEXTRACT_USER": "key",
            "AUTOEXTRACT_URL": "url",
            "AUTOEXTRACT_MAX_QUERY_ERROR_RETRIES": 31415
        }
        injector = get_injector_for_testing({Provider: 500}, settings)
        response = get_response_for_testing(callback)
        deps = await injector.build_callback_dependencies(response.request,
                                                          response)
        assert deps["item"].data == data
        assert type(deps["item"]) is provided_cls
        stats = injector.crawler.stats
        assert stats.get_value(f"autoextract/{page_type}/total") == 1
        assert stats.get_value(
            f"autoextract/{page_type}/error/query") is None
        assert stats.get_value(
            f"autoextract/{page_type}/error/request") is None
        assert stats.get_value(f"autoextract/{page_type}/success") == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("provided_cls", DATA_INPUTS)
    async def test_providers_on_query_error(self, provided_cls: AutoExtractData):
        page_type = provided_cls.page_type
        data = {"query": "The query", "error": "This is an error"}

        class Provider(AutoExtractProvider):
            async def do_request(self, *args, **kwargs):
                return [data]

        def callback(item: provided_cls):
            pass

        injector = get_injector_for_testing({Provider: 500})
        response = get_response_for_testing(callback)
        with pytest.raises(QueryError) as exinf:
            await injector.build_callback_dependencies(response.request, response)
        stats = injector.crawler.stats
        assert stats.get_value(f"autoextract/{page_type}/total") == 1
        assert stats.get_value(f"autoextract/{page_type}/error/query") == 1
        assert stats.get_value(f"autoextract/{page_type}/error/request") is None
        assert stats.get_value(f"autoextract/{page_type}/success") is None
        assert "This is an error" in str(exinf.value)
        assert "The query" in str(exinf.value)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("provided_cls", DATA_INPUTS)
    async def test_providers_on_exception(self, provided_cls: AutoExtractData):

        class Provider(AutoExtractProvider):
            async def do_request(self, *args, **kwargs):
                raise Exception()

        def callback(item: provided_cls):
            pass

        page_type = provided_cls.page_type
        injector = get_injector_for_testing({Provider: 500})
        response = get_response_for_testing(callback)
        with pytest.raises(Exception) as exinf:
            await injector.build_callback_dependencies(response.request, response)
        stats = injector.crawler.stats
        assert stats.get_value(f"autoextract/{page_type}/total") == 1
        assert stats.get_value(f"autoextract/{page_type}/error/query") is None
        assert stats.get_value(f"autoextract/{page_type}/error/request") == 1
        assert stats.get_value(f"autoextract/{page_type}/success") is None
