"""PostgresGapAnswers і факт з номером вакансії на справжній базі."""

from datetime import timedelta
from uuid import UUID

from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from domain.analysis.gap_answer import GapAnswer
from domain.analysis.ids import GapAnswerId
from domain.facts.fact import Fact, FactKind, FactSource, NewFact
from domain.facts.ids import FactId
from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from infrastructure.db.unit_of_work import UnitOfWorkFactory
from tests.integration.test_jobs_repository import ALICE, BOB, NOW, posting, uow

__all__ = ["uow"]

_ids = iter(range(1, 10_000))


def _id() -> UUID:
    return UUID(int=0xF000 + next(_ids))


async def _job(uow: UnitOfWorkFactory, user: UserId, body: str = "job") -> JobId:
    job_id = JobId(_id())
    async with uow() as tx:
        await tx.jobs.add(user, job_id, posting(body), NOW)
        await tx.commit()
    return job_id


async def _fact(uow: UnitOfWorkFactory, user: UserId, body: str) -> int:
    async with uow() as tx:
        fact = await tx.facts.add(
            user, FactId(_id()), NewFact(FactKind.SKILL, body), NOW
        )
        await tx.commit()
    return fact.number


async def _save(
    uow: UnitOfWorkFactory, user: UserId, job: JobId, answer: GapAnswer
) -> None:
    async with uow() as tx:
        await tx.gap_answers.save(user, GapAnswerId(_id()), job, answer)
        await tx.commit()


async def _answers(uow: UnitOfWorkFactory, user: UserId, job: JobId) -> list[GapAnswer]:
    async with uow() as tx:
        return await tx.gap_answers.for_job(user, job)


def yes(gap: str, *numbers: int, minutes: int = 0) -> GapAnswer:
    return GapAnswer(gap, True, numbers, NOW + timedelta(minutes=minutes))


def no(gap: str, minutes: int = 0) -> GapAnswer:
    return GapAnswer(gap, False, (), NOW + timedelta(minutes=minutes))


def test_a_job_without_answers_has_none(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_job, uow, ALICE)
    assert portal.call(_answers, uow, ALICE, job) == []


def test_an_answer_with_facts_is_read_back_with_the_fact_numbers_in_order(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_job, uow, ALICE)
    first = portal.call(_fact, uow, ALICE, "Go")
    second = portal.call(_fact, uow, ALICE, "Go at Acme")

    portal.call(_save, uow, ALICE, job, yes("No Go", second, first))

    assert portal.call(_answers, uow, ALICE, job) == [yes("No Go", second, first)]


def test_a_no_answer_is_read_back_without_facts(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_job, uow, ALICE)
    portal.call(_save, uow, ALICE, job, no("No Go"))
    assert portal.call(_answers, uow, ALICE, job) == [no("No Go")]


def test_a_repeated_answer_to_the_same_gap_text_replaces_the_previous_one(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_job, uow, ALICE)
    fact = portal.call(_fact, uow, ALICE, "Go")
    portal.call(_save, uow, ALICE, job, yes("No Go", fact))

    portal.call(_save, uow, ALICE, job, no("  no go ", minutes=5))

    assert portal.call(_answers, uow, ALICE, job) == [no("  no go ", minutes=5)]


def test_answers_to_different_gaps_come_in_the_order_of_answering(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_job, uow, ALICE)
    portal.call(_save, uow, ALICE, job, no("Kubernetes", minutes=2))
    portal.call(_save, uow, ALICE, job, no("Go", minutes=1))

    stored = portal.call(_answers, uow, ALICE, job)

    assert [answer.gap for answer in stored] == ["Go", "Kubernetes"]


def test_the_same_gap_text_on_two_jobs_is_two_answers(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    one = portal.call(_job, uow, ALICE, "one")
    two = portal.call(_job, uow, ALICE, "two")
    portal.call(_save, uow, ALICE, one, no("Go"))

    assert portal.call(_answers, uow, ALICE, two) == []


def test_another_user_does_not_see_the_answers(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_job, uow, ALICE)
    portal.call(_save, uow, ALICE, job, no("Go"))
    assert portal.call(_answers, uow, BOB, job) == []


def test_a_deleted_fact_leaves_the_answer_without_it(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_job, uow, ALICE)
    kept = portal.call(_fact, uow, ALICE, "Go")
    dropped = portal.call(_fact, uow, ALICE, "Go at Acme")
    portal.call(_save, uow, ALICE, job, yes("No Go", kept, dropped))

    async def drop() -> None:
        async with uow() as tx:
            await tx.facts.delete(ALICE, dropped)
            await tx.commit()

    portal.call(drop)

    assert portal.call(_answers, uow, ALICE, job) == [yes("No Go", kept)]


def test_deleting_the_job_deletes_its_answers(
    portal: BlockingPortal, uow: UnitOfWorkFactory, engine: AsyncEngine
) -> None:
    job = portal.call(_job, uow, ALICE)
    portal.call(_save, uow, ALICE, job, no("Go"))

    async def run() -> object:
        async with engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM jobs WHERE id = :id"), {"id": job.value}
            )
            return (
                await conn.execute(text("SELECT count(*) FROM gap_answers"))
            ).scalar()

    assert portal.call(run) == 0


def test_a_fact_with_a_job_number_is_bound_to_that_job(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    async def run() -> Fact:
        async with uow() as tx:
            number = await tx.jobs.add(ALICE, JobId(_id()), posting("job"), NOW)
            await tx.facts.add(
                ALICE,
                FactId(_id()),
                NewFact(
                    FactKind.EXPERIENCE,
                    "Go at Acme",
                    FactSource.CHAT,
                    confirmed=True,
                    job_number=number,
                ),
                NOW,
            )
            await tx.commit()
            return (await tx.facts.all(ALICE))[0]

    stored = portal.call(run)
    assert (stored.source, stored.confirmed, stored.job_id) == (
        FactSource.CHAT,
        True,
        1,
    )
