"""CLI `python -m bootstrap.create_user`: пароль лише з інтерактивного запиту, ніколи з аргументів чи виводу."""

from collections.abc import Callable

import pytest
from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from application.contracts.identity import Authenticate
from application.identity.use_cases import IdentityUseCases
from bootstrap.create_user import main
from domain.identity.errors import InvalidCredentials
from infrastructure.db.unit_of_work import unit_of_work_factory
from infrastructure.security.passwords import Argon2PasswordHasher
from infrastructure.system import RandomIds, SystemClock

PASSWORD = "correct horse battery"


@pytest.fixture
def prompts(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """Підміняє getpass: наступні виклики повертають відповіді по черзі."""

    def feed(*answers: str) -> None:
        queue = iter(answers)
        monkeypatch.setattr("getpass.getpass", lambda _prompt="": next(queue))

    return feed


@pytest.fixture(autouse=True)
def _environment(
    portal: BlockingPortal,
    engine: AsyncEngine,
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def clean() -> None:
        async with engine.begin() as conn:
            await conn.execute(text("TRUNCATE users CASCADE"))

    portal.call(clean)
    monkeypatch.setenv("JOBOFFER_DATABASE_URL", database_url)


@pytest.fixture
def identity(engine: AsyncEngine) -> IdentityUseCases:
    return IdentityUseCases(
        unit_of_work_factory(engine), SystemClock(), RandomIds(), Argon2PasswordHasher()
    )


def can_log_in(
    portal: BlockingPortal, identity: IdentityUseCases, email: str, password: str
) -> bool:
    try:
        portal.call(identity.authenticate, Authenticate(email=email, password=password))
    except InvalidCredentials:
        return False
    return True


def test_creates_a_user_who_can_log_in(
    portal: BlockingPortal,
    identity: IdentityUseCases,
    prompts: Callable[..., None],
    capsys: pytest.CaptureFixture[str],
) -> None:
    prompts(PASSWORD, PASSWORD)
    assert main(["--email", "Taras@Example.com", "--name", "Богдан"]) == 0
    assert can_log_in(portal, identity, "taras@example.com", PASSWORD)
    captured = capsys.readouterr()
    assert PASSWORD not in captured.out + captured.err
    assert "taras@example.com" in captured.out


def test_mismatched_confirmation_creates_nobody(
    portal: BlockingPortal,
    identity: IdentityUseCases,
    prompts: Callable[..., None],
    capsys: pytest.CaptureFixture[str],
) -> None:
    prompts(PASSWORD, "something else entirely")
    assert main(["--email", "taras@example.com", "--name", "Богдан"]) == 1
    assert "не збігаються" in capsys.readouterr().err
    assert not can_log_in(portal, identity, "taras@example.com", PASSWORD)


def test_short_password_is_reported_and_not_echoed(
    prompts: Callable[..., None], capsys: pytest.CaptureFixture[str]
) -> None:
    prompts("short", "short")
    assert main(["--email", "taras@example.com", "--name", "Богдан"]) == 1
    captured = capsys.readouterr()
    assert "12" in captured.err
    assert "short" not in captured.out + captured.err.replace("short.", "")


def test_duplicate_email_is_reported(
    prompts: Callable[..., None], capsys: pytest.CaptureFixture[str]
) -> None:
    prompts(PASSWORD, PASSWORD, PASSWORD, PASSWORD)
    assert main(["--email", "taras@example.com", "--name", "Богдан"]) == 0
    assert main(["--email", "TARAS@example.com", "--name", "Двійник"]) == 1
    assert "уже існує" in capsys.readouterr().err


def test_password_is_not_accepted_as_an_argument() -> None:
    with pytest.raises(SystemExit) as caught:
        main(["--email", "taras@example.com", "--name", "Богдан", "--password", "x"])
    assert caught.value.code == 2
