import json
import pytest
from copy import deepcopy

from w3lib.http import basic_auth_header
from scrapy.http import Request, Response
from scrapy.spiders import Spider
from scrapy.utils.test import get_crawler

from scrapy_autoextract import AutoExtractMiddleware
from scrapy_autoextract.middlewares import AutoExtractError, AutoExtractConfigError

AUTOX_META = {'autoextract': {'enabled': True}}

MW_SETTINGS = {
    'AUTOEXTRACT_USER': 'apikey',
    'AUTOEXTRACT_PAGE_TYPE': 'article',
}


def setup_module(module):
    global spider
    spider = Spider('spidr')


def _mock_mw(spider, settings=None):

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
    return AutoExtractMiddleware.from_crawler(crawler)


def _assert_disabled(spider, settings=None):
    mw = _mock_mw(spider, settings)
    req = Request('http://quotes.toscrape.com', meta=AUTOX_META)
    out = mw.process_request(req, spider)
    assert out is None
    assert req.meta.get('autoextract') is None
    res = Response(req.url, request=req)
    assert mw.process_response(req, res, spider) == res


def _assert_enabled(spider,
                    settings=None,
                    url='http://quotes.toscrape.com',
                    api_url='autoextract.scrapinghub.com',
                    api_auth=basic_auth_header('apikey', '')):
    mw = _mock_mw(spider, settings)

    req = Request(url, meta=AUTOX_META)
    out = mw.process_request(req, spider)
    assert api_url in out.url
    assert out.meta['autoextract'].get('enabled')
    assert out.headers.get('Authorization') == api_auth
    assert 'User-Agent' in out.headers

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
    mw = _mock_mw(spider, MW_SETTINGS)
    req = Request('http://quotes.toscrape.com', meta={'autoextract': {}})
    out = mw.process_request(req, spider)
    assert out is None


def test_enabled():
    _assert_enabled(spider, MW_SETTINGS)


def test_request_error():
    mw = _mock_mw(spider, MW_SETTINGS)
    req = Request('http://quotes.toscrape.com', meta=AUTOX_META)

    out = mw.process_request(req, spider)
    err = b'{"title":"No authentication token provided","type":"http://errors.xod.scrapinghub.com/unauthorized.html"}'
    resp = Response(out.url, request=out, body=err)
    with pytest.raises(AutoExtractError):
        mw.process_response(out, resp, spider)


def test_timeout():
    config = dict(MW_SETTINGS)
    # add a very low timeout - the middleware will ignore it
    config['AUTOEXTRACT_TIMEOUT'] = 1
    mw = _mock_mw(spider, config)
    req = Request('http://quotes.toscrape.com', meta=AUTOX_META)
    out = mw.process_request(req, spider)
    assert out is not None
    assert out.meta['download_timeout'] >= 180

    config['AUTOEXTRACT_TIMEOUT'] = 10000
    mw = _mock_mw(spider, config)
    req = Request('http://quotes.toscrape.com', meta=AUTOX_META)
    out = mw.process_request(req, spider)
    assert out is not None
    assert out.meta['download_timeout'] == 10000


def test_meta_extra():
    config = dict(MW_SETTINGS)
    mw = _mock_mw(spider, config)
    meta = deepcopy(AUTOX_META)
    meta['autoextract']['extra'] = {'some': 'stuff'}
    req = Request('http://quotes.toscrape.com', meta=meta)
    out = mw.process_request(req, spider)
    assert out is not None
    payload = json.loads(out.body.decode('utf8'))[0]
    assert payload['some'] == 'stuff'


def test_meta_headers():
    config = dict(MW_SETTINGS)
    mw = _mock_mw(spider, config)
    meta = deepcopy(AUTOX_META)
    meta['autoextract']['headers'] = {'UA': 'stuff'}
    req = Request('http://quotes.toscrape.com', meta=meta)
    out = mw.process_request(req, spider)
    assert out is not None
    assert out.headers['UA'].decode('utf8') == 'stuff'
