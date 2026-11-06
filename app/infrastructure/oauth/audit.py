"""Журнал аудиту OAuth у стандартний logging: рядок `OAUTH_AUDIT …` без секретів."""

import logging
from urllib.parse import urlsplit

from application.ports.audit import AuditEvent

audit_log = logging.getLogger("joboffer.oauth.audit")


class LoggingAuditLog:
    def record(self, event: AuditEvent) -> None:
        # Від адреси лишається хост і шлях: query може нести state клієнта.
        target = urlsplit(event.redirect or "")
        audit_log.info(
            "OAUTH_AUDIT event=%s user=%s grant=%s client=%r client_id=%s redirect=%s",
            event.name,
            event.user_id if event.user_id is not None else "-",
            event.grant_id if event.grant_id is not None else "-",
            (event.client_name or "-")[:40],
            (event.client_id or "-")[:8],
            f"{target.hostname}{target.path}" if target.hostname else "-",
        )
