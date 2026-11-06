"""AnalysisRepository на Postgres.

Повторний аналіз вакансії замінює рядок (`ON CONFLICT (job_id)`), перший `id` лишається.
`score`, `work_mode` і `filters_passed` — окремі колонки (сортування й фільтр списку), решта
розбору — у JSON `details` з тими самими ключами, що в v1: ETL переносить рядки без перетворень.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from domain.analysis.analysis import Analysis, Gap, JobAnalysis
from domain.analysis.ids import AnalysisId
from domain.analysis.keywords import KeywordFacts
from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.profile.modes import Seniority, WorkMode
from infrastructure.db.analysis.tables import AnalysisRow
from infrastructure.db.jobs.tables import JobRow


class PostgresAnalyses:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: UserId, job_id: JobId) -> Analysis | None:
        found = (
            await self._session.execute(
                select(AnalysisRow, JobRow.job_number)
                .join(JobRow, JobRow.id == AnalysisRow.job_id)
                .where(
                    AnalysisRow.user_id == user_id.value,
                    AnalysisRow.job_id == job_id.value,
                )
                .execution_options(populate_existing=True)
            )
        ).one_or_none()
        if found is None:
            return None
        row, number = found
        return _to_domain(row, number)

    async def save(  # noqa: PLR0913, PLR0917
        self,
        user_id: UserId,
        analysis_id: AnalysisId,
        job_id: JobId,
        analysis: JobAnalysis,
        flags: tuple[str, ...],
        now: datetime,
    ) -> None:
        values = {
            "score": analysis.score,
            "work_mode": None
            if analysis.work_mode is None
            else analysis.work_mode.value,
            "filters_passed": not flags,
            "flags": list(flags),
            "details": _details(analysis),
            "updated_at": now,
        }
        await self._session.execute(
            pg_insert(AnalysisRow)
            .values(
                id=analysis_id.value,
                user_id=user_id.value,
                job_id=job_id.value,
                **values,
            )
            .on_conflict_do_update(index_elements=[AnalysisRow.job_id], set_=values)
        )


def _details(analysis: JobAnalysis) -> dict[str, Any]:
    return {
        "summary": analysis.summary,
        "must_have": list(analysis.must_have),
        "nice_to_have": list(analysis.nice_to_have),
        "keywords": list(analysis.keywords),
        "candidate_asks": list(analysis.candidate_asks),
        "seniority": None if analysis.seniority is None else analysis.seniority.value,
        "location": analysis.location,
        "languages": list(analysis.languages),
        "salary_min_eur": analysis.salary_min_eur,
        "salary_max_eur": analysis.salary_max_eur,
        "relocation": analysis.relocation,
        "reasons": list(analysis.reasons),
        "gaps": [
            {"gap": item.gap, "question": item.question} for item in analysis.gaps
        ],
        # Список, не об'єкт: JSONB не зберігає порядок ключів. Нема ключа / null — старий аналіз.
        "keyword_facts": None
        if analysis.keyword_facts is None
        else [
            {"keyword": item.keyword, "fact_numbers": list(item.fact_numbers)}
            for item in analysis.keyword_facts
        ],
    }


def _gap(stored: str | dict[str, Any]) -> Gap:
    """Старі аналізи зберігали прогалини рядками (без питання), нові — об'єктами."""
    if isinstance(stored, str):
        return Gap(stored)
    return Gap(stored["gap"], stored["question"])


def _keyword_facts(
    stored: list[dict[str, Any]] | None,
) -> tuple[KeywordFacts, ...] | None:
    if stored is None:
        return None
    return tuple(
        KeywordFacts(item["keyword"], tuple(item["fact_numbers"])) for item in stored
    )


def _to_domain(row: AnalysisRow, number: int) -> Analysis:
    details = row.details
    analysis = JobAnalysis(
        score=row.score,
        summary=details["summary"],
        must_have=tuple(details["must_have"]),
        nice_to_have=tuple(details["nice_to_have"]),
        keywords=tuple(details["keywords"]),
        candidate_asks=tuple(details.get("candidate_asks", ())),
        seniority=None
        if details["seniority"] is None
        else Seniority(details["seniority"]),
        work_mode=None if row.work_mode is None else WorkMode(row.work_mode),
        location=details["location"],
        languages=tuple(details["languages"]),
        salary_min_eur=details["salary_min_eur"],
        salary_max_eur=details["salary_max_eur"],
        relocation=details["relocation"],
        reasons=tuple(details["reasons"]),
        gaps=tuple(_gap(item) for item in details["gaps"]),
        keyword_facts=_keyword_facts(details.get("keyword_facts")),
    )
    return Analysis(number, analysis, tuple(row.flags), row.updated_at)
