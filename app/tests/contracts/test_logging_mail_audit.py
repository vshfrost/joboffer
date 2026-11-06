"""Аудит відправки: один рядок `MAIL_AUDIT send event=…` у logger `joboffer.mail`, без адрес і кодів."""

import logging

import pytest

from infrastructure.gmail.audit import LoggingMailAudit

AUDIT_LOGGER = "joboffer.mail"


@pytest.fixture(autouse=True)
def _audit_logger_enabled() -> None:
    # import-linter (tests/architecture) перенастроює logging і вимикає вже створені logger-и.
    logging.getLogger(AUDIT_LOGGER).disabled = False


def test_event_is_logged_as_one_audit_line(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger=AUDIT_LOGGER):
        LoggingMailAudit().record("mail_sent")

    assert [record.getMessage() for record in caplog.records] == [
        "MAIL_AUDIT send event=mail_sent"
    ]
