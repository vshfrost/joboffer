"""Відповіді через HTTP наскрізь: сесія й CSRF, три черги з лічильниками, пошук і сторінки, деталі з подачами
власника, превʼю ефекту розбору, розбір з вебу (ті самі правила, що в MCP), 422 з текстом, чужі відповіді — 404.

Лист доходить так, як у житті: скринька → синк → зіставлення з подачею. DMARC none, щоб синк сам не
переводив подачу в replied: статус «applied» лишається вихідним для превʼю й розбору."""

from dataclasses import replace
from typing import Any

import httpx2
import pytest

from domain.mail.mail import IncomingMail
from tests.integration.test_mail_http import (
    MailClientFactory,
    MailSession,
    alice,
    bob,
    letter,
    mail_client,
    make_client,
)
from tests.integration.test_profile_http import SECTIONS
from tests.support.mail import auth_headers

__all__ = ["alice", "bob", "mail_client", "make_client"]

FORWARDED = (
    "---------- Forwarded message ---------\n"
    "From: Ana Recruiter <ana.recruiter@acme.example>\n"
    "Date: Mon, Oct 19, 2026 at 10:15 AM\n"
    "Subject: Your application to Acme\n"
    "To: Owner <owner@owner.example>\n\n"
    "Unfortunately, we are not moving forward."
)
BAD_TYPE = "Тип відповіді — один з: auto_confirmation, rejection, invitation, assignment, other."


def mail(
    gmail_id: str,
    to: str,
    *,
    sender: str = "hr@acme.example",
    dmarc: str = "none",
    **fields: Any,
) -> IncomingMail:
    """Лист компанії; за замовчуванням DMARC none (відправник не підтверджений)."""
    base = letter(gmail_id, to, sender=sender, **fields)
    return replace(base, auth_headers=auth_headers(sender, dmarc))


def apply(session: MailSession, title: str, company: str, domain: str) -> int:
    """Вакансія й подача на неї з доменом компанії; повертає номер вакансії."""
    posted = session.client.post(
        "/jobs",
        json={"text": f"{title} at {company}", "title": title, "company": company},
        headers=session.csrf,
    )
    job = int(posted.json()["job_id"])
    put = session.client.put(
        f"/jobs/{job}/application",
        json={"channel": "email", "company_domains": [domain]},
        headers=session.csrf,
    )
    assert put.status_code == 200, put.text
    return job


def board(
    session: MailSession, queue: str | None = None, /, **query: object
) -> httpx2.Response:
    params = dict(query)
    if queue is not None:
        params["queue"] = queue
    return session.client.get("/replies", params=params)  # type: ignore[arg-type]


def subjects(
    session: MailSession, queue: str | None = None, /, **query: object
) -> list[str]:
    return [
        i["untrusted_subject"] for i in board(session, queue, **query).json()["items"]
    ]


def reply_id(session: MailSession, queue: str, subject: str) -> int:
    found = [
        i["id"]
        for i in board(session, queue, per_page=100).json()["items"]
        if i["untrusted_subject"] == subject
    ]
    assert len(found) == 1, (queue, subject, found)
    return int(found[0])


def review(
    session: MailSession, reply: int, kind: str, job_id: int | None = None
) -> httpx2.Response:
    return session.client.post(
        f"/replies/{reply}/review",
        json={"type": kind, "job_id": job_id},
        headers=session.csrf,
    )


def preview(
    session: MailSession, reply: int, kind: str, job_id: int | None = None
) -> httpx2.Response:
    params: dict[str, object] = {"type": kind}
    if job_id is not None:
        params["job_id"] = job_id
    return session.client.get(f"/replies/{reply}/preview", params=params)  # type: ignore[arg-type]


def status_of(session: MailSession, job: int) -> str:
    return str(session.client.get(f"/jobs/{job}/application").json()["status"])


@pytest.fixture
def acme(alice: MailSession) -> MailSession:
    """Алісa подалась на Backend (Acme) і Platform (Zeta Labs); три листи: два від Acme, один нічий."""
    apply(alice, "Backend", "Acme", "acme.example")
    apply(alice, "Platform", "Zeta Labs", "zl.example")
    to = alice.address()
    alice.deliver(
        mail("m1", to, subject="Acme call", hours_ago=3),
        mail("m2", to, subject="Acme again", text="See you soon", hours_ago=2),
        mail("m3", to, sender="hr@nowhere.example", subject="Who are we", hours_ago=1),
    )
    return alice


def test_every_route_requires_a_session(mail_client: MailClientFactory) -> None:
    client = mail_client()
    for method, path in (
        ("GET", "/replies"),
        ("GET", "/replies/1"),
        ("GET", "/replies/1/preview?type=other"),
        ("POST", "/replies/1/review"),
    ):
        response = client.request(method, path)
        assert (response.status_code, response.json()["code"]) == (
            401,
            "not_authenticated",
        ), (method, path)


def test_review_requires_the_csrf_token(acme: MailSession) -> None:
    target = reply_id(acme, "matched", "Acme call")

    response = acme.client.post(
        f"/replies/{target}/review", json={"type": "rejection", "job_id": 1}
    )

    assert (response.status_code, response.json()["code"]) == (403, "csrf_failed")
    assert status_of(acme, 1) == "applied"
    assert subjects(acme, "reviewed") == []


def test_the_default_queue_is_to_review_newest_first_with_all_three_counters(
    acme: MailSession,
) -> None:
    response = board(acme)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["queue"] == "matched"
    assert [i["untrusted_subject"] for i in body["items"]] == [
        "Acme again",
        "Acme call",
    ]
    assert body["counts"] == {"matched": 2, "unmatched": 1, "reviewed": 0}
    assert body["page"]["total"] == 2


def test_each_queue_has_its_own_replies(acme: MailSession) -> None:
    assert subjects(acme, "matched") == ["Acme again", "Acme call"]
    assert subjects(acme, "unmatched") == ["Who are we"]
    assert subjects(acme, "reviewed") == []
    assert board(acme, "unmatched").json()["counts"] == {
        "matched": 2,
        "unmatched": 1,
        "reviewed": 0,
    }


def test_a_row_has_untrusted_fields_the_match_and_no_text(acme: MailSession) -> None:
    assert subjects(acme, "matched") == ["Acme again", "Acme call"]
    row = board(acme, "matched").json()["items"][1]

    assert row["untrusted_from_address"] == "hr@acme.example"
    assert (row["untrusted_from_name"], row["untrusted_subject"]) == (
        "María",
        "Acme call",
    )
    assert row["sender_auth"] == "unknown"
    assert row["job"] == {
        "job_id": 1,
        "title": "Backend",
        "company": "Acme",
        "status": "applied",
    }
    assert (row["confidence"], row["matched_by"]) == ("high", "domain")
    assert (row["suggested_type"], row["type"], row["reviewed_at"]) == (
        "invitation",
        None,
        None,
    )
    assert row["manual_forward"] is None
    assert "untrusted_text" not in row


def test_an_unmatched_row_has_no_job(acme: MailSession) -> None:
    assert subjects(acme, "unmatched") == ["Who are we"]
    row = board(acme, "unmatched").json()["items"][0]

    assert (row["job"], row["confidence"], row["matched_by"]) == (None, None, None)


def test_an_unknown_queue_is_422_with_the_field_and_the_list(
    acme: MailSession,
) -> None:
    response = board(acme, "archive")

    assert response.status_code == 422
    assert response.json()["field_errors"] == [
        {
            "field": "queue",
            "message": "Черга — одна з: matched, unmatched, reviewed.",
        }
    ]


@pytest.mark.parametrize(
    ("query", "field", "message"),
    [
        ({"page": 0}, "page", "Сторінка — від 1."),
        ({"per_page": 30}, "per_page", "per_page — один з: 20, 50, 100."),
        ({"q": "x" * 201}, "q", "Пошуковий запит — не довше 200 символів."),
    ],
)
def test_a_bad_query_is_422_with_the_field_and_the_text(
    acme: MailSession, query: dict[str, object], field: str, message: str
) -> None:
    response = board(acme, **query)

    assert response.status_code == 422
    assert response.json()["field_errors"] == [{"field": field, "message": message}]


def test_an_unknown_query_parameter_is_422(acme: MailSession) -> None:
    assert board(acme, sort="date").status_code == 422


def test_search_by_company_subject_and_text(acme: MailSession) -> None:
    assert subjects(acme, "matched", q="acme") == ["Acme again", "Acme call"]
    assert subjects(acme, "matched", q="LABS") == []
    assert subjects(acme, "matched", q="again") == ["Acme again"]
    assert subjects(acme, "matched", q="see you") == ["Acme again"]
    assert subjects(acme, "matched", q="nothing like it") == []


def test_search_by_the_company_of_the_matched_job(alice: MailSession) -> None:
    apply(alice, "Platform", "Zeta Labs", "zl.example")
    alice.deliver(mail("z1", alice.address(), sender="hr@zl.example", subject="Hi"))

    assert subjects(alice, "matched", q="labs") == ["Hi"]


def test_search_stays_within_the_queue_and_keeps_the_counters(
    acme: MailSession,
) -> None:
    found = board(acme, "unmatched", q="acme").json()

    assert found["items"] == []
    assert found["counts"] == {"matched": 2, "unmatched": 1, "reviewed": 0}
    assert found["page"]["total"] == 0


@pytest.mark.parametrize("size", [20, 50, 100])
def test_pages_hold_20_50_or_100_replies(alice: MailSession, size: int) -> None:
    apply(alice, "Backend", "Acme", "acme.example")
    to = alice.address()
    alice.deliver(*(mail(f"b{n}", to, hours_ago=1 + n) for n in range(1, 24)))

    first = board(alice, "matched", per_page=size, page=1).json()
    second = board(alice, "matched", per_page=size, page=2).json()

    assert first["page"]["size"] == size
    assert first["page"]["total"] == 23
    assert len(first["items"]) == min(size, 23)
    assert len(second["items"]) == max(0, 23 - size)
    assert first["page"]["has_older"] is (size < 23)


def test_the_default_page_is_20(alice: MailSession) -> None:
    apply(alice, "Backend", "Acme", "acme.example")
    to = alice.address()
    alice.deliver(*(mail(f"b{n}", to, hours_ago=1 + n) for n in range(1, 24)))

    body = board(alice, "matched").json()

    assert (len(body["items"]), body["page"]["size"]) == (20, 20)
    assert len(board(alice, "matched", page=2).json()["items"]) == 3


def test_the_details_have_the_text_the_match_and_the_owners_applications(
    acme: MailSession,
) -> None:
    target = reply_id(acme, "matched", "Acme again")

    response = acme.client.get(f"/replies/{target}")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["id"] == target
    assert body["untrusted_text"] == "See you soon"
    assert body["untrusted_subject"] == "Acme again"
    assert body["untrusted_from_address"] == "hr@acme.example"
    assert body["sender_auth"] == "unknown"
    assert body["manual_forward"] is None
    assert body["job"]["job_id"] == 1
    assert body["applications"] == [
        {"job_id": 2, "title": "Platform", "company": "Zeta Labs", "status": "applied"},
        {"job_id": 1, "title": "Backend", "company": "Acme", "status": "applied"},
    ]


def test_the_details_of_a_verified_sender(alice: MailSession) -> None:
    apply(alice, "Backend", "Acme", "acme.example")
    alice.deliver(mail("v1", alice.address(), dmarc="pass", text="Thanks for applying"))

    body = alice.client.get(f"/replies/{reply_id(alice, 'matched', 'Re: v1')}").json()

    assert body["sender_auth"] == "verified"


def test_a_hostile_text_is_prepared_for_a_human(alice: MailSession) -> None:
    apply(alice, "Backend", "Acme", "acme.example")
    alice.deliver(
        mail("h1", alice.address(), text="Hi\N{RIGHT-TO-LEFT OVERRIDE}evil word")
    )

    body = alice.client.get(f"/replies/{reply_id(alice, 'matched', 'Re: h1')}").json()

    assert body["untrusted_text"] == "Hievil word"


def test_a_manual_forward_shows_the_original_sender_from_the_block(
    alice: MailSession,
) -> None:
    contacts = {**SECTIONS["contacts"], "email": "owner@owner.example"}
    assert (
        alice.client.put("/profile/contacts", json=contacts, headers=alice.csrf)
    ).status_code == 200
    apply(alice, "Backend", "Acme", "acme.example")
    alice.deliver(
        mail(
            "f1",
            alice.address(),
            sender="owner@owner.example",
            dmarc="pass",
            subject="Fwd: Your application to Acme",
            text=FORWARDED,
        )
    )
    target = reply_id(alice, "matched", "Fwd: Your application to Acme")

    body = alice.client.get(f"/replies/{target}").json()
    row = board(alice, "matched").json()["items"][0]

    expected = {
        "untrusted_from_address": "ana.recruiter@acme.example",
        "untrusted_from_name": "Ana Recruiter",
        "untrusted_subject": "Your application to Acme",
    }
    assert body["manual_forward"] == expected
    assert row["manual_forward"] == expected
    assert body["sender_auth"] == "verified"
    assert body["job"]["job_id"] == 1
    assert status_of(alice, 1) == "applied"


def test_the_reply_of_another_user_or_a_missing_one_is_404(
    acme: MailSession, bob: MailSession
) -> None:
    target = reply_id(acme, "matched", "Acme call")
    apply(bob, "Backend", "Acme", "acme.example")

    for response in (
        bob.client.get(f"/replies/{target}"),
        acme.client.get(f"/replies/{target + 1000}"),
        preview(bob, target, "other"),
        preview(acme, target + 1000, "other"),
        review(bob, target, "rejection", 1),
        review(acme, target + 1000, "other"),
    ):
        assert (response.status_code, response.json()["code"]) == (404, "not_found")
    assert status_of(acme, 1) == "applied"
    assert subjects(acme, "reviewed") == []
    assert board(bob, "matched").json()["counts"] == {
        "matched": 0,
        "unmatched": 0,
        "reviewed": 0,
    }


def test_the_queues_of_two_users_do_not_mix(
    acme: MailSession, bob: MailSession
) -> None:
    assert subjects(acme, "matched") == ["Acme again", "Acme call"]
    assert subjects(bob, "matched") == []
    assert subjects(bob, "unmatched") == []


@pytest.mark.parametrize(
    ("kind", "before", "after", "changes"),
    [
        ("rejection", "applied", "rejected", True),
        ("invitation", "interview", "interview", False),
        ("auto_confirmation", "applied", "applied", False),
    ],
)
def test_the_preview_says_where_the_application_goes(
    acme: MailSession, kind: str, before: str, after: str, changes: bool
) -> None:
    if before != "applied":
        moved = acme.client.post(
            "/jobs/1/application/status", json={"status": before}, headers=acme.csrf
        )
        assert moved.status_code == 200
    target = reply_id(acme, "matched", "Acme call")

    response = preview(acme, target, kind, 1)

    assert response.status_code == 200
    assert response.json() == {
        "job_id": 1,
        "current_status": before,
        "status_after": after,
        "changes": changes,
    }
    assert status_of(acme, 1) == before
    assert subjects(acme, "reviewed") == []


@pytest.mark.parametrize(
    ("kind", "after"),
    [
        ("invitation", "interview"),
        ("assignment", "interview"),
        ("other", "replied"),
    ],
)
def test_the_preview_follows_the_review_rules(
    acme: MailSession, kind: str, after: str
) -> None:
    target = reply_id(acme, "matched", "Acme call")

    assert preview(acme, target, kind, 1).json()["status_after"] == after


def test_the_preview_without_a_job_changes_nothing(acme: MailSession) -> None:
    target = reply_id(acme, "matched", "Acme call")

    response = preview(acme, target, "rejection")

    assert response.json() == {
        "job_id": None,
        "current_status": None,
        "status_after": None,
        "changes": False,
    }


def test_the_preview_never_moves_a_status_back(acme: MailSession) -> None:
    acme.client.post(
        "/jobs/1/application/status", json={"status": "offer"}, headers=acme.csrf
    )
    target = reply_id(acme, "matched", "Acme call")

    body = preview(acme, target, "other", 1).json()

    assert (body["current_status"], body["status_after"], body["changes"]) == (
        "offer",
        "offer",
        False,
    )


def test_the_preview_of_a_bad_type_is_422_with_the_text(acme: MailSession) -> None:
    target = reply_id(acme, "matched", "Acme call")

    response = preview(acme, target, "ghosted", 1)

    assert response.status_code == 422
    assert response.json()["field_errors"] == [{"field": "type", "message": BAD_TYPE}]


def test_the_preview_of_a_job_without_an_application_is_404(
    acme: MailSession,
) -> None:
    acme.client.post("/jobs", json={"text": "Data at Tidewell"}, headers=acme.csrf)
    target = reply_id(acme, "matched", "Acme call")

    assert preview(acme, target, "other", 3).status_code == 404


def test_a_review_moves_the_reply_to_reviewed_and_the_application_forward(
    acme: MailSession,
) -> None:
    target = reply_id(acme, "matched", "Acme call")

    response = review(acme, target, "rejection", 1)

    assert response.status_code == 200
    body = response.json()
    assert body["reply"]["id"] == target
    assert body["reply"]["type"] == "rejection"
    assert body["reply"]["reviewed_at"] is not None
    assert body["reply"]["job"]["job_id"] == 1
    assert body["application"]["job_id"] == 1
    assert body["application"]["status"] == "rejected"
    assert status_of(acme, 1) == "rejected"
    assert subjects(acme, "matched") == ["Acme again"]
    assert subjects(acme, "reviewed") == ["Acme call"]
    assert board(acme, "matched").json()["counts"] == {
        "matched": 1,
        "unmatched": 1,
        "reviewed": 1,
    }


def test_a_review_picks_another_job_than_the_suggested_one(acme: MailSession) -> None:
    target = reply_id(acme, "unmatched", "Who are we")

    response = review(acme, target, "invitation", 2)

    assert response.status_code == 200
    assert response.json()["reply"]["job"]["job_id"] == 2
    assert status_of(acme, 2) == "interview"
    assert status_of(acme, 1) == "applied"
    assert subjects(acme, "unmatched") == []
    assert subjects(acme, "reviewed") == ["Who are we"]


def test_a_review_without_a_job_leaves_the_applications_alone(
    acme: MailSession,
) -> None:
    target = reply_id(acme, "matched", "Acme call")

    response = review(acme, target, "other")

    assert response.status_code == 200
    body = response.json()
    assert (body["reply"]["job"], body["application"]) == (None, None)
    assert status_of(acme, 1) == "applied"
    assert subjects(acme, "reviewed") == ["Acme call"]


def test_a_review_never_moves_a_status_back(acme: MailSession) -> None:
    acme.client.post(
        "/jobs/1/application/status", json={"status": "interview"}, headers=acme.csrf
    )
    target = reply_id(acme, "matched", "Acme call")

    response = review(acme, target, "other", 1)

    assert response.status_code == 200
    assert response.json()["application"]["status"] == "interview"
    assert subjects(acme, "reviewed") == ["Acme call"]


def test_a_bad_type_is_422_with_the_text_and_the_reply_stays_open(
    acme: MailSession,
) -> None:
    target = reply_id(acme, "matched", "Acme call")

    response = review(acme, target, "ghosted", 1)

    assert response.status_code == 422
    assert response.json()["field_errors"] == [{"field": "type", "message": BAD_TYPE}]
    assert status_of(acme, 1) == "applied"
    assert subjects(acme, "reviewed") == []


def test_a_job_without_an_application_is_404_and_the_reply_stays_open(
    acme: MailSession,
) -> None:
    acme.client.post("/jobs", json={"text": "Data at Tidewell"}, headers=acme.csrf)
    target = reply_id(acme, "matched", "Acme call")

    response = review(acme, target, "other", 3)

    assert (response.status_code, response.json()["code"]) == (404, "not_found")
    assert subjects(acme, "reviewed") == []


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"job_id": 1},
        {"type": "other", "extra": 1},
        {"type": "other", "job_id": "x"},
    ],
)
def test_a_malformed_review_body_is_422(
    acme: MailSession, body: dict[str, object]
) -> None:
    target = reply_id(acme, "matched", "Acme call")

    response = acme.client.post(
        f"/replies/{target}/review", json=body, headers=acme.csrf
    )

    assert response.status_code == 422
    assert subjects(acme, "reviewed") == []
