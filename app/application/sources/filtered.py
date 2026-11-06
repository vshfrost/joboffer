"""Вакансії з джерел, які поточний профіль уже не взяв би: перегляд і приховування вибраних після
підтвердження. Сервер сам перераховує список — довіряти номерам із запиту не можна."""

from collections.abc import Callable, Sequence

from application.contracts.actor import Actor
from application.ports.clock import Clock
from application.ports.sources import SourceImportUnitOfWork
from domain.identity.ids import UserId
from domain.jobs.dismiss import DISMISS_REASON_PROFILE_FILTER
from domain.shared.errors import InvalidValue
from domain.sources.filtered import FilteredChanged, FilteredJob, filtered_jobs


async def find_filtered(
    uow: SourceImportUnitOfWork, user_id: UserId
) -> list[FilteredJob]:
    """Вакансії користувача з джерел, що за його поточним профілем уже не проходять фільтр."""
    jobs = await uow.jobs.source_jobs(user_id)
    return filtered_jobs(jobs, await uow.profiles.get(user_id))


class FilteredJobUseCases:
    def __init__(
        self, unit_of_work: Callable[[], SourceImportUnitOfWork], clock: Clock
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock

    async def list_filtered(self, actor: Actor) -> list[FilteredJob]:
        """Свої вакансії з джерел, що за поточним профілем уже не проходять фільтр: не сховані,
        без аналізу й без подачі. Нічого не змінює."""
        async with self._unit_of_work() as uow:
            return await find_filtered(uow, actor.user_id)

    async def dismiss_filtered(self, actor: Actor, numbers: Sequence[int]) -> int:
        """Ховає вибрані вакансії з причиною «фільтр профілю»; повертає, скільки сховано.
        `InvalidValue` (numbers) — вибір порожній; `FilteredChanged` — хоч одного номера нема в
        перерахованому списку (нічого не сховано)."""
        chosen = list(dict.fromkeys(numbers))
        if not chosen:
            raise InvalidValue("numbers", "Нема що ховати.")
        async with self._unit_of_work() as uow:
            current = {item.number for item in await find_filtered(uow, actor.user_id)}
            stale = [number for number in chosen if number not in current]
            if stale:
                raise FilteredChanged(stale)
            await uow.jobs.dismiss(
                actor.user_id, chosen, DISMISS_REASON_PROFILE_FILTER, self._clock.now()
            )
            await uow.commit()
        return len(chosen)
