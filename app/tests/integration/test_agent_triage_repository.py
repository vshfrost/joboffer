"""Кандидати агента на справжній базі: без тріажу або з тріажем `rules` і вердиктом maybe; решту
(`rules` analyse / skip, будь-який `agent`) агент не бачить. Збереження агентом забирає рядок у cron."""

from datetime import timedelta

import pytest
from anyio.from_thread import BlockingPortal

from domain.analysis.analysis import JobAnalysis
from domain.analysis.ids import AnalysisId
from domain.applications.application import ApplicationStatus
from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.triage.ids import TriageId
from domain.triage.scoring import inputs_hash
from domain.triage.triage import TriageEntry, TriageSource, TriageVerdict
from infrastructure.db.unit_of_work import UnitOfWorkFactory
from tests.integration.test_jobs_repository import ALICE, BOB, NOW, uow
from tests.integration.test_triage_repository import (
    _add,
    _apply,
    _candidates,
    _id,
    _pending,
    _save,
)

__all__ = ["uow"]


async def _rules_save(
    uow: UnitOfWorkFactory,
    user: UserId,
    job: tuple[int, JobId],
    verdict: TriageVerdict,
) -> None:
    number = job[0]
    async with uow() as tx:
        stored = await tx.jobs.get(user, number)
        assert stored is not None
        entry = TriageEntry(number, 50, verdict, "rules")
        await tx.triage.save_auto(
            user,
            [(TriageId(_id()), stored.id, entry, inputs_hash("context", stored))],
            NOW,
        )
        await tx.commit()


async def _source(
    uow: UnitOfWorkFactory, user: UserId, number: int
) -> TriageSource | None:
    async with uow() as tx:
        triage = await tx.jobs.get_triage(user, number)
        return None if triage is None else triage.source


def test_a_job_the_rules_rated_maybe_is_a_candidate_and_pending(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    unsure = portal.call(_add, uow, ALICE, "unsure", NOW)
    fresh = portal.call(_add, uow, ALICE, "fresh", NOW + timedelta(hours=1))
    portal.call(_rules_save, uow, ALICE, unsure, TriageVerdict.MAYBE)

    assert portal.call(_candidates, uow, ALICE) == [fresh[0], unsure[0]]
    assert portal.call(_pending, uow, ALICE) == 2


@pytest.mark.parametrize("verdict", [TriageVerdict.ANALYSE, TriageVerdict.SKIP])
def test_a_job_the_rules_rated_analyse_or_skip_is_neither_candidate_nor_pending(
    portal: BlockingPortal, uow: UnitOfWorkFactory, verdict: TriageVerdict
) -> None:
    rated = portal.call(_add, uow, ALICE, "rated")
    portal.call(_rules_save, uow, ALICE, rated, verdict)

    assert portal.call(_candidates, uow, ALICE) == []
    assert portal.call(_pending, uow, ALICE) == 0


@pytest.mark.parametrize("verdict", list(TriageVerdict))
def test_a_job_the_agent_rated_is_neither_candidate_nor_pending(
    portal: BlockingPortal, uow: UnitOfWorkFactory, verdict: TriageVerdict
) -> None:
    rated = portal.call(_add, uow, ALICE, "rated")
    portal.call(_save, uow, ALICE, rated, 50, verdict, "r", NOW)

    assert portal.call(_candidates, uow, ALICE) == []
    assert portal.call(_pending, uow, ALICE) == 0


def test_a_rules_maybe_job_follows_the_candidate_rule_for_analysis_and_closed_applications(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    analysed = portal.call(_add, uow, ALICE, "analysed", NOW)
    closed = portal.call(_add, uow, ALICE, "closed", NOW + timedelta(hours=1))
    kept = portal.call(_add, uow, ALICE, "kept", NOW + timedelta(hours=2))
    for job in (analysed, closed, kept):
        portal.call(_rules_save, uow, ALICE, job, TriageVerdict.MAYBE)

    async def analyse() -> None:
        async with uow() as tx:
            await tx.analyses.save(
                ALICE,
                AnalysisId(_id()),
                analysed[1],
                JobAnalysis(score=70, summary="S."),
                (),
                NOW,
            )
            await tx.commit()

    portal.call(analyse)
    portal.call(_apply, uow, ALICE, closed[0], ApplicationStatus.REJECTED)

    assert portal.call(_candidates, uow, ALICE) == [kept[0]]
    assert portal.call(_pending, uow, ALICE) == 1


def test_a_rules_maybe_job_of_another_user_is_not_a_candidate(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    bobs = portal.call(_add, uow, BOB, "bobs")
    portal.call(_rules_save, uow, BOB, bobs, TriageVerdict.MAYBE)

    assert portal.call(_candidates, uow, ALICE) == []
    assert portal.call(_candidates, uow, BOB) == [bobs[0]]


def test_the_agent_saving_over_a_rules_row_makes_it_an_agent_row_and_the_job_leaves_the_brief(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    job = portal.call(_add, uow, ALICE, "job")
    portal.call(_rules_save, uow, ALICE, job, TriageVerdict.MAYBE)
    assert portal.call(_source, uow, ALICE, job[0]) is TriageSource.RULES

    portal.call(_save, uow, ALICE, job, 80, TriageVerdict.MAYBE, "agent", NOW)

    assert portal.call(_source, uow, ALICE, job[0]) is TriageSource.AGENT
    assert portal.call(_candidates, uow, ALICE) == []


def test_the_details_triage_tells_who_rated(
    portal: BlockingPortal, uow: UnitOfWorkFactory
) -> None:
    by_agent = portal.call(_add, uow, ALICE, "one")
    by_rules = portal.call(_add, uow, ALICE, "two")
    portal.call(_save, uow, ALICE, by_agent, 70, TriageVerdict.ANALYSE, "r", NOW)
    portal.call(_rules_save, uow, ALICE, by_rules, TriageVerdict.SKIP)

    assert portal.call(_source, uow, ALICE, by_agent[0]) is TriageSource.AGENT
    assert portal.call(_source, uow, ALICE, by_rules[0]) is TriageSource.RULES
