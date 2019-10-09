import os
import sys
import pytest

from w3lib.http import basic_auth_header
from scrapy.http import Request, Response
from scrapy.spiders import Spider
from scrapy.utils.test import get_crawler

sys.path.append(os.getcwd())
from scrapy_autoextract import AutoExtractMiddleware
from scrapy_autoextract.middlewares import AutoExtractConfigError

AUTOX_META = {'autoextract': {'enabled': True}}

MW_SETTINGS = {
    'AUTOEXTRACT_USER': 'apikey',
    'AUTOEXTRACT_PAGE_TYPE': 'article',
}


def setup_module(module):
    global spider
    spider = Spider('spidr')


def _mock_crawler(spider, settings=None):

    class MockedDownloader:
        slots = {}

        def _get_slot_key(self, a, b):
            return str(a) + str(b)

    class MockedEngine:
        downloader = MockedDownloader()
        fake_spider_closed_result = None

        def close_spider(self, spider, reason):
            self.fake_spider_closed_result = (spider, reason)

    # with `spider` instead of `type(spider)` raises an exception
    crawler = get_crawler(type(spider), settings)
    crawler.engine = MockedEngine()
    return crawler


def _assert_disabled(spider, settings=None):
    crawler = _mock_crawler(spider, settings)
    mw = AutoExtractMiddleware.from_crawler(crawler)
    req = Request('http://quotes.toscrape.com', meta=AUTOX_META)
    out = mw.process_request(req, spider)
    assert out is None
    assert req.meta.get('autoextract') is None
    res = Response(req.url, request=req)
    assert mw.process_response(req, res, spider) == res


def _assert_enabled(spider,
                    settings=None,
                    url='http://quotes.toscrape.com',
                    proxyurl='autoextract.scrapinghub.com',
                    proxyauth=basic_auth_header('apikey', '')):
    crawler = _mock_crawler(spider, settings)
    mw = AutoExtractMiddleware.from_crawler(crawler)

    req = Request(url, meta=AUTOX_META)
    out = mw.process_request(req, spider)
    assert proxyurl in out.url
    assert out.meta['autoextract'].get('enabled')
    assert out.headers.get('Authorization') == proxyauth

    resp = Response(out.url, request=out, body=b'[{}]')
    proc = mw.process_response(out, resp, spider)
    assert proc.meta['autoextract'].get('original_url') == url
    assert isinstance(proc.meta['autoextract'].get('article'), dict)


def test_bad_config():
    with pytest.raises(AutoExtractConfigError):
        _assert_disabled(spider, {})
    with pytest.raises(AutoExtractConfigError):
        _assert_disabled(spider, {'AUTOEXTRACT_USER': 'apikey'})


def test_disabled():
    crawler = _mock_crawler(spider, MW_SETTINGS)
    mw = AutoExtractMiddleware.from_crawler(crawler)
    req = Request('http://quotes.toscrape.com', meta={'autoextract': {}})
    out = mw.process_request(req, spider)
    assert out is None


def test_enabled():
    _assert_enabled(spider, MW_SETTINGS)
