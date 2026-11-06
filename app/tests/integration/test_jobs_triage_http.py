"""Тріаж у HTTP вакансій: поля списку й деталей, фільтр за вердиктом, порядок, ізоляція користувачів."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.triage.ids import TriageId
from domain.triage.triage import TriageEntry, TriageVerdict
from infrastructure.db.unit_of_work import unit_of_work_factory
from tests.integration.test_jobs_http import JobsSession, alice, bob, make_client

__all__ = ["alice", "bob", "make_client"]


class Triager:
    """Тріажить вакансії користувача напряму в сховищі (до HTTP тріаж приходить лише через MCP)."""

    def __init__(self, portal: BlockingPortal, engine: AsyncEngine, email: str) -> None:
        self._portal = portal
        self._engine = engine
        self._email = email

    def save(
        self,
        number: int,
        score: int,
        verdict: TriageVerdict,
        reason: str = "r",
        by_rules: bool = False,
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
                when = datetime(2026, 3, 4, 5, 6, tzinfo=UTC)
                entry = TriageEntry(number, score, verdict, reason)
                if by_rules:
                    await tx.triage.save_auto(
                        user,
                        [(TriageId(uuid4()), JobId(job.id.value), entry, "hash")],
                        when,
                    )
                else:
                    await tx.triage.save(
                        user, [(TriageId(uuid4()), JobId(job.id.value), entry)], when
                    )
                await tx.commit()

        self._portal.call(run)


@pytest.fixture
def alice_triage(portal: BlockingPortal, engine: AsyncEngine) -> Triager:
    return Triager(portal, engine, "alice@example.com")


def test_an_untriaged_job_has_empty_triage_fields_in_the_list_and_details(
    alice: JobsSession,
) -> None:
    alice.add()
    [item] = alice.listing().json()["items"]
    assert (item["triage_score"], item["triage_verdict"], item["triage_reason"]) == (
        None,
        None,
        None,
    )
    assert alice.get(1).json()["triage"] is None


def test_the_list_item_carries_score_verdict_and_reason(
    alice: JobsSession, alice_triage: Triager
) -> None:
    alice.add()
    alice_triage.save(1, 33, TriageVerdict.SKIP, "Onsite Berlin")
    [item] = alice.listing().json()["items"]
    assert (item["triage_score"], item["triage_verdict"], item["triage_reason"]) == (
        33,
        "skip",
        "Onsite Berlin",
    )


def test_the_details_carry_the_whole_triage(
    alice: JobsSession, alice_triage: Triager
) -> None:
    alice.add()
    alice_triage.save(1, 72, TriageVerdict.ANALYSE, "Remote Python")
    assert alice.get(1).json()["triage"] == {
        "score": 72,
        "verdict": "analyse",
        "reason": "Remote Python",
        "triaged_at": "2026-03-04T05:06:00Z",
        "source": "agent",
    }


def test_the_details_triage_of_the_cron_says_rules(
    alice: JobsSession, alice_triage: Triager
) -> None:
    alice.add()
    alice_triage.save(1, 45, TriageVerdict.MAYBE, "Невпевнено", by_rules=True)
    assert alice.get(1).json()["triage"]["source"] == "rules"


def test_the_list_is_ordered_by_triage_and_a_skip_stays_visible(
    alice: JobsSession, alice_triage: Triager
) -> None:
    for body in ("plain", "skip", "maybe", "analyse"):
        alice.add(text=body)
    alice_triage.save(2, 99, TriageVerdict.SKIP)
    alice_triage.save(3, 10, TriageVerdict.MAYBE)
    alice_triage.save(4, 1, TriageVerdict.ANALYSE)
    assert alice.numbers() == [4, 3, 2, 1]


@pytest.mark.parametrize("verdict", ["analyse", "maybe", "skip"])
def test_the_verdict_filter_keeps_only_that_verdict(
    alice: JobsSession, alice_triage: Triager, verdict: str
) -> None:
    for body in ("one", "two", "three", "four"):
        alice.add(text=body)
    alice_triage.save(1, 50, TriageVerdict.ANALYSE)
    alice_triage.save(2, 50, TriageVerdict.MAYBE)
    alice_triage.save(3, 50, TriageVerdict.SKIP)
    expected = {"analyse": [1], "maybe": [2], "skip": [3]}[verdict]
    assert alice.numbers(triage_verdict=verdict) == expected


def test_an_unknown_verdict_filter_is_a_422_on_the_field(alice: JobsSession) -> None:
    response = alice.listing(triage_verdict="great")
    assert response.status_code == 422
    assert [(e["field"], e["message"]) for e in response.json()["field_errors"]] == [
        ("triage_verdict", "Невідомий вердикт тріажу.")
    ]


def test_a_user_does_not_see_the_triage_of_another(
    alice: JobsSession, bob: JobsSession, alice_triage: Triager
) -> None:
    alice.add()
    bob.add()
    alice_triage.save(1, 90, TriageVerdict.ANALYSE)
    [item] = bob.listing().json()["items"]
    assert item["triage_verdict"] is None
    assert bob.get(1).json()["triage"] is None
