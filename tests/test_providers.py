import pytest

from autoextract_poet import AutoExtractArticleData, AutoExtractProductData
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
        data = {provided_cls.item_key: {"url": "http://example.com"}}

        class Provider(AutoExtractProvider):
            async def do_request(self, *args, **kwargs):
                assert kwargs['api_key'] == "key"
                assert kwargs['endpoint'] == "url"
                assert kwargs['max_query_error_retries'] == 31415
                return [data]

        def callback(item: provided_cls):
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
        assert stats.get_value(f"autoextract/{provided_cls.item_key}/total") == 1
        assert stats.get_value(
            f"autoextract/{provided_cls.item_key}/error/query") is None
        assert stats.get_value(
            f"autoextract/{provided_cls.item_key}/error/request") is None
        assert stats.get_value(f"autoextract/{provided_cls.item_key}/success") == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("provided_cls", DATA_INPUTS)
    async def test_providers_on_query_error(self, provided_cls: AutoExtractData):
        provided_cls
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
        assert stats.get_value(f"autoextract/{provided_cls.item_key}/total") == 1
        assert stats.get_value(f"autoextract/{provided_cls.item_key}/error/query") == 1
        assert stats.get_value(f"autoextract/{provided_cls.item_key}/error/request") is None
        assert stats.get_value(f"autoextract/{provided_cls.item_key}/success") is None
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

        injector = get_injector_for_testing({Provider: 500})
        response = get_response_for_testing(callback)
        with pytest.raises(Exception) as exinf:
            await injector.build_callback_dependencies(response.request, response)
        stats = injector.crawler.stats
        assert stats.get_value(f"autoextract/{provided_cls.item_key}/total") == 1
        assert stats.get_value(f"autoextract/{provided_cls.item_key}/error/query") is None
        assert stats.get_value(f"autoextract/{provided_cls.item_key}/error/request") == 1
        assert stats.get_value(f"autoextract/{provided_cls.item_key}/success") is None
