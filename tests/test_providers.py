import pytest
from pytest_mock import MockerFixture
from pytest_twisted import inlineCallbacks

from autoextract.aio.errors import ACCOUNT_DISABLED_ERROR_TYPE
from autoextract.stats import AggStats
from autoextract_poet import (
    AutoExtractArticleData, AutoExtractProductData, AutoExtractHtml)
from tests.utils import assert_stats, request_error
from autoextract_poet.page_inputs import AutoExtractData
from scrapy import Spider
from scrapy.crawler import Crawler
from scrapy_autoextract.providers import (
    QueryError, AutoExtractProvider, _stop_if_account_disabled,
)
from scrapy_poet.injection import get_injector_for_testing, get_response_for_testing

DATA_INPUTS = (
    AutoExtractArticleData,
    AutoExtractProductData,
)


def test_query_error():
    exc = QueryError({"foo": "bar"}, "sample error")
    assert str(exc) == "QueryError: query={'foo': 'bar'}, message='sample error'"


def test_stop_on_account_disabled(mocker: MockerFixture):
    class Engine:
        close_spider = mocker.Mock()

    class _EmptySpider(Spider):
        name = "empty_spider"

    crawler = Crawler(_EmptySpider)
    crawler.engine = Engine()
    spider = _EmptySpider.from_crawler(crawler)
    crawler.spider = spider

    _stop_if_account_disabled(Exception(), crawler)
    spider.crawler.engine.close_spider.assert_not_called()

    re = request_error({"type": "whatever"})
    _stop_if_account_disabled(re, crawler)
    spider.crawler.engine.close_spider.assert_not_called()

    re = request_error({"type": ACCOUNT_DISABLED_ERROR_TYPE})
    _stop_if_account_disabled(re, crawler)
    spider.crawler.engine.close_spider.assert_called_with(spider, "account_disabled")


class TestProviders:

    @inlineCallbacks
    @pytest.mark.parametrize("provided_cls", DATA_INPUTS)
    def test_providers(self, provided_cls: AutoExtractProductData):
        page_type = provided_cls.page_type
        data = {page_type: {"url": "http://example.com", "html": "html_content"}}

        class Provider(AutoExtractProvider):
            async def do_request(self, *args, agg_stats: AggStats, **kwargs):
                agg_stats.n_attempts += 3
                agg_stats.n_billable_query_responses += 2
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
        deps = yield injector.build_callback_dependencies(response.request,
                                                          response)
        assert deps["item"].data == data
        assert type(deps["item"]) is provided_cls
        stats = injector.crawler.stats
        expected_stats = {
            'autoextract/total/pages/count': 1,
            'autoextract/total/pages/success': 1,
            'autoextract/total/attempts/count': 3,
            'autoextract/total/attempts/billable': 2,
            f'autoextract/{page_type}/pages/count': 1,
            f'autoextract/{page_type}/pages/success': 1
        }
        assert_stats(stats, expected_stats)

    @inlineCallbacks
    @pytest.mark.parametrize("provided_cls", DATA_INPUTS)
    def test_providers_on_query_error(self, provided_cls: AutoExtractData):
        page_type = provided_cls.page_type
        data = {"query": "The query", "error": "Download error"}

        class Provider(AutoExtractProvider):
            async def do_request(self, *args, agg_stats: AggStats, **kwargs):
                agg_stats.n_attempts += 3
                agg_stats.n_billable_query_responses += 2
                return [data]

        def callback(item: provided_cls):
            pass

        injector = get_injector_for_testing({Provider: 500})
        response = get_response_for_testing(callback)
        with pytest.raises(QueryError) as exinf:
            yield injector.build_callback_dependencies(response.request, response)
        stats = injector.crawler.stats
        expected = {
            f'autoextract/{page_type}/pages/count': 1,
            f'autoextract/{page_type}/pages/error': 1,
            'autoextract/total/attempts/count': 3,
            'autoextract/total/attempts/billable': 2,
            'autoextract/total/pages/count': 1,
            'autoextract/total/pages/error': 1,
            'autoextract/total/pages/error/query/Download error': 1
        }
        assert_stats(stats, expected)
        assert "Download error" in str(exinf.value)
        assert "The query" in str(exinf.value)

    @inlineCallbacks
    @pytest.mark.parametrize("provided_cls", DATA_INPUTS)
    def test_providers_on_exception(self, provided_cls: AutoExtractData):

        class Provider(AutoExtractProvider):
            async def do_request(self, *args, agg_stats: AggStats, **kwargs):
                agg_stats.n_attempts += 3
                agg_stats.n_billable_query_responses += 2
                raise Exception()

        def callback(item: provided_cls):
            pass

        page_type = provided_cls.page_type
        injector = get_injector_for_testing({Provider: 500})
        response = get_response_for_testing(callback)
        with pytest.raises(Exception) as exinf:
            yield injector.build_callback_dependencies(response.request, response)
        stats = injector.crawler.stats
        expected = {
            f'autoextract/{page_type}/pages/count': 1,
            f'autoextract/{page_type}/pages/error': 1,
            'autoextract/total/attempts/count': 3,
            'autoextract/total/attempts/billable': 2,
            'autoextract/total/pages/count': 1,
            'autoextract/total/pages/error': 1,
            'autoextract/total/pages/error/rest/Exception': 1
        }
        assert_stats(stats, expected)
