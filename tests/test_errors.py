import pytest

from scrapy_autoextract.errors import QueryError, summarize_exception


def test_query_error():
    exc = QueryError({"foo": "bar"}, "sample error")
    assert str(exc) == "QueryError: message='sample error', query={'foo': 'bar'}"


@pytest.mark.parametrize("exception, message", [
    (QueryError({}, "domain xyz is occupied, please retry in 2.2 seconds"),
     "/query/domain occupied"),
    (QueryError({}, "Another thing"),
     "/query/Another thing"),
    (ValueError("Value Error"), "/rest/ValueError"),
    (TypeError("Type Error"), "/rest/TypeError"),
])
def test_summarize_exception(exception, message):
    assert summarize_exception(exception) == message