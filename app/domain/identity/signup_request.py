"""Запит на реєстрацію: дані чекають тут, доки email не підтверджено кодом з листа.

У домені й сховищі живуть лише хеш пароля й digest коду; сирий код знає тільки лист.
Час приходить явним значенням — домен не викликає now().
"""

import hashlib
import hmac
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Self

from domain.identity.email import Email
from domain.identity.ids import SignupRequestId
from domain.identity.password import PasswordHash
from domain.identity.session import TokenDigest
from domain.identity.user import DisplayName

CODE_LENGTH = 6
CODE_TTL = timedelta(minutes=15)
CODE_MAX_ATTEMPTS = 5
RESEND_INTERVAL = timedelta(seconds=60)
MAIL_MAX_PER_WINDOW = 5
MAIL_WINDOW = timedelta(hours=1)
SIGNUP_MAX_PER_WINDOW = 5
SIGNUP_WINDOW = timedelta(hours=1)


def code_digest(request_id: SignupRequestId, code: str) -> str:
    """sha256(id запиту + код): код не лежить ніде, а digest одного запиту не годиться для іншого."""
    return hashlib.sha256(f"{request_id.value}{code}".encode()).hexdigest()


@dataclass(frozen=True, slots=True, kw_only=True)
class SignupDraft:
    """Перевірені дані реєстрації, ще без ID, коду й часу."""

    email: Email
    password_hash: PasswordHash
    display_name: DisplayName
    invite_digest: TokenDigest
    terms_version: str


@dataclass(frozen=True, slots=True, kw_only=True)
class SignupRequest:
    id: SignupRequestId
    email: Email
    password_hash: PasswordHash
    display_name: DisplayName
    invite_digest: TokenDigest
    terms_version: str
    code_digest: str
    failed_attempts: int
    created_at: datetime
    sent_at: datetime
    expires_at: datetime

    @classmethod
    def issue(
        cls, draft: SignupDraft, *, id: SignupRequestId, code: str, now: datetime
    ) -> Self:
        return cls(
            id=id,
            email=draft.email,
            password_hash=draft.password_hash,
            display_name=draft.display_name,
            invite_digest=draft.invite_digest,
            terms_version=draft.terms_version,
            code_digest=code_digest(id, code),
            failed_attempts=0,
            created_at=now,
            sent_at=now,
            expires_at=now + CODE_TTL,
        )

    def with_new_code(self, code: str, now: datetime) -> Self:
        """Новий код (resend): спроби скидаються, строк і час відправки — від `now`."""
        return replace(
            self,
            code_digest=code_digest(self.id, code),
            failed_attempts=0,
            sent_at=now,
            expires_at=now + CODE_TTL,
        )

    def matches(self, code: str) -> bool:
        # Порівняння digest-ів у сталий час: відповідь не розкриває, скільки цифр збіглося.
        return hmac.compare_digest(self.code_digest, code_digest(self.id, code))

    def is_expired(self, now: datetime) -> bool:
        """Межа виключна: рівно в момент `expires_at` код уже не діє."""
        return now >= self.expires_at

    def failed(self) -> Self:
        """Ще одна невдала спроба коду."""
        return replace(self, failed_attempts=self.failed_attempts + 1)

    @property
    def attempts_left(self) -> int:
        return max(0, CODE_MAX_ATTEMPTS - self.failed_attempts)

    def resend_wait(self, now: datetime) -> timedelta:
        """Скільки ще чекати до повторної відправки; нуль — вже можна."""
        return max(timedelta(0), self.sent_at + RESEND_INTERVAL - now)
