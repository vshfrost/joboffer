"""Одноразове посилання на PDF документа: строк життя і кому воно відкриває файл.

Сам токен знає лише агент, що попросив посилання; у сховищі живе його sha256-дайджест
(`domain.identity.session.TokenDigest`). Час приходить явним значенням — домен не викликає now().
"""

from dataclasses import dataclass
from datetime import timedelta

from domain.identity.ids import UserId

DOWNLOAD_TTL = timedelta(minutes=10)


@dataclass(frozen=True, slots=True)
class DownloadGrant:
    """Кому й який документ відкрило використане посилання (`document_number` — номер у межах користувача)."""

    user_id: UserId
    document_number: int
