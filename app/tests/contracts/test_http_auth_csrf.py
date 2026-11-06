"""CSRF-заголовок приходить від клієнта: будь-який вміст, зокрема не-ASCII, — це відмова 403, а не збій 500."""

from typing import cast

import pytest
from starlette.requests import Request

from application.identity.sessions import SessionUseCases
from infrastructure.http.auth import CookieConfig, CsrfFailed, HttpAuth, csrf_token_for

SESSION_TOKEN = "session-token-of-the-test"


def auth() -> HttpAuth:
    # `require_csrf` сховища сесій не торкається.
    return HttpAuth(
        cast(SessionUseCases, None),
        CookieConfig(name="session", secure=True, max_age=60),
        trusted_proxies=0,
    )


def request_with_csrf_header(value: bytes) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "headers": [(b"x-csrf-token", value)],
        }
    )


def test_the_token_derived_from_the_session_is_accepted() -> None:
    header = csrf_token_for(SESSION_TOKEN).encode()

    auth().require_csrf(request_with_csrf_header(header), SESSION_TOKEN)


@pytest.mark.parametrize("value", [b"", b"wrong", "é".encode("latin-1"), b"\xff\xfe"])
def test_a_wrong_or_non_ascii_token_is_a_csrf_failure(value: bytes) -> None:
    with pytest.raises(CsrfFailed):
        auth().require_csrf(request_with_csrf_header(value), SESSION_TOKEN)
