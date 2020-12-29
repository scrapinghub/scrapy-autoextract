import json
from functools import wraps

from pytest_twisted import inlineCallbacks

from autoextract.aio import RequestError
from scrapy.statscollectors import StatsCollector
from scrapy.utils.defer import maybeDeferred_coro


def async_test(f):
    """Allow running asyncio tests on the presence of pytest_twisted"""
    @inlineCallbacks
    @wraps(f)
    def fn(*args, **kwargs):
        yield maybeDeferred_coro(f, *args, **kwargs)
    return fn


def request_error(payload) -> RequestError:
    if payload is not None and not isinstance(payload, bytes):
        payload = json.dumps(payload).encode("utf-8")
    return RequestError(
        request_info=None,
        history=None,
        status=404,
        message="",
        headers=None,
        response_content=payload,
    )


def assert_stats(stats: StatsCollector, expected: dict):
    for k, expected_val in expected.items():
        actual_val = stats.get_value(k, 0)
        assert actual_val == expected_val, \
            f"key: '{k}', value: {actual_val}, expected: {expected_val}"
