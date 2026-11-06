"""«Оновити зараз» і «уже не проходять фільтр» через HTTP наскрізь: сесія й CSRF, ліміт 2 запити за 30 хв
на користувача (429 з Retry-After), запити, які позначає справжній прогін, `refresh` і `filtered_out_count` у
списку джерел, список вакансій, що вже не проходять фільтр профілю, і приховування вибраних (409, якщо набір
змінився)."""

from datetime import datetime, timedelta
from typing import Any

import httpx2
import pytest
from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from domain.sources.kinds import FeedSource, Platform
from tests.integration.test_profile_http import make_client
from tests.integration.test_sources_manage_http import (
    ClientFactory,
    SourcesSession,
    alice,
    bob,
    db,
    posting,
    probe_net,
    sources_client,
    status_and_code,
)
from tests.support.source_runs import registry

__all__ = [
    "alice",
    "bob",
    "db",
    "make_client",
    "probe_net",
    "sources_client",
]

LIMIT_MESSAGE = "Оновлення джерел уже запитано 2 рази за 30 хв — наступне о "
RAN_AT = "2026-01-01T09:00:00Z"
type Rows = list[tuple[Any, ...]]


@pytest.fixture
def queries(portal: BlockingPortal, engine: AsyncEngine) -> Queries:
    return Queries(portal, engine)


class Queries:
    """Прямі запити до таблиці запитів: що записано, перенесення запиту в минуле."""

    def __init__(self, portal: BlockingPortal, engine: AsyncEngine) -> None:
        self._portal = portal
        self._engine = engine

    def rows(self, sql: str, **params: object) -> Rows:
        async def run() -> Rows:
            async with self._engine.connect() as conn:
                found = await conn.execute(text(sql), params)
                return [tuple(row) for row in found.all()]

        return self._portal.call(run)

    def execute(self, sql: str) -> None:
        async def run() -> None:
            async with self._engine.begin() as conn:
                await conn.execute(text(sql))

        self._portal.call(run)

    def requested(self, email: str) -> list[datetime]:
        found = self.rows(
            "SELECT r.requested_at FROM source_refresh_requests r "
            "JOIN users u ON u.id = r.user_id WHERE u.email = :email ORDER BY r.requested_at",
            email=email,
        )
        return [row[0] for row in found]

    def pending(self) -> int:
        return int(
            self.rows(
                "SELECT count(*) FROM source_refresh_requests WHERE handled_at IS NULL"
            )[0][0]
        )

    def total(self) -> int:
        return int(self.rows("SELECT count(*) FROM source_refresh_requests")[0][0])


def ask(session: SourcesSession) -> httpx2.Response:
    return session.client.post("/sources/refresh", headers=session.csrf)


def at(moment: object) -> datetime | None:
    return datetime.fromisoformat(moment) if isinstance(moment, str) else None


def import_jobs(session: SourcesSession, *titles: str, company: str = "acme") -> None:
    """Компанія з вакансіями, імпортованими справжнім прогоном за порожнім профілем (беруться всі)."""
    session.company(company)
    scripts = registry([*Platform, *FeedSource], [])
    scripts[Platform.GREENHOUSE].postings[company] = [posting(t) for t in titles]
    session.refresh(scripts)


def only_keywords(
    session: SourcesSession, *words: str, exclude: tuple[str, ...] = ()
) -> None:
    body = {
        "title_keywords": list(words),
        "title_exclude": list(exclude),
        "stop_words": [],
    }
    assert (
        session.client.put(
            "/profile/rules", json=body, headers=session.csrf
        ).status_code
        == 200
    )


def numbers(session: SourcesSession) -> dict[str, int]:
    items = session.client.get("/jobs", params={"limit": 200}).json()["items"]
    return {str(item["title"]): int(item["job_id"]) for item in items}


def filtered(session: SourcesSession) -> list[dict[str, Any]]:
    response = session.client.get("/sources/filtered")
    assert response.status_code == 200, response.text
    return list(response.json())


def dismiss(session: SourcesSession, chosen: list[int]) -> httpx2.Response:
    return session.client.post(
        "/sources/filtered/dismiss", json={"numbers": chosen}, headers=session.csrf
    )


def visible_titles(session: SourcesSession) -> set[str]:
    return set(numbers(session))


# --- сесія й CSRF -----------------------------------------------------------------------------


def test_the_new_routes_require_a_session(sources_client: ClientFactory) -> None:
    client = sources_client()
    for method, path in (
        ("POST", "/sources/refresh"),
        ("GET", "/sources/filtered"),
        ("POST", "/sources/filtered/dismiss"),
    ):
        response = client.request(method, path)
        assert status_and_code(response) == (401, "not_authenticated"), (method, path)


def test_unsafe_requests_need_the_csrf_token_and_change_nothing(
    alice: SourcesSession, queries: Queries
) -> None:
    import_jobs(alice, "Product Manager")
    only_keywords(alice, "backend")
    chosen = [numbers(alice)["Product Manager"]]

    attempts = (
        alice.client.post("/sources/refresh"),
        alice.client.post("/sources/filtered/dismiss", json={"numbers": chosen}),
    )

    assert [status_and_code(r) for r in attempts] == [(403, "csrf_failed")] * 2
    assert queries.total() == 0
    assert [item["title"] for item in filtered(alice)] == ["Product Manager"]


# --- «Оновити зараз» --------------------------------------------------------------------------


def test_a_new_user_sees_two_requests_and_no_filtered_jobs(
    alice: SourcesSession,
) -> None:
    response = alice.listing()

    body = response.json()
    assert body.get("refresh") == {
        "limit": 2,
        "remaining": 2,
        "next_at": None,
        "last_run_at": None,
    }
    assert body.get("filtered_out_count") == 0


def test_the_first_request_is_accepted_and_queued(
    alice: SourcesSession, queries: Queries
) -> None:
    response = ask(alice)

    assert response.status_code == 202
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "limit": 2,
        "remaining": 1,
        "next_at": None,
        "last_run_at": None,
    }
    assert queries.pending() == 1


def test_the_second_request_is_accepted_and_says_when_the_next_one_frees_up(
    alice: SourcesSession, queries: Queries
) -> None:
    ask(alice)
    response = ask(alice)

    assert response.status_code == 202
    first = queries.requested("alice@example.com")[0]
    body = response.json()
    assert (body.get("limit"), body.get("remaining")) == (2, 0)
    assert at(body.get("next_at")) == first + timedelta(minutes=30)
    assert queries.pending() == 2


def test_the_third_request_is_429_refresh_limit_with_retry_after(
    alice: SourcesSession, queries: Queries
) -> None:
    ask(alice)
    ask(alice)

    third = ask(alice)

    assert (third.status_code, third.json().get("code")) == (429, "refresh_limit")
    assert third.json().get("message", "").startswith(LIMIT_MESSAGE)
    assert third.json().get("message", "").endswith(" (Мадрид).")
    assert 1 <= int(third.headers["retry-after"]) <= 30 * 60
    assert queries.total() == 2


def test_the_sources_list_shows_what_is_left_and_when_the_next_request_frees_up(
    alice: SourcesSession, queries: Queries
) -> None:
    ask(alice)
    ask(alice)
    assert queries.total() == 2

    refresh = alice.listing().json().get("refresh", {})

    first = queries.requested("alice@example.com")[0]
    assert (refresh.get("limit"), refresh.get("remaining")) == (2, 0)
    assert at(refresh.get("next_at")) == first + timedelta(minutes=30)


def test_a_request_is_available_again_when_the_oldest_is_older_than_30_minutes(
    alice: SourcesSession, queries: Queries
) -> None:
    ask(alice)
    ask(alice)
    queries.execute(
        "UPDATE source_refresh_requests SET requested_at = requested_at - interval '31 minutes' "
        "WHERE id = (SELECT min(id) FROM source_refresh_requests)"
    )

    response = ask(alice)

    assert response.status_code == 202
    assert response.json().get("remaining") == 0
    second = queries.requested("alice@example.com")[1]
    assert at(response.json().get("next_at")) == second + timedelta(minutes=30)


def test_requests_are_counted_per_user(
    alice: SourcesSession, bob: SourcesSession
) -> None:
    ask(alice)
    ask(alice)

    response = ask(bob)

    assert response.status_code == 202
    assert response.json().get("remaining") == 1
    assert bob.listing().json().get("refresh", {}).get("remaining") == 1


def test_a_real_run_marks_every_waiting_request_handled(
    alice: SourcesSession, bob: SourcesSession, queries: Queries
) -> None:
    ask(alice)
    ask(alice)
    ask(bob)
    assert queries.pending() == 3

    alice.refresh()

    assert queries.pending() == 0
    assert queries.total() == 3
    assert ask(alice).status_code == 429


def test_last_run_at_is_the_latest_run_of_my_sources_or_null(
    alice: SourcesSession, bob: SourcesSession
) -> None:
    alice.company("acme")
    fresh = {"limit": 2, "remaining": 2, "next_at": None, "last_run_at": None}
    assert alice.listing().json().get("refresh") == fresh

    alice.refresh()

    assert alice.listing().json().get("refresh") == fresh | {"last_run_at": RAN_AT}
    assert ask(alice).json() == {
        "limit": 2,
        "remaining": 1,
        "next_at": None,
        "last_run_at": RAN_AT,
    }
    assert bob.listing().json().get("refresh") == fresh


# --- вакансії, що вже не проходять фільтр ------------------------------------------------------


def test_filtered_lists_my_source_jobs_the_profile_no_longer_takes_with_reasons(
    alice: SourcesSession,
) -> None:
    import_jobs(
        alice, "Backend Engineer", "Product Manager", "Graduate Backend Engineer"
    )
    only_keywords(alice, "backend", exclude=("graduate",))
    found = numbers(alice)

    assert filtered(alice) == [
        {
            "number": found["Product Manager"],
            "title": "Product Manager",
            "company": "Acme",
            "reason": "title",
        },
        {
            "number": found["Graduate Backend Engineer"],
            "title": "Graduate Backend Engineer",
            "company": "Acme",
            "reason": "excluded",
        },
    ]


def test_filtered_out_count_in_the_sources_list_matches(alice: SourcesSession) -> None:
    import_jobs(alice, "Backend Engineer", "Product Manager", "Product Owner")
    only_keywords(alice, "backend")

    assert alice.listing().json().get("filtered_out_count") == 2


def test_filtered_is_private_and_skips_hidden_and_manual_jobs(
    alice: SourcesSession, bob: SourcesSession
) -> None:
    import_jobs(alice, "Product Manager", "Product Owner")
    only_keywords(alice, "backend")
    manual = alice.client.post(
        "/jobs",
        json={"text": "Опис вакансії Product Lead", "title": "Product Lead"},
        headers=alice.csrf,
    )
    assert manual.status_code == 201
    found = numbers(alice)
    hide = alice.client.post(
        "/jobs/dismiss",
        json={"job_ids": [found["Product Owner"]], "reason": "не цікаво"},
        headers=alice.csrf,
    )
    assert hide.status_code == 204

    assert [item["title"] for item in filtered(alice)] == ["Product Manager"]
    assert filtered(bob) == []


# --- приховати вибрані ------------------------------------------------------------------------


def test_dismissing_hides_the_chosen_with_the_profile_filter_reason(
    alice: SourcesSession,
) -> None:
    import_jobs(alice, "Backend Engineer", "Product Manager", "Product Owner")
    only_keywords(alice, "backend")
    found = numbers(alice)

    response = dismiss(alice, [found["Product Manager"], found["Product Owner"]])

    assert response.status_code == 200
    assert response.json() == {"dismissed": 2}
    assert visible_titles(alice) == {"Backend Engineer"}
    assert filtered(alice) == []
    assert alice.listing().json().get("filtered_out_count") == 0
    reason = alice.client.get("/jobs", params={"dismissed": True}).json()["items"]
    assert {item["title"] for item in reason} == {"Product Manager", "Product Owner"}
    details = alice.client.get(f"/jobs/{found['Product Manager']}").json()
    assert details["dismiss_reason"] == "фільтр профілю"


def test_dismissing_a_repeated_number_counts_it_once(alice: SourcesSession) -> None:
    import_jobs(alice, "Product Manager")
    only_keywords(alice, "backend")
    number = numbers(alice)["Product Manager"]

    response = dismiss(alice, [number, number])

    assert response.json() == {"dismissed": 1}


def test_a_number_outside_the_recalculated_list_is_409_and_nothing_is_hidden(
    alice: SourcesSession,
) -> None:
    import_jobs(alice, "Backend Engineer", "Product Manager")
    only_keywords(alice, "backend")
    found = numbers(alice)

    response = dismiss(alice, [found["Product Manager"], found["Backend Engineer"]])

    assert status_and_code(response) == (409, "filtered_changed")
    assert visible_titles(alice) == {"Backend Engineer", "Product Manager"}
    assert len(filtered(alice)) == 1


def test_a_profile_change_after_viewing_makes_the_old_choice_409(
    alice: SourcesSession,
) -> None:
    import_jobs(alice, "Data Engineer", "Product Manager")
    only_keywords(alice, "backend")
    seen = [item["number"] for item in filtered(alice)]
    only_keywords(alice, "data")

    response = dismiss(alice, seen)

    assert status_and_code(response) == (409, "filtered_changed")
    assert visible_titles(alice) == {"Data Engineer", "Product Manager"}


def test_another_users_job_cannot_be_hidden(
    alice: SourcesSession, bob: SourcesSession
) -> None:
    import_jobs(alice, "Product Manager")
    only_keywords(alice, "backend")
    only_keywords(bob, "backend")
    number = numbers(alice)["Product Manager"]

    response = dismiss(bob, [number])

    assert status_and_code(response) == (409, "filtered_changed")
    assert [item["title"] for item in filtered(alice)] == ["Product Manager"]


def test_an_empty_choice_is_422_at_numbers_with_nothing_to_hide(
    alice: SourcesSession,
) -> None:
    import_jobs(alice, "Product Manager")
    only_keywords(alice, "backend")

    response = dismiss(alice, [])

    assert status_and_code(response) == (422, "invalid_value")
    assert response.json()["field_errors"] == [
        {"field": "numbers", "message": "Нема що ховати."}
    ]
    assert len(filtered(alice)) == 1


@pytest.mark.parametrize("body", [{}, {"numbers": "1"}, {"numbers": [1], "extra": 1}])
def test_a_malformed_dismiss_body_is_422(alice: SourcesSession, body: object) -> None:
    response = alice.client.post(
        "/sources/filtered/dismiss", json=body, headers=alice.csrf
    )

    assert status_and_code(response) == (422, "invalid_request")
