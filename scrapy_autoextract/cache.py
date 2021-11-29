import abc
import gzip
import json
import pickle
import sqlite3

import sqlitedict
from autoextract.request import Request
from scrapinghub import NotFound, ScrapinghubClient


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
    def __init__(self, path, *, compressed=True):
        self.compressed = compressed
        tablename = 'responses_gzip' if compressed else 'responses'
        self.db = sqlitedict.SqliteDict(path,
                                        tablename=tablename,
                                        autocommit=True,
                                        encode=self.encode,
                                        decode=self.decode)

    def encode(self, obj):
        # based on sqlitedict.encode
        data = pickle.dumps(obj, pickle.HIGHEST_PROTOCOL)
        if self.compressed:
            data = gzip.compress(data, compresslevel=3)
        return sqlite3.Binary(data)

    def decode(self, obj):
        # based on sqlitedict.decode
        data = bytes(obj)
        if self.compressed:
            # gzip is slightly less efficient than raw zlib, but it does
            # e.g. crc checks out of box
            data = gzip.decompress(data)
        return pickle.loads(data)

    @classmethod
    def fingerprint(cls, request: Request) -> str:
        return json.dumps(
            request.as_dict(),
            ensure_ascii=False,
            sort_keys=True
        )

    def __str__(self):
        return f"AutoExtractCache <{self.db.filename} | " \
               f"compressed: {self.compressed} | " \
               f"{len(self.db)} records>"

    def __getitem__(self, fingerprint: str):
        return self.db[fingerprint]

    def __setitem__(self, fingerprint: str, value) -> None:
        self.db[fingerprint] = value

    def close(self):
        self.db.close()


class ScrapyCloudCollectionCache(_Cache):
    def __init__(self, project, collection):
        sc = ScrapinghubClient()
        self.collection = sc.get_project(project).collections.get_store(collection)

    @classmethod
    def fingerprint(cls, request: Request) -> str:
        return request.url

    def __getitem__(self, fingerprint: str):
        try:
            return self.collection.get(fingerprint)
        except NotFound:
            raise KeyError

    def __setitem__(self, fingerprint: str, value) -> None:
        self.collection.set(
            {'_key': fingerprint,
             'value': value}
        )

    def close(self):
        pass
