"""Вакансії через HTTP наскрізь: сесія й CSRF, 422 за полями, 404 для чужих, ізоляція користувачів."""

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

import httpx2
import pytest
from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.jobs.job import NewJob
from infrastructure.db.unit_of_work import unit_of_work_factory
from tests.integration.test_profile_http import (
    ClientFactory,
    Session,
    make_client,
)

__all__ = ["make_client"]

POSTING = "Senior Python engineer. Remote. Asyncio, Postgres."
ALERT_LINK = (
    "https://es.linkedin.com/comm/jobs/view/dev-at-acme-4012345678/?trackingId=x"
)


class JobsSession:
    def __init__(self, session: Session) -> None:
        self.client = session.client
        self.csrf = session.csrf

    def listing(self, **query: object) -> httpx2.Response:
        return self.client.get("/jobs", params=query)  # type: ignore[arg-type]

    def get(self, job_id: object) -> httpx2.Response:
        return self.client.get(f"/jobs/{job_id}")

    def add(self, **fields: str) -> httpx2.Response:
        body = {"text": POSTING} | fields
        return self.client.post("/jobs", json=body, headers=self.csrf)

    def dismiss(self, job_ids: list[int], reason: str = "не цікаво") -> httpx2.Response:
        body = {"job_ids": job_ids, "reason": reason}
        return self.client.post("/jobs/dismiss", json=body, headers=self.csrf)

    def restore(self, job_id: int) -> httpx2.Response:
        return self.client.post(f"/jobs/{job_id}/restore", headers=self.csrf)

    def numbers(self, **query: object) -> list[int]:
        return [item["job_id"] for item in self.listing(**query).json()["items"]]


@pytest.fixture
def alice(make_client: ClientFactory) -> JobsSession:
    return JobsSession(Session(make_client(), "alice@example.com"))


@pytest.fixture
def bob(make_client: ClientFactory) -> JobsSession:
    return JobsSession(Session(make_client(), "bob@example.com"))


def field_errors(response: httpx2.Response) -> list[tuple[str, str]]:
    return [
        (item["field"], item["message"]) for item in response.json()["field_errors"]
    ]


def test_every_route_requires_a_session(make_client: ClientFactory) -> None:
    client = make_client()
    for method, path in (
        ("GET", "/jobs"),
        ("GET", "/jobs/1"),
        ("POST", "/jobs"),
        ("POST", "/jobs/dismiss"),
        ("POST", "/jobs/1/restore"),
    ):
        response = client.request(method, path)
        assert (response.status_code, response.json()["code"]) == (
            401,
            "not_authenticated",
        ), (method, path)


def test_unsafe_requests_require_the_csrf_token(alice: JobsSession) -> None:
    for path, body in (
        ("/jobs", {"text": POSTING}),
        ("/jobs/dismiss", {"job_ids": [1], "reason": "x"}),
        ("/jobs/1/restore", None),
    ):
        response = alice.client.post(path, json=body)
        assert (response.status_code, response.json()["code"]) == (403, "csrf_failed")
    assert alice.numbers() == []


def test_a_new_user_has_an_empty_list_and_no_sources(alice: JobsSession) -> None:
    response = alice.listing()
    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "sources": [],
        "counts": {"in_progress": 0, "applied_unreviewed": 0, "needs_text": False},
    }
    assert response.headers["cache-control"] == "no-store"


def test_a_new_job_is_created_with_number_one(alice: JobsSession) -> None:
    response = alice.add(title="Backend", company="Acme", url="https://acme.com/j/1")
    assert response.status_code == 201
    assert response.json() == {"job_id": 1, "duplicate": False, "outcome": "created"}
    assert alice.add(text="another").json()["job_id"] == 2


def test_the_numbers_of_users_are_independent(
    alice: JobsSession, bob: JobsSession
) -> None:
    alice.add(text="one")
    alice.add(text="two")
    assert bob.add(text="one").json()["job_id"] == 1


def test_a_job_shows_its_details(alice: JobsSession) -> None:
    alice.add(title="Backend", company="Acme", url="https://Acme.com/j/1/?utm_source=x")
    details = alice.get(1).json()
    created_at = details.pop("created_at")
    assert created_at.endswith(("Z", "+00:00"))
    opened_at = details.pop("opened_at")
    assert opened_at is not None
    assert opened_at.endswith(("Z", "+00:00"))
    assert details == {
        "job_id": 1,
        "source": "manual",
        "url": "https://acme.com/j/1",
        "title": "Backend",
        "company": "Acme",
        "location": None,
        "text": POSTING,
        "needs_text": False,
        "dismissed_at": None,
        "dismiss_reason": None,
        "is_new": False,
        "triage": None,
    }


def test_the_list_item_has_the_row_fields(alice: JobsSession) -> None:
    alice.add(title="Backend", company="Acme", url="https://acme.com/j/1")
    body = alice.listing().json()
    item = body["items"][0]
    item.pop("created_at")
    assert item == {
        "job_id": 1,
        "source": "manual",
        "url": "https://acme.com/j/1",
        "title": "Backend",
        "company": "Acme",
        "needs_text": False,
        "dismissed": False,
        "score": None,
        "filters_passed": None,
        "work_mode": None,
        "triage_score": None,
        "triage_verdict": None,
        "triage_reason": None,
        "status": None,
        "is_new": False,
    }
    assert body["sources"] == ["manual"]


def test_the_same_text_in_another_case_is_a_duplicate(alice: JobsSession) -> None:
    alice.add()
    response = alice.add(text=f"  {POSTING.upper()}  ")
    assert response.status_code == 200
    assert response.json() == {"job_id": 1, "duplicate": True, "outcome": "duplicate"}
    assert alice.numbers() == [1]


def test_the_same_url_with_tracking_is_a_duplicate(alice: JobsSession) -> None:
    alice.add(text="one", url="https://acme.com/jobs/1")
    response = alice.add(text="two", url="https://ACME.com/jobs/1/?utm_source=m#apply")
    assert response.json() == {"job_id": 1, "duplicate": True, "outcome": "duplicate"}


def test_a_linkedin_link_completes_the_waiting_job(
    alice: JobsSession, waiting_job: int
) -> None:
    response = alice.add(url=ALERT_LINK, title="Ignored", company="Ignored")
    assert response.status_code == 200
    assert response.json() == {
        "job_id": waiting_job,
        "duplicate": False,
        "outcome": "text_added",
    }
    details = alice.get(waiting_job).json()
    assert (details["text"], details["needs_text"]) == (POSTING, False)
    assert (details["title"], details["company"]) == ("Backend Dev", "Acme")


def test_a_linkedin_link_to_a_job_with_text_changes_nothing(
    alice: JobsSession, waiting_job: int
) -> None:
    alice.add(url=ALERT_LINK)
    again = alice.add(text="A different description", url=ALERT_LINK)
    assert again.json() == {
        "job_id": waiting_job,
        "duplicate": True,
        "outcome": "duplicate",
    }
    assert alice.get(waiting_job).json()["text"] == POSTING


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({"text": ""}, [("text", "Встав текст опису вакансії.")]),
        ({"text": "   "}, [("text", "Встав текст опису вакансії.")]),
        ({"text": "x" * 100_001}, [("text", "Опис задовгий: більше 100000 символів.")]),
        (
            {"url": "example.com/job"},
            [("url", "Посилання має починатися з http:// або https://.")],
        ),
        (
            {"text": "", "url": "ftp://x.com"},
            [
                ("text", "Встав текст опису вакансії."),
                ("url", "Посилання має починатися з http:// або https://."),
            ],
        ),
    ],
)
def test_an_invalid_job_is_422_with_the_v1_texts(
    alice: JobsSession, fields: dict[str, str], expected: list[tuple[str, str]]
) -> None:
    response = alice.add(**fields)
    assert (response.status_code, response.json()["code"]) == (422, "invalid_fields")
    assert field_errors(response) == expected
    assert alice.numbers() == []


def test_a_job_body_with_an_unknown_field_is_422(alice: JobsSession) -> None:
    response = alice.client.post(
        "/jobs", json={"text": "x", "role": "admin"}, headers=alice.csrf
    )
    assert (response.status_code, response.json()["code"]) == (422, "invalid_request")


def test_a_missing_job_is_404(alice: JobsSession) -> None:
    response = alice.get(99)
    assert (response.status_code, response.json()["code"]) == (404, "not_found")


def test_a_job_of_another_user_is_404_like_a_missing_one(
    alice: JobsSession, bob: JobsSession
) -> None:
    alice.add()
    foreign, missing = bob.get(1), bob.get(99)
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json()["message"] == missing.json()["message"]


def test_a_job_number_that_is_not_an_integer_is_422(alice: JobsSession) -> None:
    assert alice.get("abc").status_code == 422


def test_a_huge_job_number_is_404(alice: JobsSession) -> None:
    assert alice.get(10**30).status_code == 404


def test_the_list_filters(alice: JobsSession) -> None:
    alice.add(text="we use Rust", title="Engineer")
    alice.add(text="python only", title="Dev", company="Acme")
    assert alice.numbers(query="rust") == [1]
    assert alice.numbers(query="acme") == [2]
    assert alice.numbers(source="manual") == [2, 1]
    assert alice.numbers(source="other") == []
    assert alice.numbers(days="7") == [2, 1]
    assert alice.numbers(limit=1) == [2]


def test_invalid_filters_are_422_with_the_v1_texts(alice: JobsSession) -> None:
    response = alice.listing(days="0", limit=0, query="x" * 201)
    assert response.status_code == 422
    assert field_errors(response) == [
        ("query", "Запит задовгий: більше 200 символів."),
        ("days", "Свіжість — ціле число днів від 1 до 3650."),
        ("limit", "Ліміт — від 1 до 200."),
    ]


def test_dismissed_jobs_leave_the_list_and_show_with_the_flag(
    alice: JobsSession,
) -> None:
    alice.add(text="keep")
    alice.add(text="gone")
    response = alice.dismiss([2], "  не   цікаво зовсім ")
    assert response.status_code == 204
    assert alice.numbers() == [1]
    assert alice.numbers(dismissed="true") == [2]
    item = alice.listing(dismissed="true").json()["items"][0]
    assert item["dismissed"] is True
    details = alice.get(2).json()
    assert details["dismiss_reason"] == "не цікаво зовсім"
    assert details["dismissed_at"] is not None


def test_dismissing_again_keeps_the_first_reason(alice: JobsSession) -> None:
    alice.add()
    alice.dismiss([1], "перша")
    alice.dismiss([1], "друга")
    assert alice.get(1).json()["dismiss_reason"] == "перша"


@pytest.mark.parametrize(
    ("job_ids", "reason", "field", "message"),
    [
        ([], "x", "job_ids", "Порожня пачка: потрібна хоч одна вакансія."),
        (list(range(1, 52)), "x", "job_ids", "У пачці не більше 50 вакансій."),
        ([1, 1], "x", "job_ids", "Елемент 2: вакансія 1 уже є в елементі 1."),
        ([1, 99], "x", "job_ids", "Елемент 2: вакансію 99 не знайдено."),
        ([1], "", "reason", "Вкажи причину приховування."),
        ([1], "x" * 201, "reason", "Причина задовга: більше 200 символів."),
    ],
)
def test_an_invalid_dismissal_is_422_and_hides_nothing(
    alice: JobsSession, job_ids: list[int], reason: str, field: str, message: str
) -> None:
    alice.add()
    response = alice.dismiss(job_ids, reason)
    assert (response.status_code, response.json()["code"]) == (422, "invalid_value")
    assert field_errors(response) == [(field, message)]
    assert alice.numbers() == [1]


def test_a_job_of_another_user_cannot_be_dismissed(
    alice: JobsSession, bob: JobsSession
) -> None:
    alice.add()
    assert bob.dismiss([1]).status_code == 422
    assert alice.numbers() == [1]


def test_a_restored_job_is_back_in_the_list(alice: JobsSession) -> None:
    alice.add()
    alice.dismiss([1])
    assert alice.restore(1).status_code == 204
    assert alice.numbers() == [1]
    assert alice.get(1).json()["dismiss_reason"] is None


def test_restoring_a_job_that_is_not_dismissed_changes_nothing(
    alice: JobsSession,
) -> None:
    alice.add()
    before = alice.get(1).json()
    assert alice.restore(1).status_code == 204
    assert alice.get(1).json() == before


def test_restoring_a_missing_or_foreign_job_is_404(
    alice: JobsSession, bob: JobsSession
) -> None:
    alice.add()
    alice.dismiss([1])
    assert alice.restore(99).status_code == 404
    assert bob.restore(1).status_code == 404
    assert alice.numbers(dismissed="true") == [1]


def test_one_user_does_not_see_the_jobs_of_another(
    alice: JobsSession, bob: JobsSession
) -> None:
    alice.add()
    assert bob.listing().json() == {
        "items": [],
        "sources": [],
        "counts": {"in_progress": 0, "applied_unreviewed": 0, "needs_text": False},
    }


@pytest.fixture
def waiting_job(alice: JobsSession, portal: BlockingPortal, engine: AsyncEngine) -> int:
    """Вакансія Аліси з листа-алерту (її створить B10): без тексту, є посилання, посада й компанія."""

    async def seed() -> int:
        async with engine.connect() as conn:
            row = await conn.execute(
                text("SELECT id FROM users WHERE email = 'alice@example.com'")
            )
            user_id = UserId(row.scalar_one())
        async with unit_of_work_factory(engine)() as tx:
            number = await tx.jobs.add(
                user_id,
                JobId(uuid4()),
                NewJob(
                    text=None,
                    url="https://www.linkedin.com/jobs/view/4012345678",
                    title="Backend Dev",
                    company="Acme",
                    linkedin_id="4012345678",
                    source="linkedin_alert",
                ),
                datetime.now(UTC),
            )
            await tx.commit()
            return number

    return portal.call(seed)


@pytest.fixture
def seed_job(
    alice: JobsSession, portal: BlockingPortal, engine: AsyncEngine
) -> Callable[[str], int]:
    """Вакансія Аліси з заданим джерелом (ats:/rss: створить імпорт з джерел) — з текстом."""

    def seed(source: str) -> int:
        async def run() -> int:
            async with engine.connect() as conn:
                row = await conn.execute(
                    text("SELECT id FROM users WHERE email = 'alice@example.com'")
                )
                user_id = UserId(row.scalar_one())
            async with unit_of_work_factory(engine)() as tx:
                number = await tx.jobs.add(
                    user_id,
                    JobId(uuid4()),
                    NewJob(text=f"Posting from {source}", source=source),
                    datetime.now(UTC),
                )
                await tx.commit()
                return number

        return portal.call(run)

    return seed


def is_new(alice: JobsSession, number: int) -> bool:
    items = {item["job_id"]: item for item in alice.listing().json()["items"]}
    return bool(items[number]["is_new"])


@pytest.mark.parametrize("source", ["ats:greenhouse", "rss:remoteok"])
def test_an_unopened_source_job_is_new(
    alice: JobsSession, seed_job: Callable[[str], int], source: str
) -> None:
    assert is_new(alice, seed_job(source)) is True


def test_a_manual_job_is_not_new(alice: JobsSession) -> None:
    alice.add()
    assert is_new(alice, 1) is False


def test_a_linkedin_alert_job_is_not_new(alice: JobsSession, waiting_job: int) -> None:
    assert is_new(alice, waiting_job) is False


def test_opening_a_job_sets_the_first_open_time_and_clears_new(
    alice: JobsSession, seed_job: Callable[[str], int]
) -> None:
    number = seed_job("ats:greenhouse")
    assert alice.get(number).json()["opened_at"] is not None
    assert is_new(alice, number) is False


def test_opening_again_keeps_the_first_open_time(
    alice: JobsSession, seed_job: Callable[[str], int]
) -> None:
    number = seed_job("rss:remoteok")
    first = alice.get(number).json()["opened_at"]
    second = alice.get(number).json()["opened_at"]
    assert first is not None
    assert second == first


def test_the_details_of_an_unopened_source_job_already_count_as_opened(
    alice: JobsSession, seed_job: Callable[[str], int]
) -> None:
    details = alice.get(seed_job("ats:lever")).json()
    assert details["is_new"] is False
