"""Етапи вакансій для табів вебу через HTTP наскрізь: відкриті, у процесі, подані; відмови зникають
із вебу; лічильники табів не залежать від фільтрів і ліміту."""

import itertools
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.jobs.job import NewJob
from infrastructure.db.unit_of_work import unit_of_work_factory
from tests.integration.test_jobs_http import (
    ALERT_LINK,
    JobsSession,
    alice,
    bob,
    field_errors,
)
from tests.integration.test_profile_http import make_client

__all__ = ["alice", "bob", "make_client"]

NO_COUNTS = {"in_progress": 0, "applied_unreviewed": 0, "needs_text": False}
ACTIVE = ["applied", "replied", "interview", "offer"]


class Seeds:
    """Рядки напряму в таблиці: вакансії тут створює HTTP, а взаємодії (аналіз, документи …) — SQL."""

    def __init__(
        self,
        portal: BlockingPortal,
        engine: AsyncEngine,
        session: JobsSession,
        email: str,
    ) -> None:
        self._portal = portal
        self._engine = engine
        self._session = session
        self._email = email
        self._seq = itertools.count(1)

    def run(self, sql: str, **params: Any) -> Any:
        async def execute() -> Any:
            async with self._engine.begin() as conn:
                result = await conn.execute(text(sql), params)
                return result.first() if result.returns_rows else None

        return self._portal.call(execute)

    def ids(self, number: int) -> dict[str, Any]:
        row = self.run(
            "SELECT j.id AS job, j.user_id AS usr FROM jobs j "
            "JOIN users u ON u.id = j.user_id "
            "WHERE u.email = :email AND j.job_number = :number",
            email=self._email,
            number=number,
        )
        return {"job": row.job, "usr": row.usr, "n": next(self._seq), "id": uuid4()}

    def waiting_job(self, linkedin_id: str = "4012345678") -> int:
        """Вакансія з листа-алерту: без тексту."""

        async def seed() -> int:
            async with self._engine.connect() as conn:
                row = await conn.execute(
                    text("SELECT id FROM users WHERE email = :email"),
                    {"email": self._email},
                )
                user_id = UserId(row.scalar_one())
            async with unit_of_work_factory(self._engine)() as tx:
                number = await tx.jobs.add(
                    user_id,
                    JobId(uuid4()),
                    NewJob(
                        text=None,
                        url=f"https://www.linkedin.com/jobs/view/{linkedin_id}",
                        title="Backend Dev",
                        company="Acme",
                        linkedin_id=linkedin_id,
                        source="linkedin_alert",
                    ),
                    datetime.now(UTC),
                )
                await tx.commit()
                return number

        return self._portal.call(seed)

    def triage(self, number: int, verdict: str) -> None:
        self.run(
            "INSERT INTO job_triage (id, user_id, job_id, score, verdict, reason, "
            "triaged_at) VALUES (:id, :usr, :job, 50, :verdict, 'r', now())",
            verdict=verdict,
            **self.ids(number),
        )

    def analysis(self, number: int) -> None:
        self.run(
            "INSERT INTO job_analyses (id, user_id, job_id, score, filters_passed, "
            "details, updated_at) VALUES (:id, :usr, :job, 70, true, "
            "CAST('{}' AS jsonb), now())",
            **self.ids(number),
        )

    def document(self, number: int, kind: str) -> None:
        self.run(
            "INSERT INTO documents (id, user_id, document_number, job_id, kind, "
            "version, content, created_at) VALUES (:id, :usr, :n, :job, :kind, 1, "
            "CAST('{}' AS jsonb), now())",
            kind=kind,
            **self.ids(number),
        )

    def kit(self, number: int) -> None:
        self.run(
            "INSERT INTO interview_kits (id, user_id, kit_number, job_id, version, "
            "content, created_at) VALUES (:id, :usr, :n, :job, 1, "
            "CAST('{}' AS jsonb), now())",
            **self.ids(number),
        )

    def prep_topic(self, number: int) -> None:
        ids = self.ids(number)
        self.run(
            "INSERT INTO prep_topics (id, user_id, topic_number, slug, title, kind, "
            "created_at) VALUES (:id, :usr, :n, 'topic', 'Topic', 'tech', now())",
            **ids,
        )
        self.run(
            "INSERT INTO prep_topic_jobs (topic_id, job_id, gap) "
            "VALUES (:id, :job, 'gap')",
            **ids,
        )

    def fact(self, number: int) -> None:
        self.run(
            "INSERT INTO facts (id, user_id, fact_number, kind, text, text_hash, "
            "created_at, updated_at, job_id) VALUES (:id, :usr, :n, 'skill', "
            "'Rust', :hash, now(), now(), :job)",
            hash=f"hash-{number}",
            **self.ids(number),
        )

    def general_fact(self, number: int) -> None:
        """Факт без вакансії: до жодної вакансії не належить."""
        self.run(
            "INSERT INTO facts (id, user_id, fact_number, kind, text, text_hash, "
            "created_at, updated_at) VALUES (:id, :usr, :n, 'skill', 'Go', :hash, "
            "now(), now())",
            hash=f"general-{number}",
            **self.ids(number),
        )

    def reply(self, number: int | None, *, reviewed: bool = False) -> None:
        """Лист компанії; `number` None — лист не зіставлено з вакансією."""
        mail = self.run(
            "INSERT INTO mail_messages (user_id, gmail_id, received_at, category, "
            "attachments) VALUES ((SELECT id FROM users WHERE email = :email), :gmail, "
            "now(), 'company', CAST('[]' AS jsonb)) RETURNING id",
            email=self._email,
            gmail=f"gmail-{uuid4()}",
        )
        job: UUID | None = None if number is None else self.ids(number)["job"]
        self.run(
            "INSERT INTO job_replies (user_id, mail_id, job_id, suggested_type, "
            "reviewed_at) VALUES ((SELECT id FROM users WHERE email = :email), :mail, "
            ":job, 'other', CASE WHEN :reviewed THEN now() END)",
            email=self._email,
            mail=mail.id,
            job=job,
            reviewed=reviewed,
        )


SeedsFactory = Callable[[JobsSession, str], Seeds]


@pytest.fixture
def seeds_for(portal: BlockingPortal, engine: AsyncEngine) -> SeedsFactory:
    return lambda session, email: Seeds(portal, engine, session, email)


@pytest.fixture
def seed(alice: JobsSession, seeds_for: SeedsFactory) -> Seeds:
    return seeds_for(alice, "alice@example.com")


def apply(session: JobsSession, number: int, *moves: str) -> None:
    """Подача на вакансію і далі за статусами по черзі."""
    response = session.client.put(
        f"/jobs/{number}/application", json={"channel": "email"}, headers=session.csrf
    )
    assert response.status_code == 200
    for status in moves:
        moved = session.client.post(
            f"/jobs/{number}/application/status",
            json={"status": status},
            headers=session.csrf,
        )
        assert moved.status_code == 200, moved.text


def counts(session: JobsSession, **query: object) -> Any:
    return session.listing(**query).json().get("counts")


def counted(session: JobsSession, key: str, **query: object) -> Any:
    """Одне поле лічильників; нема лічильників — None, щоб тест падав на порівнянні."""
    return (counts(session, **query) or {}).get(key)


def unreviewed(session: JobsSession) -> Any:
    """`applied_unreviewed` — саме число, не прапорець (True == 1 у Python)."""
    value = counted(session, "applied_unreviewed")
    assert type(value) is int, value
    return value


def test_a_job_with_text_and_no_interaction_is_open(
    alice: JobsSession,
) -> None:
    alice.add(text="manual posting")
    assert alice.numbers(stage="open") == [1]
    assert alice.numbers(stage="in_progress") == []
    assert alice.numbers(stage="applied") == []


@pytest.mark.parametrize("verdict", ["analyse", "maybe", "skip"])
def test_a_triaged_job_stays_open_whatever_the_verdict(
    alice: JobsSession, seed: Seeds, verdict: str
) -> None:
    alice.add(text="triaged posting")
    seed.triage(1, verdict)
    assert alice.numbers(stage="open") == [1]
    assert alice.numbers(stage="in_progress") == []


def test_opening_the_details_keeps_a_job_open(alice: JobsSession) -> None:
    alice.add(text="to be opened")
    assert alice.get(1).status_code == 200
    assert alice.numbers(stage="open") == [1]
    assert alice.numbers(stage="in_progress") == []


def test_a_linkedin_alert_job_without_text_is_only_in_needs_text(
    alice: JobsSession, seed: Seeds
) -> None:
    seed.waiting_job()
    assert alice.numbers(stage="open") == []
    assert alice.numbers(stage="in_progress") == []
    assert alice.numbers(stage="applied") == []
    assert alice.numbers(needs_text="true") == [1]


def test_the_same_alert_job_after_its_text_was_added_is_open(
    alice: JobsSession, seed: Seeds
) -> None:
    seed.waiting_job()
    assert alice.add(url=ALERT_LINK).json()["outcome"] == "text_added"
    assert alice.numbers(stage="open") == [1]
    assert alice.numbers(stage="in_progress") == []
    assert alice.numbers(needs_text="true") == []


@pytest.mark.parametrize(
    "interaction",
    ["analysis", "cv", "cover_letter", "interview_kit", "prep_topic", "fact"],
)
def test_each_kind_of_interaction_moves_a_job_to_in_progress(
    alice: JobsSession, seed: Seeds, interaction: str
) -> None:
    alice.add(text="worked on")
    {
        "analysis": lambda: seed.analysis(1),
        "cv": lambda: seed.document(1, "cv"),
        "cover_letter": lambda: seed.document(1, "cl"),
        "interview_kit": lambda: seed.kit(1),
        "prep_topic": lambda: seed.prep_topic(1),
        "fact": lambda: seed.fact(1),
    }[interaction]()
    assert alice.numbers(stage="in_progress") == [1]
    assert alice.numbers(stage="open") == []
    assert alice.numbers(stage="applied") == []


def test_a_fact_without_a_job_is_no_interaction_with_any_job(
    alice: JobsSession, seed: Seeds
) -> None:
    alice.add(text="untouched")
    seed.general_fact(1)
    assert alice.numbers(stage="open") == [1]
    assert alice.numbers(stage="in_progress") == []


def test_a_job_with_an_application_and_an_analysis_is_applied_only(
    alice: JobsSession, seed: Seeds
) -> None:
    alice.add(text="applied after analysis")
    seed.analysis(1)
    apply(alice, 1)
    assert alice.numbers(stage="applied") == [1]
    assert alice.numbers(stage="in_progress") == []
    assert alice.numbers(stage="open") == []


@pytest.mark.parametrize("status", ACTIVE)
def test_every_active_status_is_applied(alice: JobsSession, status: str) -> None:
    alice.add(text="in the funnel")
    apply(alice, 1, *([] if status == "applied" else [status]))
    assert alice.numbers(stage="applied") == [1]
    assert alice.numbers(stage="in_progress") == []
    assert alice.numbers(stage="open") == []


def test_a_withdrawn_application_is_in_progress_and_not_applied(
    alice: JobsSession,
) -> None:
    alice.add(text="withdrawn later")
    apply(alice, 1, "withdrawn")
    assert alice.numbers(stage="in_progress") == [1]
    assert alice.numbers(stage="applied") == []
    assert alice.numbers(stage="open") == []


def test_a_rejected_application_is_in_no_stage_even_when_searched_for(
    alice: JobsSession,
) -> None:
    alice.add(text="rejected posting", title="Unique Title")
    apply(alice, 1, "rejected")
    for stage in ("open", "in_progress", "applied"):
        assert alice.numbers(stage=stage) == [], stage
    assert alice.numbers(query="unique") == []
    assert alice.numbers(stage="applied", query="unique") == []
    assert alice.numbers(status="rejected") == []
    assert alice.numbers() == []


def test_a_rejected_job_stays_reachable_by_its_direct_link(
    alice: JobsSession,
) -> None:
    alice.add(text="rejected posting")
    apply(alice, 1, "rejected")
    assert alice.get(1).status_code == 200
    application = alice.client.get("/jobs/1/application")
    assert application.json()["status"] == "rejected"


def test_a_rejected_job_without_text_is_also_hidden_from_needs_text(
    alice: JobsSession, seed: Seeds
) -> None:
    seed.waiting_job()
    apply(alice, 1, "rejected")
    assert alice.numbers(needs_text="true") == []
    assert counted(alice, "needs_text") is False


def test_a_dismissed_job_with_an_interaction_is_only_in_the_dismissed_list(
    alice: JobsSession, seed: Seeds
) -> None:
    alice.add(text="worked on, then dropped")
    seed.analysis(1)
    assert alice.dismiss([1]).status_code == 204
    for stage in ("open", "in_progress", "applied"):
        assert alice.numbers(stage=stage) == [], stage
    assert alice.numbers(dismissed="true") == [1]
    assert counted(alice, "in_progress") == 0


def test_the_stage_combines_with_the_status_filter(alice: JobsSession) -> None:
    alice.add(text="first")
    alice.add(text="second")
    alice.add(text="third, never applied")
    apply(alice, 1)
    apply(alice, 2, "replied")
    assert sorted(alice.numbers(stage="applied")) == [1, 2]
    assert alice.numbers(stage="applied", status="replied") == [2]


def test_without_a_stage_the_list_still_has_every_job_that_is_not_rejected(
    alice: JobsSession, seed: Seeds
) -> None:
    alice.add(text="open one")
    alice.add(text="worked one")
    alice.add(text="applied one")
    alice.add(text="rejected one")
    seed.analysis(2)
    apply(alice, 3)
    apply(alice, 4, "rejected")
    assert sorted(alice.numbers()) == [1, 2, 3]


def test_an_unknown_stage_is_422(alice: JobsSession) -> None:
    response = alice.listing(stage="all")
    assert response.status_code == 422
    assert field_errors(response) == [
        ("stage", "Етап — один з: open, in_progress, applied.")
    ]


def test_a_new_user_has_no_tab_counts(alice: JobsSession) -> None:
    assert counts(alice) == NO_COUNTS


def test_the_in_progress_count_ignores_the_query_filters(
    alice: JobsSession, seed: Seeds
) -> None:
    for title in ("Alpha", "Beta", "Gamma"):
        alice.add(text=f"{title} posting", title=title)
    for number in (1, 2, 3):
        seed.analysis(number)
    assert counted(alice, "in_progress", stage="open", query="zzz-no-match") == 3
    assert counted(alice, "in_progress", stage="in_progress", query="alpha") == 3
    assert counted(alice, "in_progress", source="other", days="1") == 3


def test_the_in_progress_count_is_not_cut_by_the_list_limit(
    alice: JobsSession, seed: Seeds
) -> None:
    for number in (1, 2, 3):
        alice.add(text=f"posting {number}")
        seed.analysis(number)
    response = alice.listing(stage="in_progress", limit=1)
    assert len(response.json()["items"]) == 1
    assert counted(alice, "in_progress", stage="in_progress", limit=1) == 3


def test_the_in_progress_count_includes_withdrawn_and_excludes_the_rest(
    alice: JobsSession, seed: Seeds
) -> None:
    for number in range(1, 6):
        alice.add(text=f"posting {number}")
    seed.analysis(1)  # у процесі
    apply(alice, 2, "withdrawn")  # у процесі
    apply(alice, 3)  # подано
    apply(alice, 4, "rejected")  # відмова
    # 5 — відкрита
    assert counted(alice, "in_progress") == 2


@pytest.mark.parametrize("status", ACTIVE)
def test_an_unreviewed_reply_on_an_active_application_raises_the_applied_flag(
    alice: JobsSession, seed: Seeds, status: str
) -> None:
    alice.add(text="waiting for a reply")
    apply(alice, 1, *([] if status == "applied" else [status]))
    seed.reply(1)
    assert unreviewed(alice) == 1


def test_unreviewed_replies_are_counted_per_job(
    alice: JobsSession, seed: Seeds
) -> None:
    for number in (1, 2, 3):
        alice.add(text=f"posting {number}")
        apply(alice, number)
    seed.reply(1)
    seed.reply(2)
    seed.reply(3, reviewed=True)
    assert unreviewed(alice) == 2


def test_several_unreviewed_replies_on_one_job_count_once(
    alice: JobsSession, seed: Seeds
) -> None:
    alice.add(text="chatty company")
    apply(alice, 1)
    for _ in range(3):
        seed.reply(1)
    assert unreviewed(alice) == 1


def test_a_reviewed_reply_does_not_raise_the_applied_flag(
    alice: JobsSession, seed: Seeds
) -> None:
    alice.add(text="answered")
    apply(alice, 1)
    seed.reply(1, reviewed=True)
    assert unreviewed(alice) == 0


def test_an_unmatched_reply_does_not_raise_the_applied_flag(
    alice: JobsSession, seed: Seeds
) -> None:
    alice.add(text="applied")
    apply(alice, 1)
    seed.reply(None)
    assert unreviewed(alice) == 0


@pytest.mark.parametrize("closing", ["rejected", "withdrawn"])
def test_a_reply_on_a_closed_application_does_not_raise_the_applied_flag(
    alice: JobsSession, seed: Seeds, closing: str
) -> None:
    alice.add(text="closed")
    apply(alice, 1, closing)
    seed.reply(1)
    assert unreviewed(alice) == 0


def test_a_reply_on_a_job_without_application_does_not_raise_the_applied_flag(
    alice: JobsSession, seed: Seeds
) -> None:
    alice.add(text="never applied")
    seed.reply(1)
    assert unreviewed(alice) == 0


def test_the_needs_text_flag_follows_the_needs_text_tab(
    alice: JobsSession, seed: Seeds
) -> None:
    alice.add(text="has text")
    assert counted(alice, "needs_text") is False
    seed.waiting_job()
    assert counted(alice, "needs_text") is True
    assert alice.numbers(needs_text="true") == [2]
    assert alice.add(url=ALERT_LINK).json()["outcome"] == "text_added"
    assert counted(alice, "needs_text") is False
    assert alice.numbers(needs_text="true") == []


def test_a_dismissed_job_without_text_does_not_raise_the_needs_text_flag(
    alice: JobsSession, seed: Seeds
) -> None:
    seed.waiting_job()
    assert alice.dismiss([1]).status_code == 204
    assert counted(alice, "needs_text") is False


def test_the_tab_counts_do_not_depend_on_the_tab_being_listed(
    alice: JobsSession, seed: Seeds
) -> None:
    alice.add(text="worked on")
    seed.analysis(1)
    seed.waiting_job()
    expected = {"in_progress": 1, "applied_unreviewed": 0, "needs_text": True}
    for query in ({}, {"stage": "open"}, {"stage": "applied"}, {"dismissed": "true"}):
        assert counts(alice, **query) == expected, query


def test_the_data_of_another_user_does_not_change_the_counts(
    alice: JobsSession,
    bob: JobsSession,
    seeds_for: SeedsFactory,
) -> None:
    theirs = seeds_for(bob, "bob@example.com")
    bob.add(text="bob's worked job")
    theirs.analysis(1)
    apply(bob, 1)
    theirs.reply(1)
    theirs.waiting_job()
    bob.add(text="bob's second worked job")
    theirs.kit(3)
    assert counts(bob) == {
        "in_progress": 1,
        "applied_unreviewed": 1,
        "needs_text": True,
    }
    assert counts(alice) == NO_COUNTS
    assert alice.numbers(stage="in_progress") == []
    assert alice.numbers(stage="applied") == []
