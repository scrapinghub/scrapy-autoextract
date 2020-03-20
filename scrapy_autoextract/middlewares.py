import time
import json
import logging

import scrapy
from scrapy import signals
from scrapy.http import Headers, HtmlResponse
from scrapy.utils.python import global_object_name
from scrapy.exceptions import IgnoreRequest, DropItem
from w3lib.http import basic_auth_header

from .__version__ import __version__

logger = logging.getLogger(__name__)

AUTOEXTRACT_META_KEY = '_autoextract_processed'
USER_AGENT = 'scrapy-autoextract/{} scrapy/{}'.format(__version__, scrapy.__version__)
MAX_ERROR_BODY = 2000


class AutoExtractError(Exception):
    pass


class AutoExtractConfigError(Exception):
    pass


class SlotPolicy(object):
    PER_DOMAIN = 'per_domain'
    SINGLE_SLOT = 'single_slot'
    SCRAPY_DEFAULT = 'scrapy_default'


class AutoExtractMiddleware(object):
    """
    Middleware that allows a Scrapy Spider to receive Automatic Data Extraction
    results within the `response.meta`.

    The service URL can be specified with `AUTOEXTRACT_URL` in scrapy settings.
    """

    DEFAULT_URL = 'https://autoextract.scrapinghub.com/v1/extract'
    DEFAULT_TIMEOUT = 660
    DEFAULT_SLOT_POLICY = SlotPolicy.PER_DOMAIN

    def __init__(self, crawler):
        self.crawler = crawler
        self.settings = crawler.settings
        self._api_user = self.settings['AUTOEXTRACT_USER']
        self._api_pass = ''
        self.page_type = self.settings['AUTOEXTRACT_PAGE_TYPE']
        if not self.page_type:
            self.page_type = getattr(crawler.spider, 'page_type', None)
        self.timeout = max(
            self.settings.getint('AUTOEXTRACT_TIMEOUT', self.DEFAULT_TIMEOUT),
            self.settings.getint('DOWNLOAD_TIMEOUT', 180),
        )
        self.slot_policy = self.settings.get('AUTOEXTRACT_SLOT_POLICY', self.DEFAULT_SLOT_POLICY)

        self._api_url = self.settings.get('AUTOEXTRACT_URL', self.DEFAULT_URL)
        logger.info('Using AutoExtract API URL: %s', self._api_url, extra={'spider': crawler.spider})

        self.nr_resp = 0
        self.avg_latency = 0
        self.max_latency = 0
        self.total_latency = 0

    @classmethod
    def from_crawler(cls, crawler):
        if not crawler.settings.get('AUTOEXTRACT_USER'):
            raise AutoExtractConfigError('AUTOEXTRACT_USER is required')
        o = cls(crawler)
        crawler.signals.connect(o.spider_closed, signal=signals.spider_closed)
        return o

    def spider_closed(self, spider):
        if self.nr_resp > 0:
            self.autoextract_latency_stats()
            logger.info(
                'Total "%i" responses from AutoExtract, average latency=%.3f, max latency=%.3f',
                self.nr_resp,
                self.avg_latency,
                self.max_latency,
                extra={'spider': spider},
            )

    def process_request(self, request, spider):
        """
        The request will be passed to the AutoExtract server only if the request
        is explicitly enabled with `{'autoextract': {'enabled': True}}` meta.
        The page type value must be also present, either in the
        AUTOEXTRACT_PAGE_TYPE option, or in `{'autoextract': {'pageType': '...'}}` meta.
        """
        if not self._is_enabled_for_request(request):
            return

        # If the request was already processed by AutoExtract
        if request.meta.get(AUTOEXTRACT_META_KEY):
            return

        if request.method != 'GET':
            raise AutoExtractError('Only GET requests are supported by AutoExtract')

        request.meta[AUTOEXTRACT_META_KEY] = {
            'original_url': request.url,
            'timing': {
                'start_ts': time.time()
            },
        }

        # Maybe over-write the page type value from the request
        page_type = self._check_page_type(request)
        logger.debug('Process AutoExtract request for %s URL %s',
                     page_type,
                     request,
                     extra={'spider': spider})

        # Define request timeout
        request.meta['download_timeout'] = self.timeout

        # Define concurrency settings
        self._set_download_slot(request, request.meta)

        payload = {'url': request.url, 'pageType': page_type}

        # Add the extra payload, if available
        extra_payload = self._get_meta_name(request, 'extra')
        if extra_payload:
            payload.update(extra_payload)

        headers = Headers({
            'Content-Type': 'application/json',
            'User-Agent': USER_AGENT,
            'Authorization': basic_auth_header(self._api_user, self._api_pass)
        })
        # Update the headers, if provided
        extra_headers = self._get_meta_name(request, 'headers')
        if extra_headers:
            headers.update(extra_headers)

        new_request = request.replace(
            url=self._api_url,
            method='POST',
            headers=headers,
            body=json.dumps([payload], sort_keys=True),
        )

        self.inc_metric('autoextract/request_count')
        return new_request

    def process_response(self, request, response, spider):
        if not self._is_enabled_for_request(request):
            return response

        # If the request was never processed by AutoExtract
        if not request.meta.get(AUTOEXTRACT_META_KEY):
            return response

        url = request.meta[AUTOEXTRACT_META_KEY]['original_url']
        body = response.body.decode('utf8')

        try:
            response_object = json.loads(body)
        except Exception:
            self.inc_metric('autoextract/errors/json_decode')
            self._log_debug_error(response, body)
            raise AutoExtractError('Cannot parse JSON response from AutoExtract'
                                   ' for {}: {}'.format(url, response.body[:MAX_ERROR_BODY]))

        if response.status != 200:
            self.inc_metric('autoextract/errors/response_error/{}'.format(response.status))
            self._log_debug_error(response, body)
            raise AutoExtractError('Received error from AutoExtract for '
                                   '{}: {}'.format(url, response_object))

        result = None
        if isinstance(response_object, list):
            result = response_object[0]
        else:
            self.inc_metric('autoextract/errors/type_error')
            self._log_debug_error(response, body)
            raise AutoExtractError('Received invalid response from AutoExtract for '
                                   '{}: {}'.format(url, response_object))

        if result.get('error'):
            self.inc_metric('autoextract/errors/result_error')
            self._log_debug_error(response, body)
            raise AutoExtractError('Received error from AutoExtract for '
                                   '{}: {}'.format(url, result["error"]))

        stop_time = time.time()
        latency = stop_time - request.meta[AUTOEXTRACT_META_KEY]['timing']['start_ts']

        self.nr_resp += 1
        self.total_latency += latency
        self.max_latency = max(self.max_latency, latency)
        self.avg_latency = float(self.total_latency) / self.nr_resp
        self.autoextract_latency_stats()

        autoextract = request.meta.pop(AUTOEXTRACT_META_KEY)
        # Middleware-level timings
        autoextract['timing'].update({'end_ts': stop_time, 'latency': latency})

        page_type = self._check_page_type(request)
        logger.debug('AutoExtract latency for %s URL %s was %.3fs',
                     page_type,
                     url,
                     latency,
                     extra={'spider': spider})

        # The AutoExtract processed item is added here
        autoextract[page_type] = result.get(page_type) or {}
        request.meta['autoextract'] = autoextract
        page_html = result.pop('html', '<body></body>')

        return HtmlResponse(
            url,
            request=request,
            body=page_html.encode('utf-8'),
            encoding='utf-8',
        )

    def process_exception(self, request, exception, spider):
        if isinstance(exception, (IgnoreRequest, DropItem)):
            return
        if not self._is_enabled_for_request(request):
            return

        autoextract = request.meta.pop(AUTOEXTRACT_META_KEY)
        stop_time = time.time()
        latency = time.time() - autoextract['timing']['start_ts']
        autoextract['timing'].update({'end_ts': stop_time, 'latency': latency})

        # Make sure to log all unknown failures
        logger.warning('AutoExtract failure after %.3fs for %s: %s',
                       latency,
                       autoextract['original_url'],
                       repr(exception),
                       extra={'spider': spider})

        request.meta['autoextract'] = autoextract
        ex_class = global_object_name(exception.__class__)
        self.inc_metric('autoextract/errors/total_count', spider=spider)
        self.inc_metric('autoextract/errors/type_count/%s' % ex_class, spider=spider)

    def _is_enabled_for_request(self, request):
        if 'autoextract' not in request.meta:
            return False
        if not request.meta.get('autoextract', {}).get('enabled'):
            return False
        return True

    def _check_page_type(self, request):
        # Use pageType value from the request.meta['autoextract']
        # and fallback to the value from middleware
        page_type = request.meta.get('autoextract', {}).get('pageType', self.page_type)
        if not page_type or not isinstance(page_type, str):
            raise AutoExtractConfigError('Invalid pageType value: {}'.format(page_type))
        return page_type

    def _set_download_slot(self, request, meta):
        if self.slot_policy == SlotPolicy.PER_DOMAIN:
            # Group requests by domain to respect download
            # delays and concurrency options
            slot = self.crawler.engine.downloader._get_slot_key(request, None)
            meta['download_slot'] = slot
        elif self.slot_policy == SlotPolicy.SINGLE_SLOT:
            # Use a single slot for all AutoExtract requests
            meta['download_slot'] = '__AutoExtract__'
        # Else, use standard Scrapy concurrency setup

    def _get_meta_name(self, request, name):
        extra_data = None
        if request.meta['autoextract'].get(name):
            if not isinstance(request.meta['autoextract'][name], dict):
                raise AutoExtractError('Invalid type for "{}" meta'.format(name))
            extra_data = request.meta['autoextract'][name]
        return extra_data

    def inc_metric(self, key, **kwargs):
        self.crawler.stats.inc_value(key, **kwargs)

    def set_metric(self, key, value):
        self.crawler.stats.set_value(key, value)

    def _log_debug_error(self, response, body):
        if len(body) > MAX_ERROR_BODY:
            half_body = MAX_ERROR_BODY // 2
            body = body[:half_body] + ' [...] ' + body[-half_body:]
        logger.debug('AutoExtract response status=%i  headers=%s  content=%s', response.status,
                     response.headers.to_unicode_dict(), body)

    def autoextract_latency_stats(self):
        self.set_metric('autoextract/response_count', self.nr_resp)
        self.set_metric('autoextract/response_avg_latency', self.avg_latency)
        self.set_metric('autoextract/response_max_latency', self.max_latency)
