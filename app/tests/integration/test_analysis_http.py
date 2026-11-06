"""Аналіз у HTTP: `GET /jobs/{id}/analysis`, застарілість після зміни профілю, поля й фільтр списку."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from domain.analysis.analysis import Gap, JobAnalysis
from domain.analysis.gap_answer import GapAnswer
from domain.analysis.ids import AnalysisId, GapAnswerId
from domain.facts.fact import FactKind, NewFact
from domain.facts.ids import FactId
from domain.identity.ids import UserId
from domain.profile.modes import Seniority, WorkMode
from infrastructure.db.unit_of_work import unit_of_work_factory
from tests.integration.test_jobs_http import JobsSession, alice, bob, make_client
from tests.integration.test_profile_http import SECTIONS

__all__ = ["alice", "bob", "make_client"]

SAVED_AT = datetime(2026, 3, 4, 5, 6, tzinfo=UTC)
FULL = JobAnalysis(
    score=77,
    summary="A backend role.",
    must_have=("Python",),
    nice_to_have=("Go",),
    keywords=("asyncio",),
    seniority=Seniority.SENIOR,
    work_mode=WorkMode.REMOTE,
    location="Madrid",
    languages=("English",),
    salary_min_eur=60000,
    salary_max_eur=80000,
    relocation=False,
    reasons=("Fits",),
    gaps=(Gap("No Go", "Do you have Go experience? Where, how long?"),),
)


class Analyst:
    """Зберігає аналіз напряму в сховищі (до HTTP аналіз приходить лише через MCP)."""

    def __init__(self, portal: BlockingPortal, engine: AsyncEngine, email: str) -> None:
        self._portal = portal
        self._engine = engine
        self._email = email

    def save(
        self,
        number: int,
        analysis: JobAnalysis = FULL,
        flags: tuple[str, ...] = (),
        when: datetime = SAVED_AT,
    ) -> None:
        async def run() -> None:
            async with self._engine.connect() as conn:
                row = await conn.execute(
                    text("SELECT id FROM users WHERE email = :email"),
                    {"email": self._email},
                )
                user = UserId(row.scalar_one())
            async with unit_of_work_factory(self._engine)() as tx:
                job = await tx.jobs.get(user, number)
                assert job is not None
                await tx.analyses.save(
                    user, AnalysisId(uuid4()), job.id, analysis, flags, when
                )
                await tx.commit()

        self._portal.call(run)

    def answer(self, number: int, gap: str, *fact_texts: str) -> list[int]:
        """Відповідь на прогалину: з текстами фактів — «є досвід», без них — «нема досвіду».
        Віддає номери створених фактів."""

        async def run() -> list[int]:
            async with self._engine.connect() as conn:
                row = await conn.execute(
                    text("SELECT id FROM users WHERE email = :email"),
                    {"email": self._email},
                )
                user = UserId(row.scalar_one())
            async with unit_of_work_factory(self._engine)() as tx:
                job = await tx.jobs.get(user, number)
                assert job is not None
                numbers = [
                    (
                        await tx.facts.add(
                            user,
                            FactId(uuid4()),
                            NewFact(FactKind.SKILL, body),
                            SAVED_AT,
                        )
                    ).number
                    for body in fact_texts
                ]
                await tx.gap_answers.save(
                    user,
                    GapAnswerId(uuid4()),
                    job.id,
                    GapAnswer(gap, bool(numbers), tuple(numbers), SAVED_AT),
                )
                await tx.commit()
                return numbers

        return self._portal.call(run)


@pytest.fixture
def alice_analyst(portal: BlockingPortal, engine: AsyncEngine) -> Analyst:
    return Analyst(portal, engine, "alice@example.com")


@pytest.fixture
def bob_analyst(portal: BlockingPortal, engine: AsyncEngine) -> Analyst:
    return Analyst(portal, engine, "bob@example.com")


def analysis_of(session: JobsSession, number: int) -> Any:
    return session.client.get(f"/jobs/{number}/analysis")


def test_the_analysis_requires_a_session(make_client: Any) -> None:
    response = make_client().get("/jobs/1/analysis")
    assert (response.status_code, response.json()["code"]) == (401, "not_authenticated")


def test_a_job_without_analysis_is_404(alice: JobsSession) -> None:
    alice.add()
    assert analysis_of(alice, 1).status_code == 404


def test_a_missing_job_is_404(alice: JobsSession) -> None:
    assert analysis_of(alice, 99).status_code == 404
    assert analysis_of(alice, 10**30).status_code == 404


def test_the_analysis_has_every_field_the_flags_and_no_stale_mark(
    alice: JobsSession, alice_analyst: Analyst
) -> None:
    alice.add()
    flags = ("Формат remote — не з профілю.",)
    alice_analyst.save(1, FULL, flags)
    response = analysis_of(alice, 1)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "job_id": 1,
        "score": 77,
        "summary": "A backend role.",
        "must_have": ["Python"],
        "nice_to_have": ["Go"],
        "keywords": ["asyncio"],
        "seniority": "senior",
        "work_mode": "remote",
        "location": "Madrid",
        "languages": ["English"],
        "salary_min_eur": 60000,
        "salary_max_eur": 80000,
        "relocation": False,
        "reasons": ["Fits"],
        "gaps": [
            {
                "number": 1,
                "gap": "No Go",
                "question": "Do you have Go experience? Where, how long?",
                "status": "open",
                "fact_ids": [],
            }
        ],
        "filters_passed": False,
        "flags": list(flags),
        "updated_at": "2026-03-04T05:06:00Z",
        "stale_since": None,
    }


def test_gaps_come_back_numbered_from_1_in_order_with_their_questions(
    alice: JobsSession, alice_analyst: Analyst
) -> None:
    alice.add()
    gaps = (Gap("Kubernetes", "Have you run it? Where?"), Gap("Go", "Written Go?"))
    alice_analyst.save(1, JobAnalysis(score=1, summary="s", gaps=gaps))
    assert analysis_of(alice, 1).json()["gaps"] == [
        {
            "number": 1,
            "gap": "Kubernetes",
            "question": "Have you run it? Where?",
            "status": "open",
            "fact_ids": [],
        },
        {
            "number": 2,
            "gap": "Go",
            "question": "Written Go?",
            "status": "open",
            "fact_ids": [],
        },
    ]


def test_an_analysis_stored_with_string_gaps_has_null_questions(
    alice: JobsSession,
    alice_analyst: Analyst,
    portal: BlockingPortal,
    engine: AsyncEngine,
) -> None:
    alice.add()
    alice_analyst.save(1, JobAnalysis(score=1, summary="s"))

    async def legacy() -> None:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE job_analyses SET details = jsonb_set(details, '{gaps}', "
                    """'["Old gap", "Another"]'::jsonb)"""
                )
            )

    portal.call(legacy)
    assert analysis_of(alice, 1).json()["gaps"] == [
        {
            "number": 1,
            "gap": "Old gap",
            "question": None,
            "status": "open",
            "fact_ids": [],
        },
        {
            "number": 2,
            "gap": "Another",
            "question": None,
            "status": "open",
            "fact_ids": [],
        },
    ]


def test_a_gap_closed_with_facts_comes_back_closed_with_the_fact_ids(
    alice: JobsSession, alice_analyst: Analyst
) -> None:
    alice.add()
    alice_analyst.save(1)
    numbers = alice_analyst.answer(1, "No Go", "2 years of Go at Acme", "Go in prod")

    [gap] = analysis_of(alice, 1).json()["gaps"]

    assert (gap["status"], gap["fact_ids"]) == ("closed", numbers)
    assert len(numbers) == 2


def test_a_gap_answered_with_no_experience_comes_back_with_no_facts(
    alice: JobsSession, alice_analyst: Analyst
) -> None:
    alice.add()
    alice_analyst.save(1)
    alice_analyst.answer(1, "No Go")

    [gap] = analysis_of(alice, 1).json()["gaps"]

    assert (gap["status"], gap["fact_ids"]) == ("no_experience", [])


def test_only_the_answered_gap_changes_status(
    alice: JobsSession, alice_analyst: Analyst
) -> None:
    alice.add()
    gaps = (Gap("Kubernetes", "Run it?"), Gap("Go", "Written Go?"))
    alice_analyst.save(1, JobAnalysis(score=1, summary="s", gaps=gaps))
    alice_analyst.answer(1, "go")

    statuses = [gap["status"] for gap in analysis_of(alice, 1).json()["gaps"]]

    assert statuses == ["open", "no_experience"]


def test_the_answers_of_another_user_are_not_shown(
    alice: JobsSession,
    bob: JobsSession,
    alice_analyst: Analyst,
    bob_analyst: Analyst,
) -> None:
    alice.add()
    bob.add()
    alice_analyst.save(1)
    bob_analyst.save(1)
    bob_analyst.answer(1, "No Go")

    [gap] = analysis_of(alice, 1).json()["gaps"]

    assert (gap["status"], gap["fact_ids"]) == ("open", [])


def test_nothing_stated_comes_back_as_nulls_and_empty_lists(
    alice: JobsSession, alice_analyst: Analyst
) -> None:
    alice.add()
    alice_analyst.save(1, JobAnalysis(score=0, summary="Thin."))
    body = analysis_of(alice, 1).json()
    assert body["score"] == 0
    assert (
        body["seniority"],
        body["work_mode"],
        body["location"],
        body["relocation"],
    ) == (
        None,
        None,
        None,
        None,
    )
    assert (body["must_have"], body["gaps"], body["flags"]) == ([], [], [])
    assert body["filters_passed"] is True


def test_a_profile_change_after_the_analysis_marks_it_stale(
    alice: JobsSession, alice_analyst: Analyst
) -> None:
    alice.add()
    alice_analyst.save(1, when=datetime(2020, 1, 1, tzinfo=UTC))
    saved = alice.client.put(
        "/profile/target", json=SECTIONS["target"], headers=alice.csrf
    )
    assert saved.status_code == 200
    stale = analysis_of(alice, 1).json()["stale_since"]
    assert stale is not None
    assert stale.endswith(("Z", "+00:00"))
    assert datetime.fromisoformat(stale).year >= 2026


def test_contacts_and_unchanged_sections_do_not_move_the_change_time(
    alice: JobsSession, portal: BlockingPortal, engine: AsyncEngine
) -> None:
    async def changed_at() -> object:
        async with engine.connect() as conn:
            row = await conn.execute(
                text("SELECT analysis_inputs_changed_at FROM profiles")
            )
            return row.scalar_one()

    alice.client.put("/profile/target", json=SECTIONS["target"], headers=alice.csrf)
    first = portal.call(changed_at)
    assert first is not None
    alice.client.put("/profile/target", json=SECTIONS["target"], headers=alice.csrf)
    alice.client.put("/profile/contacts", json=SECTIONS["contacts"], headers=alice.csrf)
    assert portal.call(changed_at) == first


def test_a_user_does_not_see_the_analysis_of_another(
    alice: JobsSession, bob: JobsSession, alice_analyst: Analyst
) -> None:
    alice.add()
    bob.add()
    alice_analyst.save(1)
    assert analysis_of(bob, 1).status_code == 404
    assert bob.listing().json()["items"][0]["score"] is None


def test_the_list_item_carries_score_filters_and_work_mode(
    alice: JobsSession, alice_analyst: Analyst
) -> None:
    alice.add()
    alice_analyst.save(1, FULL, ("f",))
    [item] = alice.listing().json()["items"]
    assert (item["score"], item["filters_passed"], item["work_mode"]) == (
        77,
        False,
        "remote",
    )


def test_the_list_is_ordered_analysed_first_by_filters_then_score(
    alice: JobsSession, alice_analyst: Analyst
) -> None:
    for body in ("plain", "failed", "low", "high"):
        alice.add(text=body)
    alice_analyst.save(2, JobAnalysis(99, "s"), ("f",))
    alice_analyst.save(3, JobAnalysis(40, "s"))
    alice_analyst.save(4, JobAnalysis(85, "s"))
    assert alice.numbers() == [4, 3, 2, 1]


def test_the_work_mode_filter_keeps_only_analysed_jobs_of_that_mode(
    alice: JobsSession, alice_analyst: Analyst
) -> None:
    for body in ("remote", "onsite", "plain"):
        alice.add(text=body)
    alice_analyst.save(1, JobAnalysis(1, "s", work_mode=WorkMode.REMOTE))
    alice_analyst.save(2, JobAnalysis(1, "s", work_mode=WorkMode.ONSITE))
    assert alice.numbers(work_mode="remote") == [1]
    assert alice.numbers(work_mode="hybrid") == []


def test_an_unknown_work_mode_filter_is_a_422_on_the_field(alice: JobsSession) -> None:
    response = alice.listing(work_mode="office")
    assert response.status_code == 422
    assert [(e["field"], e["message"]) for e in response.json()["field_errors"]] == [
        ("work_mode", "Невідомий формат роботи.")
    ]
