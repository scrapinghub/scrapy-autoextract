from autoextract.aio.errors import DomainOccupied


class QueryError(Exception):

    def __init__(self, query: dict, message: str):
        self.query = query
        self.message = message

    def __str__(self):
        return f"QueryError: message='{self.message}', query={self.query}"


def summarize_exception(exc):
    """
    Provides a text that represents the exception. To be used in stats, so
    produced text shouldn't be too diverse.
    """
    if isinstance(exc, QueryError):
        msg = exc.message
        if DomainOccupied.from_message(msg):
            # Removes variability from domain occupy messages
            msg = "domain occupied"
        msg = f"/query/{msg}"
    else:
        msg = f"/rest/{exc.__class__.__name__}"
    return msg
