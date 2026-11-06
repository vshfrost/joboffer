"""SignupRequestRepository на Postgres. Один запит на email: унікальність гарантує constraint."""

from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from domain.identity.email import Email
from domain.identity.ids import SignupRequestId
from domain.identity.password import PasswordHash
from domain.identity.session import TokenDigest
from domain.identity.signup_request import SignupRequest
from domain.identity.user import DisplayName
from infrastructure.db.identity.tables import SignupRequestRow


def _to_domain(row: SignupRequestRow) -> SignupRequest:
    return SignupRequest(
        id=SignupRequestId(row.id),
        email=Email(row.email),
        password_hash=PasswordHash(row.password_hash),
        display_name=DisplayName(row.display_name),
        invite_digest=TokenDigest(row.invite_digest),
        terms_version=row.terms_version,
        code_digest=row.code_digest,
        failed_attempts=row.failed_attempts,
        created_at=row.created_at,
        sent_at=row.sent_at,
        expires_at=row.expires_at,
    )


def _values(request: SignupRequest) -> dict[str, object]:
    return {
        "id": request.id.value,
        "email": request.email.value,
        "password_hash": request.password_hash.value,
        "display_name": request.display_name.value,
        "invite_digest": request.invite_digest.value,
        "terms_version": request.terms_version,
        "code_digest": request.code_digest,
        "failed_attempts": request.failed_attempts,
        "created_at": request.created_at,
        "sent_at": request.sent_at,
        "expires_at": request.expires_at,
    }


class PostgresSignupRequests:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, request: SignupRequest) -> None:
        # Повторна реєстрація тієї самої адреси замінює запит: один UPSERT, без гонки між DELETE і INSERT.
        values = _values(request)
        await self._session.execute(
            insert(SignupRequestRow)
            .values(**values)
            .on_conflict_do_update(index_elements=["email"], set_=values)
        )

    async def get(self, request_id: SignupRequestId) -> SignupRequest | None:
        # FOR UPDATE: паралельні спроби коду йдуть по черзі й не обходять ліміт у 5 спроб.
        row = await self._session.scalar(
            select(SignupRequestRow)
            .where(SignupRequestRow.id == request_id.value)
            .with_for_update()
        )
        return None if row is None else _to_domain(row)

    async def save(self, request: SignupRequest) -> None:
        await self._session.execute(
            update(SignupRequestRow)
            .where(SignupRequestRow.id == request.id.value)
            .values(**_values(request))
        )

    async def delete(self, request_id: SignupRequestId) -> None:
        await self._session.execute(
            delete(SignupRequestRow).where(SignupRequestRow.id == request_id.value)
        )

    async def purge_expired(self, now: datetime) -> None:
        await self._session.execute(
            delete(SignupRequestRow).where(SignupRequestRow.expires_at <= now)
        )
