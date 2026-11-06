"""In-memory сторінка джерел: каталог, запити «оновити зараз», вакансії й профілі в одній транзакції
поверх спільного сховища прогону. Зміни видно лише після `commit()`; вихід без нього їх відкидає."""

from tests.support.source_manage import InMemorySourceCatalog
from tests.support.source_runs import InMemorySourceRunUnitOfWork


class InMemorySourceOverviewUnitOfWork(InMemorySourceRunUnitOfWork):
    @property
    def source_catalog(self) -> InMemorySourceCatalog:
        if self._runs is None:
            raise RuntimeError("UnitOfWork використовується поза `async with`")
        return InMemorySourceCatalog(self._store.subscriptions, self._runs)
