"""Спільні fixtures для core-наборів (unit, acceptance). Лише stdlib + pytest + hypothesis + anyio."""

from collections.abc import Iterator

import pytest
from anyio.from_thread import BlockingPortal, start_blocking_portal
from hypothesis import given, settings, target
from hypothesis import strategies as st

from tests.support.clock import FakeClock
from tests.support.ids import SequentialIds
from tests.support.isolation import deny_io

# Hypothesis без бази прикладів на диску й з відтворюваним порядком.
settings.register_profile("core", database=None, derandomize=True)
settings.load_profile("core")


@pytest.fixture(scope="session", autouse=True)
def _warm_up_hypothesis() -> None:
    """Hypothesis лениво імпортує модулі (читає .pyc) при першій генерації.

    Робимо це до заборони IO: session-фікстури стартують раніше за `_core_denies_io`.
    """

    @settings(database=None)
    @given(st.uuids(), st.text(), st.integers())
    def probe(_uuid: object, text: str, _number: int) -> None:
        target(float(len(text)))  # будить фазу оптимізації, яка теж імпортує модулі

    probe()


@pytest.fixture(scope="session", autouse=True)
def _warm_up_anyio() -> None:
    """anyio лениво імпортує backend при першому старті порталу — теж до заборони IO."""

    async def noop() -> None:
        return None

    with start_blocking_portal() as warm:
        warm.call(noop)


@pytest.fixture(autouse=True)
def _core_denies_io(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    with deny_io(monkeypatch):
        yield


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def ids() -> SequentialIds:
    return SequentialIds()


@pytest.fixture
def portal() -> Iterator[BlockingPortal]:
    """Один event loop на тест. Кроки pytest-bdd синхронні: async use case — через `portal.call(...)`."""
    with start_blocking_portal() as running:
        yield running
