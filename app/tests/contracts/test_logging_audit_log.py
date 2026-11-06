"""Адаптер аудиту: один рядок `OAUTH_AUDIT …` у logger `joboffer.oauth.audit`, без query адреси й повних id."""

import logging
from uuid import UUID

import pytest

from application.ports.audit import AuditEvent
from domain.identity.ids import GrantId, UserId
from infrastructure.oauth.audit import LoggingAuditLog

AUDIT_LOGGER = "joboffer.oauth.audit"
USER = UserId(UUID(int=100))
GRANT = GrantId(UUID(int=200))


@pytest.fixture(autouse=True)
def _audit_logger_enabled() -> None:
    # import-linter (tests/architecture) перенастроює logging і вимикає вже створені logger-и.
    logging.getLogger(AUDIT_LOGGER).disabled = False


def test_event_is_logged_as_one_audit_line(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger=AUDIT_LOGGER):
        LoggingAuditLog().record(
            AuditEvent(
                name="login",
                user_id=USER,
                grant_id=GRANT,
                client_id="6f1c0a52-0000-4000-8000-000000000001",
                client_name="Claude",
                redirect="https://claude.ai/api/mcp/auth_callback?state=abc#frag",
            )
        )

    assert [record.getMessage() for record in caplog.records] == [
        f"OAUTH_AUDIT event=login user={USER} grant={GRANT} client='Claude' "
        "client_id=6f1c0a52 redirect=claude.ai/api/mcp/auth_callback"
    ]


def test_missing_fields_are_dashes(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger=AUDIT_LOGGER):
        LoggingAuditLog().record(AuditEvent(name="register_rejected"))

    assert [record.getMessage() for record in caplog.records] == [
        "OAUTH_AUDIT event=register_rejected user=- grant=- client='-' client_id=- redirect=-"
    ]
