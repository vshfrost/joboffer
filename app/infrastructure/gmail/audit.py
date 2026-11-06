"""Аудит відправки листів у logging: рядок `MAIL_AUDIT send event=…` без адрес і кодів."""

import logging

logger = logging.getLogger("joboffer.mail")


class LoggingMailAudit:
    def record(self, event: str) -> None:
        logger.info("MAIL_AUDIT send event=%s", event)
