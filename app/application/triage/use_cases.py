"""Use cases тріажу. REST і MCP викликають саме їх — правила в одному місці.

Claude отримує пачку свіжих вакансій без тріажу, швидко оцінює їх за початком тексту й профілем,
сервер валідує й зберігає. Вакансія скрізь — за номером у межах користувача; чужа й неіснуюча
не відрізняються.
"""

from collections.abc import Callable, Sequence

from application.contracts.actor import Actor
from application.contracts.triage import (
    SavedTriageData,
    TriageBriefData,
    TriageCandidateData,
    TriageData,
    TriageFactData,
    TriageInput,
)
from application.ports.clock import Clock
from application.ports.ids import IdGenerator
from application.ports.prompts import PromptKey, Prompts
from application.ports.triage import TriageUnitOfWork
from application.profile.use_cases import profile_data
from domain.applications.application import CLOSED_STATUSES
from domain.jobs.ids import JobId
from domain.shared.errors import InvalidValue
from domain.triage.brief import agent_text
from domain.triage.ids import TriageId
from domain.triage.triage import (
    AGENT_BATCH,
    TriageEntry,
    parse_entry,
)


class TriageUseCases:
    def __init__(
        self,
        unit_of_work: Callable[[], TriageUnitOfWork],
        clock: Clock,
        ids: IdGenerator,
        prompts: Prompts,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock
        self._ids = ids
        self._prompts = prompts

    async def prepare_triage(
        self, actor: Actor, limit: int = AGENT_BATCH, include_context: bool = True
    ) -> TriageBriefData:
        """Пачка вакансій для агента: з текстом, без аналізу й відмови, не сховані, без тріажу або з тріажем
        `rules` і вердиктом maybe; новіші першими. Текст — секції вимог, а без них весь. Профіль, правила й
        підтверджені факти йдуть лише з `include_context`. `InvalidValue` — ліміт."""
        if not 1 <= limit <= AGENT_BATCH:
            raise InvalidValue("limit", f"Ліміт — від 1 до {AGENT_BATCH}.")
        async with self._unit_of_work() as uow:
            jobs = await uow.triage.candidates(actor.user_id, limit)
            pending = await uow.triage.pending(actor.user_id)
            profile = await uow.profiles.get(actor.user_id) if include_context else None
            facts = await uow.facts.all(actor.user_id) if include_context else None
        candidates = []
        for job in jobs:
            # Кандидати мають текст (`needs_text` їх не пропускає).
            text = agent_text(job.text or "")
            candidates.append(
                TriageCandidateData(
                    job_number=job.number,
                    title=job.title,
                    company=job.company,
                    source=job.source,
                    location=job.location,
                    text=text.text,
                    text_scope=text.scope,
                )
            )
        return TriageBriefData(
            jobs=tuple(candidates),
            pending=pending,
            profile=None if profile is None else profile_data(profile),
            rules=self._prompts.get(PromptKey.TRIAGE_RULES)
            if include_context
            else None,
            facts=None
            if facts is None
            else tuple(
                TriageFactData(kind=fact.kind.value, text=fact.text)
                for fact in facts
                if fact.confirmed
            ),
        )

    async def save_triage(
        self, actor: Actor, items: Sequence[TriageInput]
    ) -> SavedTriageData:
        """Зберігає тріаж пачки: усе або нічого. Повторний тріаж вакансії перезаписує попередній.
        `InvalidValue` з номером елемента — порожня чи завелика пачка, повтор вакансії, чужа /
        неіснуюча / без тексту / з відмовою (rejected, withdrawn) вакансія, скор поза 0–100, невідомий вердикт, погана причина."""
        if not items:
            raise InvalidValue("items", "Порожня пачка: потрібен хоч один елемент.")
        if len(items) > AGENT_BATCH:
            raise InvalidValue("items", f"У пачці не більше {AGENT_BATCH} елементів.")
        entries = [
            parse_entry(
                position, item.job_number, item.score, item.verdict, item.reason
            )
            for position, item in enumerate(items, start=1)
        ]
        first_seen: dict[int, int] = {}
        for position, entry in enumerate(entries, start=1):
            if entry.job_number in first_seen:
                raise InvalidValue(
                    "items",
                    f"Елемент {position}: вакансія {entry.job_number} уже є в елементі "
                    f"{first_seen[entry.job_number]}.",
                )
            first_seen[entry.job_number] = position
        now = self._clock.now()
        async with self._unit_of_work() as uow:
            checked: list[tuple[TriageId, JobId, TriageEntry]] = []
            for position, entry in enumerate(entries, start=1):
                job = await uow.jobs.get(actor.user_id, entry.job_number)
                if job is None:
                    raise InvalidValue(
                        "items",
                        f"Елемент {position}: вакансію {entry.job_number} не знайдено.",
                    )
                if job.needs_text:
                    raise InvalidValue(
                        "items",
                        f"Елемент {position}: у вакансії {entry.job_number} "
                        "нема тексту опису.",
                    )
                if await uow.analyses.get(actor.user_id, job.id) is not None:
                    raise InvalidValue(
                        "items",
                        f"Елемент {position}: вакансію {entry.job_number} "
                        "уже проаналізовано.",
                    )
                application = await uow.applications.get(
                    actor.user_id, entry.job_number
                )
                if application is not None and application.status in CLOSED_STATUSES:
                    raise InvalidValue(
                        "items",
                        f"Елемент {position}: вакансію {entry.job_number} "
                        "відхилено або відкликано в подачі.",
                    )
                checked.append((TriageId(self._ids.new()), job.id, entry))
            await uow.triage.save(actor.user_id, checked, now)
            await uow.commit()
        return SavedTriageData(
            saved=tuple(
                TriageData(
                    job_number=entry.job_number,
                    score=entry.score,
                    verdict=entry.verdict,
                    reason=entry.reason,
                    triaged_at=now,
                )
                for _, _, entry in checked
            )
        )
