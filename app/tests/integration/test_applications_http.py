"""Подачі через HTTP наскрізь: сесія й CSRF, 422 за полями, 404 для чужих, перехід статусу, список і «Не цікаво»."""

from datetime import UTC, date, datetime, timedelta

import httpx2
import pytest

from tests.integration.test_profile_http import (
    ClientFactory,
    Session,
    make_client,
)

__all__ = ["make_client"]

POSTING = "Senior Python engineer. Remote. Asyncio, Postgres."
EVERY_MOVE = ["replied", "interview", "offer", "rejected", "withdrawn"]


class ApplicationsSession:
    def __init__(self, session: Session) -> None:
        self.client = session.client
        self.csrf = session.csrf

    def add_job(self, text: str = POSTING) -> int:
        response = self.client.post("/jobs", json={"text": text}, headers=self.csrf)
        return int(response.json()["job_id"])

    def get(self, job: object) -> httpx2.Response:
        return self.client.get(f"/jobs/{job}/application")

    def put(self, job: object, **fields: object) -> httpx2.Response:
        body = {"channel": "email"} | fields
        return self.client.put(f"/jobs/{job}/application", json=body, headers=self.csrf)

    def move(self, job: object, status: str) -> httpx2.Response:
        return self.client.post(
            f"/jobs/{job}/application/status",
            json={"status": status},
            headers=self.csrf,
        )

    def listing(self, **query: object) -> httpx2.Response:
        return self.client.get("/jobs", params=query)  # type: ignore[arg-type]

    def numbers(self, **query: object) -> list[int]:
        return [item["job_id"] for item in self.listing(**query).json()["items"]]

    def dismiss(self, job_ids: list[int]) -> httpx2.Response:
        body = {"job_ids": job_ids, "reason": "не цікаво"}
        return self.client.post("/jobs/dismiss", json=body, headers=self.csrf)


@pytest.fixture
def alice(make_client: ClientFactory) -> ApplicationsSession:
    return ApplicationsSession(Session(make_client(), "alice@example.com"))


@pytest.fixture
def bob(make_client: ClientFactory) -> ApplicationsSession:
    return ApplicationsSession(Session(make_client(), "bob@example.com"))


def field_errors(response: httpx2.Response) -> list[tuple[str, str]]:
    return [
        (item["field"], item["message"]) for item in response.json()["field_errors"]
    ]


def test_every_route_requires_a_session(make_client: ClientFactory) -> None:
    client = make_client()
    for method, path in (
        ("GET", "/jobs/1/application"),
        ("PUT", "/jobs/1/application"),
        ("POST", "/jobs/1/application/status"),
    ):
        response = client.request(method, path)
        assert (response.status_code, response.json()["code"]) == (
            401,
            "not_authenticated",
        ), (method, path)


def test_unsafe_requests_require_the_csrf_token(alice: ApplicationsSession) -> None:
    job = alice.add_job()
    for method, path, body in (
        ("PUT", f"/jobs/{job}/application", {"channel": "email"}),
        ("POST", f"/jobs/{job}/application/status", {"status": "replied"}),
    ):
        response = alice.client.request(method, path, json=body)
        assert (response.status_code, response.json()["code"]) == (403, "csrf_failed")
    assert alice.get(job).status_code == 404


def test_a_job_without_application_answers_404(alice: ApplicationsSession) -> None:
    job = alice.add_job()
    response = alice.get(job)
    assert (response.status_code, response.json()["code"]) == (404, "not_found")


def test_marking_a_job_applied_returns_the_application(
    alice: ApplicationsSession,
) -> None:
    job = alice.add_job()
    response = alice.put(
        job,
        channel="ats",
        applied_on="2026-01-01",
        ats="lever",
        company_domains=["https://www.Acme.com/jobs"],
        company_emails=["HR@Acme.com"],
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    changed_at = body.pop("status_changed_at")
    assert changed_at.endswith(("Z", "+00:00"))
    assert body == {
        "job_id": job,
        "status": "applied",
        "applied_on": "2026-01-01",
        "channel": "ats",
        "ats": "lever",
        "company_domains": ["acme.com"],
        "company_emails": ["hr@acme.com"],
        "allowed_transitions": EVERY_MOVE,
    }


def test_the_application_can_be_read_back(alice: ApplicationsSession) -> None:
    job = alice.add_job()
    saved = alice.put(job, applied_on="2026-01-01").json()
    response = alice.get(job)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == saved


def test_an_empty_date_means_today(alice: ApplicationsSession) -> None:
    job = alice.add_job()
    applied_on = alice.put(job, applied_on="").json()["applied_on"]
    assert date.fromisoformat(applied_on) <= datetime.now(UTC).date() + timedelta(
        days=1
    )


def test_optional_fields_may_be_left_out(alice: ApplicationsSession) -> None:
    job = alice.add_job()
    body = alice.put(job).json()
    assert (body["ats"], body["company_domains"], body["company_emails"]) == (
        None,
        [],
        [],
    )


def test_saving_again_replaces_the_details_and_keeps_the_status(
    alice: ApplicationsSession,
) -> None:
    job = alice.add_job()
    alice.put(job, channel="email", company_emails=["a@acme.com"])
    moved = alice.move(job, "interview").json()
    again = alice.put(job, channel="referral", ats="ashby").json()
    assert (again["status"], again["status_changed_at"]) == (
        "interview",
        moved["status_changed_at"],
    )
    assert (again["channel"], again["ats"], again["company_emails"]) == (
        "referral",
        "ashby",
        [],
    )


def test_invalid_fields_are_reported_one_by_one(alice: ApplicationsSession) -> None:
    job = alice.add_job()
    response = alice.put(
        job,
        channel="phone",
        applied_on="soon",
        ats="workday",
        company_domains=["no"],
        company_emails=["jane"],
    )
    assert (response.status_code, response.json()["code"]) == (422, "invalid_fields")
    assert field_errors(response) == [
        ("applied_on", "Дата подачі — у форматі YYYY-MM-DD."),
        ("channel", "Канал — один з: email, ats, linkedin, referral."),
        (
            "ats",
            "ATS — один з: greenhouse, lever, ashby, workable, smartrecruiters, other.",
        ),
        ("company_domains", "Некоректний домен компанії: no."),
        ("company_emails", "Некоректна адреса компанії: jane."),
    ]
    assert alice.get(job).status_code == 404


def test_a_future_date_is_refused(alice: ApplicationsSession) -> None:
    job = alice.add_job()
    response = alice.put(job, applied_on="2999-01-01")
    assert response.status_code == 422
    assert field_errors(response) == [
        ("applied_on", "Дата подачі не може бути в майбутньому.")
    ]


def test_eleven_domains_are_refused(alice: ApplicationsSession) -> None:
    job = alice.add_job()
    response = alice.put(job, company_domains=[f"c{n}.com" for n in range(11)])
    assert field_errors(response) == [
        ("company_domains", "Не більше 10 доменів компанії.")
    ]


def test_a_body_without_a_channel_is_refused(alice: ApplicationsSession) -> None:
    job = alice.add_job()
    response = alice.client.put(f"/jobs/{job}/application", json={}, headers=alice.csrf)
    assert (response.status_code, response.json()["code"]) == (422, "invalid_request")


def test_unknown_body_fields_are_refused(alice: ApplicationsSession) -> None:
    job = alice.add_job()
    response = alice.client.put(
        f"/jobs/{job}/application",
        json={"channel": "email", "status": "offer"},
        headers=alice.csrf,
    )
    assert (response.status_code, response.json()["code"]) == (422, "invalid_request")


def test_an_unknown_job_answers_404(alice: ApplicationsSession) -> None:
    assert alice.put(99).status_code == 404
    assert alice.get(99).status_code == 404
    assert alice.move(99, "replied").status_code == 404


def test_a_job_number_that_is_not_a_number_is_refused(
    alice: ApplicationsSession,
) -> None:
    assert alice.get("abc").status_code == 422


@pytest.mark.parametrize("status", EVERY_MOVE)
def test_every_forward_move_from_applied_is_accepted(
    alice: ApplicationsSession, status: str
) -> None:
    job = alice.add_job()
    alice.put(job)
    response = alice.move(job, status)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == status
    assert alice.get(job).json() == body


def test_a_move_lists_only_the_moves_that_are_still_allowed(
    alice: ApplicationsSession,
) -> None:
    job = alice.add_job()
    alice.put(job)
    assert alice.move(job, "interview").json()["allowed_transitions"] == [
        "offer",
        "rejected",
        "withdrawn",
    ]
    assert alice.move(job, "rejected").json()["allowed_transitions"] == []


def test_the_same_status_changes_nothing(alice: ApplicationsSession) -> None:
    job = alice.add_job()
    before = alice.put(job).json()
    response = alice.move(job, "applied")
    assert (response.status_code, response.json()) == (200, before)


def test_a_closed_application_is_refused_with_the_v1_text(
    alice: ApplicationsSession,
) -> None:
    job = alice.add_job()
    alice.put(job)
    alice.move(job, "withdrawn")
    response = alice.move(job, "offer")
    assert (response.status_code, response.json()["code"]) == (422, "invalid_value")
    assert field_errors(response) == [
        ("status", "Подачу вже закрито (withdrawn): статус більше не змінюється.")
    ]


def test_a_move_back_is_refused_with_the_v1_text(alice: ApplicationsSession) -> None:
    job = alice.add_job()
    alice.put(job)
    alice.move(job, "offer")
    response = alice.move(job, "applied")
    assert response.status_code == 422
    assert field_errors(response)[0][0] == "status"
    assert field_errors(response)[0][1].startswith("Статус offer → applied неможливий")
    assert alice.get(job).json()["status"] == "offer"


def test_an_unknown_status_is_refused(alice: ApplicationsSession) -> None:
    job = alice.add_job()
    alice.put(job)
    response = alice.move(job, "hired")
    assert response.status_code == 422
    assert field_errors(response) == [
        (
            "status",
            "Статус — один з: applied, replied, interview, offer, rejected, withdrawn.",
        )
    ]


def test_moving_a_job_without_application_answers_404(
    alice: ApplicationsSession,
) -> None:
    job = alice.add_job()
    assert alice.move(job, "replied").status_code == 404


def test_a_user_does_not_see_or_change_the_application_of_another(
    alice: ApplicationsSession, bob: ApplicationsSession
) -> None:
    job = alice.add_job()
    alice.put(job)
    assert bob.get(job).status_code == 404
    assert bob.put(job).status_code == 404
    assert bob.move(job, "offer").status_code == 404
    assert alice.get(job).json()["status"] == "applied"


def test_the_same_job_number_of_two_users_has_two_applications(
    alice: ApplicationsSession, bob: ApplicationsSession
) -> None:
    alice_job = alice.add_job("Alice job")
    bob_job = bob.add_job("Bob job")
    assert alice_job == bob_job == 1
    alice.put(alice_job, channel="email")
    bob.put(bob_job, channel="linkedin")
    bob.move(bob_job, "offer")
    assert alice.get(1).json()["channel"] == "email"
    assert alice.get(1).json()["status"] == "applied"
    assert bob.get(1).json()["channel"] == "linkedin"
    assert bob.get(1).json()["status"] == "offer"


# --- список ---


def test_the_list_row_has_the_status(alice: ApplicationsSession) -> None:
    plain = alice.add_job("plain")
    applied = alice.add_job("applied")
    alice.put(applied)
    alice.move(applied, "interview")
    rows = {item["job_id"]: item for item in alice.listing().json()["items"]}
    assert rows[plain]["status"] is None
    assert rows[applied]["status"] == "interview"


def test_the_list_can_be_filtered_by_one_status(alice: ApplicationsSession) -> None:
    first, second, third = (alice.add_job(f"job {n}") for n in "abc")
    for job in (first, second, third):
        alice.put(job)
    alice.move(second, "offer")
    alice.move(third, "rejected")
    assert alice.numbers(status="offer") == [second]
    assert alice.numbers(status="applied") == [first]


def test_the_active_group_has_the_four_open_statuses(
    alice: ApplicationsSession,
) -> None:
    jobs = [alice.add_job(f"job {n}") for n in range(6)]
    for job, status in zip(
        jobs[1:], ["applied", "replied", "interview", "offer", "rejected"], strict=True
    ):
        alice.put(job)
        alice.move(job, status)
    assert sorted(alice.numbers(status="active")) == jobs[1:5]


def test_the_closed_group_in_the_web_list_has_only_withdrawn(
    alice: ApplicationsSession,
) -> None:
    """Відмови зникають із веб-списку повністю (рішення 2026-11-04); MCP їх лишає."""
    jobs = [alice.add_job(f"job {n}") for n in range(4)]
    alice.put(jobs[1])
    alice.put(jobs[2])
    alice.put(jobs[3])
    alice.move(jobs[2], "rejected")
    alice.move(jobs[3], "withdrawn")
    assert sorted(alice.numbers(status="closed")) == jobs[3:]


def test_an_unknown_status_filter_is_refused(alice: ApplicationsSession) -> None:
    alice.add_job()
    response = alice.listing(status="hired")
    assert (response.status_code, response.json()["code"]) == (422, "invalid_fields")
    assert field_errors(response)[0][0] == "status"


def test_the_status_filter_combines_with_the_text_query(
    alice: ApplicationsSession,
) -> None:
    python = alice.add_job("Python backend")
    java = alice.add_job("Java backend")
    alice.put(python)
    alice.put(java)
    assert alice.numbers(status="active", query="python") == [python]


def test_the_status_filter_ignores_the_applications_of_another_user(
    alice: ApplicationsSession, bob: ApplicationsSession
) -> None:
    alice.add_job("Alice job")
    bob_job = bob.add_job("Bob job")
    bob.put(bob_job)
    assert alice.numbers(status="active") == []
    assert bob.numbers(status="active") == [bob_job]


# --- «Не цікаво» ---


def test_an_applied_job_cannot_be_hidden(alice: ApplicationsSession) -> None:
    job = alice.add_job()
    alice.put(job)
    response = alice.dismiss([job])
    assert (response.status_code, response.json()["code"]) == (
        409,
        "job_has_application",
    )
    assert response.json()["message"] == (
        "На вакансію 1 уже є подача — поданих вакансій не ховають."
    )
    assert alice.numbers() == [job]


def test_a_batch_with_an_applied_job_hides_nothing(alice: ApplicationsSession) -> None:
    first, second = alice.add_job("one"), alice.add_job("two")
    alice.put(second)
    response = alice.dismiss([first, second])
    assert response.status_code == 409
    assert response.json()["message"] == (
        "Елемент 2: на вакансію 2 уже є подача — поданих вакансій не ховають."
    )
    assert sorted(alice.numbers()) == [first, second]


def test_a_job_without_application_is_hidden_as_before(
    alice: ApplicationsSession,
) -> None:
    first, second = alice.add_job("one"), alice.add_job("two")
    alice.put(second)
    assert alice.dismiss([first]).status_code == 204
    assert alice.numbers() == [second]
