"""UserRepository на Postgres. Унікальність email гарантує constraint, а не попередня перевірка."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from domain.identity.email import Email
from domain.identity.errors import EmailTaken
from domain.identity.external_identity import ExternalIdentity
from domain.identity.ids import ExternalIdentityId, UserId
from domain.identity.password import PasswordHash
from domain.identity.user import DisplayName, User
from domain.shared.errors import NotFound
from infrastructure.db.identity.tables import UserIdentityRow, UserRow

_EMAIL_UNIQUE = "uq_users_email"


def _to_domain(row: UserRow) -> User:
    return User(
        id=UserId(row.id),
        email=Email(row.email),
        display_name=DisplayName(row.display_name),
        password_hash=None
        if row.password_hash is None
        else PasswordHash(row.password_hash),
        version=row.version,
        created_at=row.created_at,
        terms_version=row.terms_version,
        terms_accepted_at=row.terms_accepted_at,
    )


def _violates(error: IntegrityError, constraint: str) -> bool:
    diag = getattr(error.orig, "diag", None)
    return getattr(diag, "constraint_name", None) == constraint


class PostgresUsers:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: UserId) -> User:
        row = await self._session.get(UserRow, user_id.value)
        if row is None:
            raise NotFound(f"Користувача {user_id} нема")
        return _to_domain(row)

    async def find_by_email(self, email: Email) -> User | None:
        row = await self._session.scalar(
            select(UserRow).where(UserRow.email == email.value)
        )
        return None if row is None else _to_domain(row)

    async def add(self, user: User) -> None:
        self._session.add(
            UserRow(
                id=user.id.value,
                email=user.email.value,
                display_name=user.display_name.value,
                password_hash=None
                if user.password_hash is None
                else user.password_hash.value,
                version=user.version,
                created_at=user.created_at,
                terms_version=user.terms_version,
                terms_accepted_at=user.terms_accepted_at,
            )
        )
        try:
            await self._session.flush()
        except IntegrityError as error:
            if _violates(error, _EMAIL_UNIQUE):
                raise EmailTaken("Користувач з таким email уже існує") from error
            raise


class PostgresExternalIdentities:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find(self, provider: str, subject: str) -> ExternalIdentity | None:
        row = await self._session.scalar(
            select(UserIdentityRow).where(
                UserIdentityRow.provider == provider, UserIdentityRow.subject == subject
            )
        )
        if row is None:
            return None
        return ExternalIdentity(
            id=ExternalIdentityId(row.id),
            provider=row.provider,
            subject=row.subject,
            user_id=UserId(row.user_id),
            created_at=row.created_at,
        )

    async def add(self, identity: ExternalIdentity) -> None:
        self._session.add(
            UserIdentityRow(
                id=identity.id.value,
                provider=identity.provider,
                subject=identity.subject,
                user_id=identity.user_id.value,
                created_at=identity.created_at,
            )
        )
        await self._session.flush()
