"""Запити на авторизацію в очікуванні входу: словник у памʼяті процесу з обмеженим розміром."""

from domain.oauth.entities import PendingAuthorization

MAX_PENDING = 1000


class InMemoryPendingAuthorizations:
    def __init__(self, max_size: int = MAX_PENDING) -> None:
        self._max_size = max_size
        self._items: dict[str, PendingAuthorization] = {}

    def put(self, rid: str, pending: PendingAuthorization) -> None:
        self._items[rid] = pending
        # /authorize відкритий без входу: без обмеження його можна використати, щоб роздути памʼять.
        while len(self._items) > self._max_size:
            del self._items[next(iter(self._items))]

    def get(self, rid: str) -> PendingAuthorization | None:
        return self._items.get(rid)

    def take(self, rid: str) -> PendingAuthorization | None:
        return self._items.pop(rid, None)
