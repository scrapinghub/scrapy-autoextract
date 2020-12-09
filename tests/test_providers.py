import asyncio
import copy
import os
import signal
from asyncio import CancelledError
from signal import SIGINT

import pytest
from pytest_mock import MockerFixture
from pytest_twisted import inlineCallbacks
from twisted.internet.defer import Deferred

from autoextract.aio.errors import ACCOUNT_DISABLED_ERROR_TYPE
from autoextract.stats import AggStats
from autoextract_poet import (
    AutoExtractArticleData, AutoExtractProductData, AutoExtractHtml)
from tests.utils import assert_stats, request_error, async_test
from autoextract_poet.page_inputs import AutoExtractData
from scrapy import Spider
from scrapy.crawler import Crawler
from scrapy_autoextract.providers import (
    AutoExtractProvider, _stop_if_account_disabled,
)
from scrapy_autoextract.errors import QueryError
from scrapy_poet.injection import get_injector_for_testing, get_response_for_testing

DATA_INPUTS = (
    AutoExtractArticleData,
    AutoExtractProductData,
)


def test_stop_spider_on_account_disabled(mocker: MockerFixture):
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
        url, html = "http://example.com", "html_content"
        data_wo_html = {page_type: {"url": url}}
        data = {page_type: {"url": url}, "html": html}
        provider_wrapper = []

        class Provider(AutoExtractProvider):
            async def do_request(self, *args, agg_stats: AggStats, **kwargs):
                assert provider.aiohttp_session.connector.limit == 2020
                agg_stats.n_attempts += 3
                agg_stats.n_billable_query_responses += 2
                assert kwargs['api_key'] == "key"
                assert kwargs['endpoint'] == "url"
                assert kwargs['max_query_error_retries'] == 31415
                return [copy.deepcopy(data)]

        def callback(item: provided_cls):
            pass

        def callback_with_html(item: provided_cls, html: AutoExtractHtml):
            pass

        def callback_only_html(html: AutoExtractHtml):
            pass

        settings = {
            "AUTOEXTRACT_USER": "key",
            "AUTOEXTRACT_URL": "url",
            "AUTOEXTRACT_MAX_QUERY_ERROR_RETRIES": 31415,
            "CONCURRENT_REQUESTS": 2020,
            "CONCURRENT_REQUESTS_PER_DOMAIN": 1980,
        }
        injector = get_injector_for_testing({Provider: 500}, settings)
        stats = injector.crawler.stats
        provider = injector.providers[-1]
        provider_wrapper.append(provider)
        assert provider.per_domain_semaphore.concurrency_per_slot == 1980

        #  - No HTML requested case -

        response = get_response_for_testing(callback)
        kwargs = yield injector.build_callback_dependencies(response.request,
                                                          response)
        assert kwargs["item"].data == data_wo_html
        assert type(kwargs["item"]) is provided_cls
        expected_stats = {
            'autoextract/total/pages/count': 1,
            'autoextract/total/pages/success': 1,
            'autoextract/total/attempts/count': 3,
            'autoextract/total/attempts/billable': 2,
            f'autoextract/{page_type}/pages/count': 1,
            f'autoextract/{page_type}/pages/success': 1
        }
        assert_stats(stats, expected_stats)

        #  - Both HTML and item requested case -

        response = get_response_for_testing(callback_with_html)
        kwargs = yield injector.build_callback_dependencies(response.request,
                                                          response)
        item, html_response = kwargs["item"], kwargs["html"]
        assert item.data == data_wo_html
        assert type(item) is provided_cls
        assert (html_response.url, html_response.html) == (url, html)
        assert type(html_response) is AutoExtractHtml
        expected_stats = {
            'autoextract/total/pages/count': 2,
            'autoextract/total/pages/success': 2,
            'autoextract/total/pages/html': 1,
            'autoextract/total/attempts/count': 6,
            'autoextract/total/attempts/billable': 4,
            f'autoextract/{page_type}/pages/count': 2,
            f'autoextract/{page_type}/pages/success': 2,
            f'autoextract/{page_type}/pages/html': 1,
        }
        assert_stats(stats, expected_stats)

        #  - Only HTML is requested case -

        injector.providers[0].page_type_class_for_html = provided_cls
        response = get_response_for_testing(callback_only_html)
        kwargs = yield injector.build_callback_dependencies(response.request,
                                                          response)
        assert "item" not in kwargs
        html_response = kwargs["html"]
        assert (html_response.url, html_response.html) == (url, html)
        assert type(html_response) is AutoExtractHtml
        expected_stats = {
            'autoextract/total/pages/count': 3,
            'autoextract/total/pages/success': 3,
            'autoextract/total/pages/html': 2,
            'autoextract/total/attempts/count': 9,
            'autoextract/total/attempts/billable': 6,
            f'autoextract/{page_type}/pages/count': 3,
            f'autoextract/{page_type}/pages/success': 3,
            f'autoextract/{page_type}/pages/html': 2,
        }
        assert_stats(stats, expected_stats)


    @inlineCallbacks
    @pytest.mark.parametrize("provided_cls", DATA_INPUTS)
    def test_on_query_error(self, provided_cls: AutoExtractData):
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
            f'autoextract/{page_type}/pages/errors': 1,
            'autoextract/total/attempts/count': 3,
            'autoextract/total/attempts/billable': 2,
            'autoextract/total/pages/count': 1,
            'autoextract/total/pages/errors': 1,
            'autoextract/total/pages/errors/query/Download error': 1
        }
        assert_stats(stats, expected)
        assert "Download error" in str(exinf.value)
        assert "The query" in str(exinf.value)

    @inlineCallbacks
    @pytest.mark.parametrize("provided_cls", DATA_INPUTS)
    def test_on_exception(self, provided_cls: AutoExtractData):

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
            f'autoextract/{page_type}/pages/errors': 1,
            'autoextract/total/attempts/count': 3,
            'autoextract/total/attempts/billable': 2,
            'autoextract/total/pages/count': 1,
            'autoextract/total/pages/errors': 1,
            'autoextract/total/pages/errors/rest/Exception': 1
        }
        assert_stats(stats, expected)

    @async_test
    @pytest.mark.parametrize("provided_cls", DATA_INPUTS)
    async def test_on_cancellation(self, provided_cls: AutoExtractProductData):
        old_handler = signal.getsignal(SIGINT)
        signal.signal(SIGINT, lambda x, y: None)
        try:
            lock = asyncio.Lock()
            await lock.acquire()

            class Provider(AutoExtractProvider):
                async def do_request(self, *args, agg_stats: AggStats, **kwargs):
                    await lock.acquire()

            def callback(item: provided_cls):
                pass

            injector = get_injector_for_testing({Provider: 500})
            stats = injector.crawler.stats
            response = get_response_for_testing(callback)
            deferred = injector.build_callback_dependencies(response.request,
                                                              response)
            build_callbacks_future = Deferred.asFuture(deferred, asyncio.get_event_loop())

            async def cancel_after(sleep):
                await asyncio.sleep(sleep)
                pid = os.getpid()
                try:
                    os.kill(pid, SIGINT)
                except KeyboardInterrupt:
                    # As an effect of the SIGINT killing the process might receive
                    # here a KeyboardInterrupt exception. This is Ok.
                    pass
                return CancelledError()

            result = await asyncio.gather(
                build_callbacks_future, cancel_after(0.05), return_exceptions=True
            )
            assert all([isinstance(r, CancelledError) for r in result])

            page_type = provided_cls.page_type
            expected_stats = {
                'autoextract/total/pages/count': 1,
                'autoextract/total/pages/cancelled': 1,
                'autoextract/total/pages/errors': 0,
                f'autoextract/{page_type}/pages/count': 1,
                f'autoextract/{page_type}/pages/cancelled': 1,
                f'autoextract/{page_type}/pages/errors': 0,
            }
            assert_stats(stats, expected_stats)

        finally:
            signal.signal(SIGINT, old_handler)
