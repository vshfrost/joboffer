"""Сутності OAuth: привʼязка коду та строк токена."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from domain.identity.ids import GrantId
from domain.identity.session import TokenDigest
from domain.oauth.entities import CodeBinding, StoredToken, TokenKind
from domain.shared.errors import InvalidValue

NOW = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
BINDING = CodeBinding(
    code_challenge="challenge",
    redirect_uri="https://claude.ai/api/mcp/auth_callback",
    redirect_uri_provided_explicitly=True,
)


def make(kind: TokenKind, code: CodeBinding | None) -> StoredToken:
    return StoredToken(
        digest=TokenDigest.from_token("secret"),
        kind=kind,
        grant_id=GrantId(UUID(int=1)),
        expires_at=NOW + timedelta(minutes=5),
        code=code,
    )


def test_code_exposes_its_binding() -> None:
    assert make(TokenKind.CODE, BINDING).binding == BINDING


@pytest.mark.parametrize("kind", [TokenKind.CODE, TokenKind.ACCESS, TokenKind.REFRESH])
def test_token_without_a_binding_has_none_to_expose(kind: TokenKind) -> None:
    with pytest.raises(InvalidValue):
        make(kind, None).binding  # noqa: B018 — перевіряємо виняток доступу до властивості


def test_token_expires_exactly_at_its_deadline() -> None:
    token = make(TokenKind.ACCESS, None)

    assert not token.is_expired(NOW + timedelta(minutes=5) - timedelta(seconds=1))
    assert token.is_expired(NOW + timedelta(minutes=5))
