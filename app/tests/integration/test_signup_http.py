"""POST /auth/signup → verify → resend наскрізь: застосунок на справжньому Postgres, фейковий Gmail і ALTCHA."""

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from anyio.from_thread import BlockingPortal
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from application.contracts.legal import LegalDoc
from bootstrap.api import container_of, create_app
from bootstrap.settings import Settings
from infrastructure.http.auth import csrf_token_for
from tests.support.altcha import TEST_KEY, solve_challenge
from tests.support.fake_mailbox import FakeMailbox

COOKIE = "__Host-joboffer_session"
PASSWORD = "Correct-Horse-9"
SIGNUP = "/auth/signup"
VERIFY = "/auth/signup/verify"
RESEND = "/auth/signup/resend"
MAILROOM = "mailroom@example.com"

type ClientFactory = Callable[..., TestClient]


@pytest.fixture
def mailbox() -> FakeMailbox:
    return FakeMailbox()


@pytest.fixture
def make_client(
    portal: BlockingPortal,
    engine: AsyncEngine,
    database_url: str,
    mailbox: FakeMailbox,
) -> Iterator[ClientFactory]:
    async def clean() -> None:
        async with engine.begin() as conn:
            for table in (
                "users CASCADE",
                "signup_requests",
                "signup_invites",
                "login_failures",
                "signup_limits",
                "altcha_solutions",
                "mail_sends",
            ):
                await conn.execute(text(f"TRUNCATE {table}"))

    portal.call(clean)
    opened: list[TestClient] = []

    def factory(*, mail: bool = True, **overrides: Any) -> TestClient:
        mail_settings: dict[str, Any] = (
            {
                "mail_address": MAILROOM,
                "gmail_client_id": "id",
                "gmail_client_secret": SecretStr("client-secret"),
                "gmail_send_refresh_token": SecretStr("send-refresh"),
            }
            if mail
            else {}
        )
        fields: dict[str, Any] = {
            "environment": "test",
            "database_url": database_url,
            "altcha_hmac_key": SecretStr(TEST_KEY),
            "altcha_maxnumber": 500,
            "signup_mode": "invite",
            **mail_settings,
            **overrides,
        }
        settings = Settings(**fields)
        client = TestClient(
            create_app(settings, mail_transport=mailbox.transport()),
            base_url="https://testserver",
        )
        client.__enter__()
        opened.append(client)
        return client

    yield factory
    for client in opened:
        client.__exit__(None, None, None)


@pytest.fixture
def client(make_client: ClientFactory) -> TestClient:
    return make_client()


def issue_invite(client: TestClient) -> str:
    invites = container_of(client.app).invites  # type: ignore[arg-type]
    assert client.portal is not None
    return client.portal.call(invites.create).token


def terms_version(client: TestClient) -> str:
    legal = container_of(client.app).legal  # type: ignore[arg-type]
    return legal.get(LegalDoc.TERMS).version


def solved(client: TestClient) -> str:
    return solve_challenge(**client.get("/auth/challenge").json())


def signup_body(client: TestClient, invite: str, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "email": "taras@example.com",
        "password": PASSWORD,
        "invite": invite,
        "terms_version": terms_version(client),
        "altcha": solved(client),
    }
    body.update(overrides)
    return body


def sql(
    portal: BlockingPortal, engine: AsyncEngine, statement: str, **params: Any
) -> list[Any]:
    async def run() -> list[Any]:
        async with engine.begin() as conn:
            result = await conn.execute(text(statement), params)
            return list(result.all()) if result.returns_rows else []

    return portal.call(run)


def register(client: TestClient, invite: str, **overrides: Any) -> str:
    response = client.post(SIGNUP, json=signup_body(client, invite, **overrides))
    assert response.status_code == 202, response.text
    return str(response.json()["signup_id"])


def test_signup_is_202_with_a_signup_id_and_mails_the_code(
    client: TestClient, mailbox: FakeMailbox
) -> None:
    response = client.post(SIGNUP, json=signup_body(client, issue_invite(client)))

    assert response.status_code == 202
    assert list(response.json()) == ["signup_id"]
    assert response.headers["cache-control"] == "no-store"
    assert mailbox.to() == ["taras@example.com"]
    assert len(mailbox.codes()) == 1


def test_verify_with_the_right_code_is_201_with_a_session_cookie_and_csrf_token(
    client: TestClient, mailbox: FakeMailbox
) -> None:
    signup_id = register(client, issue_invite(client), display_name="Богдан")

    response = client.post(
        VERIFY, json={"signup_id": signup_id, "code": mailbox.codes()[-1]}
    )

    assert response.status_code == 201
    body = response.json()
    assert (body["user"]["email"], body["user"]["display_name"]) == (
        "taras@example.com",
        "Богдан",
    )
    set_cookie = response.headers["set-cookie"]
    assert set_cookie.startswith(f"{COOKIE}=")
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    assert "Path=/" in set_cookie
    assert body["csrf_token"] == csrf_token_for(client.cookies[COOKIE])
    assert response.headers["cache-control"] == "no-store"


def test_the_session_from_verify_works_for_me(
    client: TestClient, mailbox: FakeMailbox
) -> None:
    signup_id = register(client, issue_invite(client))
    client.post(VERIFY, json={"signup_id": signup_id, "code": mailbox.codes()[-1]})

    response = client.get("/auth/me")

    assert response.status_code == 200
    assert response.json()["user"]["email"] == "taras@example.com"


def test_the_new_user_can_log_in_with_the_password(
    client: TestClient, mailbox: FakeMailbox
) -> None:
    signup_id = register(client, issue_invite(client))
    client.post(VERIFY, json={"signup_id": signup_id, "code": mailbox.codes()[-1]})
    client.cookies.clear()

    response = client.post(
        "/auth/login", json={"email": "taras@example.com", "password": PASSWORD}
    )

    assert response.status_code == 200


def test_a_wrong_code_is_422_with_the_attempts_left(
    client: TestClient, mailbox: FakeMailbox
) -> None:
    signup_id = register(client, issue_invite(client))

    response = client.post(VERIFY, json={"signup_id": signup_id, "code": "000000"})

    assert response.status_code == 422
    body = response.json()
    assert (body["code"], body["attempts_left"]) == ("code_incorrect", 4)
    assert COOKIE not in client.cookies


def test_the_fifth_wrong_code_is_signup_expired(
    client: TestClient, mailbox: FakeMailbox
) -> None:
    signup_id = register(client, issue_invite(client))

    responses = [
        client.post(VERIFY, json={"signup_id": signup_id, "code": "000000"})
        for _ in range(5)
    ]
    right = client.post(
        VERIFY, json={"signup_id": signup_id, "code": mailbox.codes()[-1]}
    )

    assert [r.status_code for r in responses] == [422] * 5
    assert [r.json()["code"] for r in responses] == [
        "code_incorrect",
        "code_incorrect",
        "code_incorrect",
        "code_incorrect",
        "signup_expired",
    ]
    assert (right.status_code, right.json()["code"]) == (422, "signup_expired")


def test_an_expired_code_is_signup_expired(
    client: TestClient,
    mailbox: FakeMailbox,
    portal: BlockingPortal,
    engine: AsyncEngine,
) -> None:
    signup_id = register(client, issue_invite(client))
    sql(
        portal,
        engine,
        "UPDATE signup_requests SET expires_at = now() - interval '1 second'",
    )

    response = client.post(
        VERIFY, json={"signup_id": signup_id, "code": mailbox.codes()[-1]}
    )

    assert (response.status_code, response.json()["code"]) == (422, "signup_expired")


@pytest.mark.parametrize(
    "signup_id", ["00000000-0000-0000-0000-0000000000ff", "not-a-uuid", ""]
)
def test_an_unknown_signup_id_is_signup_expired(
    client: TestClient, signup_id: str
) -> None:
    response = client.post(VERIFY, json={"signup_id": signup_id, "code": "123456"})

    assert (response.status_code, response.json()["code"]) == (422, "signup_expired")


def test_resend_right_after_signup_is_429_with_retry_after(client: TestClient) -> None:
    signup_id = register(client, issue_invite(client))

    response = client.post(RESEND, json={"signup_id": signup_id})

    assert (response.status_code, response.json()["code"]) == (429, "too_many_attempts")
    assert 55 <= int(response.headers["retry-after"]) <= 60


def test_resend_after_60_seconds_is_202_and_mails_a_new_code(
    client: TestClient,
    mailbox: FakeMailbox,
    portal: BlockingPortal,
    engine: AsyncEngine,
) -> None:
    signup_id = register(client, issue_invite(client))
    sql(
        portal,
        engine,
        "UPDATE signup_requests SET sent_at = sent_at - interval '61 seconds'",
    )

    response = client.post(RESEND, json={"signup_id": signup_id})

    assert response.status_code == 202
    assert response.json() == {"signup_id": signup_id}
    assert len(mailbox.codes()) == 2
    assert mailbox.codes()[0] != mailbox.codes()[1]


def test_resend_for_an_unknown_request_is_signup_expired(client: TestClient) -> None:
    response = client.post(
        RESEND, json={"signup_id": "00000000-0000-0000-0000-0000000000ff"}
    )

    assert (response.status_code, response.json()["code"]) == (422, "signup_expired")


def test_the_sixth_registration_from_one_client_in_an_hour_is_429(
    client: TestClient,
) -> None:
    invite = issue_invite(client)
    for number in range(5):
        register(client, invite, email=f"user{number}@example.com")

    response = client.post(
        SIGNUP, json=signup_body(client, invite, email="extra@example.com")
    )

    assert (response.status_code, response.json()["code"]) == (429, "too_many_attempts")
    assert 3590 <= int(response.headers["retry-after"]) <= 3600


def test_a_closed_signup_is_404_signup_closed(make_client: ClientFactory) -> None:
    client = make_client(signup_mode="closed")

    response = client.post(SIGNUP, json=signup_body(client, "any-invite"))

    assert (response.status_code, response.json()["code"]) == (404, "signup_closed")


def test_without_mail_settings_signup_is_503_registration_closed(
    make_client: ClientFactory,
) -> None:
    client = make_client(mail=False)

    response = client.post(SIGNUP, json=signup_body(client, issue_invite(client)))

    assert (response.status_code, response.json()["code"]) == (
        503,
        "registration_closed",
    )


def test_a_filled_honeypot_is_202_and_nothing_happens(
    client: TestClient,
    mailbox: FakeMailbox,
    portal: BlockingPortal,
    engine: AsyncEngine,
) -> None:
    response = client.post(
        SIGNUP,
        json=signup_body(
            client, issue_invite(client), website="https://spam.example.com"
        ),
    )

    assert response.status_code == 202
    assert list(response.json()) == ["signup_id"]
    assert mailbox.messages == []
    assert sql(portal, engine, "SELECT 1 FROM signup_requests") == []


def test_a_mail_failure_is_503_and_the_invite_stays_valid(
    client: TestClient, mailbox: FakeMailbox
) -> None:
    invite = issue_invite(client)
    mailbox.send_status = 500

    response = client.post(SIGNUP, json=signup_body(client, invite))

    assert (response.status_code, response.json()["code"]) == (503, "mail_unavailable")
    assert (
        client.get("/auth/signup/invite", params={"invite": invite}).status_code == 200
    )


def test_a_wrong_altcha_is_422_challenge_failed(client: TestClient) -> None:
    response = client.post(
        SIGNUP,
        json=signup_body(client, issue_invite(client), altcha="not-a-solution"),
    )

    assert (response.status_code, response.json()["code"]) == (422, "challenge_failed")


def test_an_unknown_invite_is_404_invite_invalid(client: TestClient) -> None:
    response = client.post(SIGNUP, json=signup_body(client, "no-such-invite"))

    assert (response.status_code, response.json()["code"]) == (404, "invite_invalid")


def test_a_password_without_a_digit_is_422_password_weak_on_the_password_field(
    client: TestClient,
) -> None:
    response = client.post(
        SIGNUP,
        json=signup_body(client, issue_invite(client), password="Correct-Horse-Bat"),
    )

    assert (response.status_code, response.json()["code"]) == (422, "password_weak")
    body = response.json()
    assert [e["field"] for e in body["field_errors"]] == ["password"]
    assert "цифру" in body["message"]


def test_a_short_password_is_422_on_the_password_field(client: TestClient) -> None:
    response = client.post(
        SIGNUP, json=signup_body(client, issue_invite(client), password="Abcde1!")
    )

    assert (response.status_code, response.json()["code"]) == (422, "invalid_value")
    assert [e["field"] for e in response.json()["field_errors"]] == ["password"]


def test_an_8_character_password_with_all_classes_is_accepted(
    client: TestClient,
) -> None:
    response = client.post(
        SIGNUP, json=signup_body(client, issue_invite(client), password="Abcdef1!")
    )

    assert response.status_code == 202


@pytest.mark.parametrize("terms", [None, "", "2020-01-01"])
def test_missing_or_outdated_terms_are_422_on_the_terms_field(
    client: TestClient, terms: str | None
) -> None:
    body = signup_body(client, issue_invite(client))
    if terms is None:
        del body["terms_version"]
    else:
        body["terms_version"] = terms

    response = client.post(SIGNUP, json=body)

    assert response.status_code == 422
    assert [e["field"] for e in response.json()["field_errors"]] == ["terms_version"]


def test_a_body_without_an_email_is_422_invalid_request(client: TestClient) -> None:
    body = signup_body(client, issue_invite(client))
    del body["email"]

    response = client.post(SIGNUP, json=body)

    assert (response.status_code, response.json()["code"]) == (422, "invalid_request")


def test_an_existing_email_gets_the_same_202_and_the_account_exists_mail(
    client: TestClient,
    mailbox: FakeMailbox,
    portal: BlockingPortal,
    engine: AsyncEngine,
) -> None:
    invite = issue_invite(client)
    first = register(client, invite)
    client.post(VERIFY, json={"signup_id": first, "code": mailbox.codes()[-1]})
    invite = issue_invite(client)
    mailbox.messages.clear()

    response = client.post(SIGNUP, json=signup_body(client, invite))

    assert response.status_code == 202
    assert list(response.json()) == ["signup_id"]
    assert mailbox.to() == ["taras@example.com"]
    assert mailbox.codes() == []
    assert "вже є акаунт" in mailbox.messages[0].get_content()
    assert sql(portal, engine, "SELECT 1 FROM signup_requests") == []
    assert (
        client.get("/auth/signup/invite", params={"invite": invite}).status_code == 200
    )


def test_the_invite_redeemed_while_waiting_for_the_code_is_409(
    client: TestClient, mailbox: FakeMailbox
) -> None:
    invite = issue_invite(client)
    signup_id = register(client, invite)
    invites = container_of(client.app).invites  # type: ignore[arg-type]
    assert client.portal is not None
    client.portal.call(invites.redeem, invite)

    response = client.post(
        VERIFY, json={"signup_id": signup_id, "code": mailbox.codes()[-1]}
    )

    assert (response.status_code, response.json()["code"]) == (409, "invite_used")
    assert COOKIE not in client.cookies
