"""Вихідна пошта застосунку: лист від його скриньки одержувачу та два збої відправки.
Ліміт — захист від флуду: листів за ковзні 24 год не більше, ніж дозволено налаштуванням."""

from dataclasses import dataclass
from datetime import timedelta

MAIL_SEND_DAILY_LIMIT = 50
MAIL_SEND_WINDOW = timedelta(hours=24)


@dataclass(frozen=True, slots=True)
class OutgoingMail:
    """Лист text/plain. Відправник — скринька застосунку, її задає адаптер."""

    to: str
    subject: str
    body: str


class MailUnavailable(Exception):
    """Пошту не вдалося відправити (Google недоступний чи відмовив). Без відповіді Google."""


class MailQuotaExceeded(Exception):
    """Добовий ліміт листів вичерпано: запиту до Google не було."""
