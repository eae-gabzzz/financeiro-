"""Firestore em memória para testes (nunca toca em dados reais)."""
import copy
import uuid
from datetime import datetime, timezone

from google.api_core.exceptions import AlreadyExists, NotFound
from google.cloud.firestore import SERVER_TIMESTAMP


def _resolve(data):
    return {k: (datetime.now(timezone.utc) if v is SERVER_TIMESTAMP else v) for k, v in data.items()}


class Snap:
    def __init__(self, id, data):
        self.id, self._data = id, data

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return copy.deepcopy(self._data) if self._data is not None else None


class Doc:
    def __init__(self, store, name, id):
        self.store, self.name, self.id = store, name, id

    def _col(self):
        return self.store.setdefault(self.name, {})

    def get(self):
        return Snap(self.id, self._col().get(self.id))

    def set(self, data):
        self._col()[self.id] = _resolve(copy.deepcopy(data))

    def create(self, data):
        if self.id in self._col():
            raise AlreadyExists("já existe")
        self.set(data)

    def update(self, data):
        if self.id not in self._col():
            raise NotFound("não existe")
        self._col()[self.id].update(_resolve(copy.deepcopy(data)))

    def delete(self):
        self._col().pop(self.id, None)


class Query:
    def __init__(self, store, name, filters=()):
        self.store, self.name, self.filters = store, name, tuple(filters)

    def where(self, field=None, op=None, value=None, *, filter=None):
        if filter is not None:
            field, op, value = filter.field_path, filter.op_string, filter.value
        assert op == "=="
        return Query(self.store, self.name, self.filters + ((field, value),))

    def stream(self):
        for id, data in list(self.store.get(self.name, {}).items()):
            if all(data.get(f) == v for f, v in self.filters):
                yield Snap(id, copy.deepcopy(data))


class Collection(Query):
    def document(self, id=None):
        return Doc(self.store, self.name, id or uuid.uuid4().hex)


class FakeFirestore:
    def __init__(self, store=None):
        self.store = {} if store is None else store

    def collection(self, name):
        return Collection(self.store, name)


class BrokenFirestore:
    """Simula falha de gravação do Firestore."""
    def collection(self, name):
        raise RuntimeError("Firestore indisponível")
