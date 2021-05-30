import abc
import json

import sqlitedict
from autoextract.request import Request


class _Cache(abc.ABC):
    @classmethod
    @abc.abstractmethod
    def fingerprint(cls, request: Request) -> str:
        return ''

    @abc.abstractmethod
    def __getitem__(self, fingerprint: str):
        pass

    @abc.abstractmethod
    def __setitem__(self, fingerprint: str, value) -> None:
        pass

    def close(self):
        pass


class DummyCache(_Cache):
    @classmethod
    def fingerprint(cls, request: Request) -> str:
        return ''

    def __getitem__(self, fingerprint: str):
        raise KeyError()

    def __setitem__(self, fingerprint: str, value) -> None:
        pass

    def __str__(self):
        return "no cache"


class AutoExtractCache(_Cache):
    def __init__(self, path):
        self.db = sqlitedict.SqliteDict(path, autocommit=True)

    @classmethod
    def fingerprint(cls, request: Request) -> str:
        return json.dumps(
            request.as_dict(),
            ensure_ascii=False,
            sort_keys=True
        )

    def __str__(self):
        return f"AutoExtractCache <{self.db.filename} | {len(self.db)} records>"

    def __getitem__(self, fingerprint: str):
        return self.db[fingerprint]

    def __setitem__(self, fingerprint: str, value) -> None:
        self.db[fingerprint] = value

    def close(self):
        self.db.close()
