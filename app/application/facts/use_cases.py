"""Use cases оригіналу CV і фактів. REST і MCP викликають саме їх — правила в одному місці.

Факти з'являються непідтвердженими (крім вписаних користувачем вручну); підтверджує їх власник. Факт скрізь — за номером
у межах користувача; чужий і неіснуючий не відрізняються.
"""

from collections.abc import Callable, Sequence
from dataclasses import replace

from application.contracts.actor import Actor
from application.contracts.facts import (
    FactData,
    FactInput,
    FactLibraryData,
    OriginalCvData,
    SavedFactsData,
)
from application.ports.clock import Clock
from application.ports.facts import FactUnitOfWork
from application.ports.ids import IdGenerator
from domain.facts.errors import DuplicateFact
from domain.facts.fact import Fact, FactSource, NewFact, NewOriginalCv
from domain.facts.ids import FactId
from domain.facts.library import count_facts, ordered
from domain.shared.errors import InvalidValue, NotFound


class FactUseCases:
    def __init__(
        self,
        unit_of_work: Callable[[], FactUnitOfWork],
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock
        self._ids = ids

    async def save_original_cv(self, actor: Actor, text: str, file_name: str) -> None:
        """Зберігає текст CV замість попереднього; факти лишаються. `InvalidValue` — нічого
        не збережено."""
        cv = NewOriginalCv.parse(text=text, file_name=file_name)
        async with self._unit_of_work() as uow:
            await uow.original_cvs.save(actor.user_id, cv, self._clock.now())
            await uow.commit()

    async def get_original_cv(self, actor: Actor) -> OriginalCvData:
        """`NotFound` — оригінал ще не збережено."""
        async with self._unit_of_work() as uow:
            cv = await uow.original_cvs.get(actor.user_id)
        if cv is None:
            raise NotFound("Original CV ще не збережено.")
        return OriginalCvData(
            text=cv.text, file_name=cv.file_name, saved_at=cv.saved_at
        )

    async def save_facts(
        self, actor: Actor, items: Sequence[FactInput], source: str = "cv"
    ) -> SavedFactsData:
        """Додає факти непідтвердженими з одним джерелом (cv, chat чи manual); дублі (у базі,
        раніше в пачці, іншого виду) пропускає. Хоч один некоректний — нічого не збережено:
        `InvalidValue` «Факт N: …», для невідомого джерела — поле `source`."""
        fact_source = FactSource.parse(source)
        facts = [
            _parse_item(item, position, fact_source)
            for position, item in enumerate(items)
        ]
        user = actor.user_id
        added: list[Fact] = []
        skipped: list[str] = []
        async with self._unit_of_work() as uow:
            await uow.facts.lock_additions(user)
            for fact in facts:
                if await uow.facts.find_duplicate(user, fact.fingerprint) is not None:
                    skipped.append(fact.text)
                    continue
                added.append(
                    await uow.facts.add(
                        user, FactId(self._ids.new()), fact, self._clock.now()
                    )
                )
            await uow.commit()
        return SavedFactsData(
            added=tuple(fact_data(fact) for fact in added), skipped=tuple(skipped)
        )

    async def create_fact(self, actor: Actor, data: FactInput) -> FactData:
        """Факт, який користувач вписав сам: джерело manual, одразу підтверджений.
        `InvalidValue` — некоректний факт, `DuplicateFact` — такий текст уже є."""
        fact = replace(
            NewFact.parse(kind=data.kind, text=data.text, source=FactSource.MANUAL),
            confirmed=True,
        )
        user = actor.user_id
        async with self._unit_of_work() as uow:
            await uow.facts.lock_additions(user)
            duplicate = await uow.facts.find_duplicate(user, fact.fingerprint)
            if duplicate is not None:
                raise DuplicateFact(duplicate)
            created = await uow.facts.add(
                user,
                FactId(self._ids.new()),
                fact,
                self._clock.now(),
            )
            await uow.commit()
        return fact_data(created)

    async def list_facts(self, actor: Actor) -> FactLibraryData:
        """Усі факти за видами, усередині виду — в порядку додавання, і лічильники."""
        async with self._unit_of_work() as uow:
            facts = await uow.facts.all(actor.user_id)
        return FactLibraryData(
            facts=tuple(fact_data(fact) for fact in ordered(facts)),
            counts=count_facts(facts),
        )

    async def update_fact(
        self, actor: Actor, fact_number: int, data: FactInput
    ) -> FactData:
        """Змінює вид і текст та знімає підтвердження. `InvalidValue` — некоректний факт,
        `DuplicateFact` — такий текст уже в іншому, `NotFound` — нема чи чужий."""
        fact = NewFact.parse(kind=data.kind, text=data.text)
        user = actor.user_id
        async with self._unit_of_work() as uow:
            await uow.facts.lock_additions(user)
            if await uow.facts.get(user, fact_number) is None:
                raise _not_found(fact_number)
            duplicate = await uow.facts.find_duplicate(user, fact.fingerprint)
            if duplicate is not None and duplicate != fact_number:
                raise DuplicateFact(duplicate)
            changed = await uow.facts.replace(
                user, fact_number, fact, self._clock.now()
            )
            await uow.commit()
        return fact_data(changed)

    async def delete_fact(self, actor: Actor, fact_number: int) -> None:
        """Видаляє назавжди. `NotFound` — нема чи чужий."""
        async with self._unit_of_work() as uow:
            if await uow.facts.get(actor.user_id, fact_number) is None:
                raise _not_found(fact_number)
            await uow.facts.delete(actor.user_id, fact_number)
            await uow.commit()

    async def confirm_facts(
        self, actor: Actor, fact_numbers: Sequence[int]
    ) -> tuple[FactData, ...]:
        """Підтверджує лише названі факти. Порожньо — `InvalidValue`; хоч один невідомий чи
        чужий — `NotFound`, нічого не змінено."""
        numbers = frozenset(fact_numbers)
        if not numbers:
            raise InvalidValue("fact_ids", "Не вибрано жодного факту.")
        user = actor.user_id
        async with self._unit_of_work() as uow:
            known = {fact.number for fact in await uow.facts.all(user)}
            missing = sorted(numbers - known)
            if missing:
                raise NotFound(f"Факти не знайдено: {_numbers(missing)}.")
            await uow.facts.confirm(user, numbers, self._clock.now())
            await uow.commit()
            confirmed = [
                fact for fact in await uow.facts.all(user) if fact.number in numbers
            ]
        return tuple(fact_data(fact) for fact in confirmed)


def _parse_item(item: FactInput, position: int, source: FactSource) -> NewFact:
    try:
        return NewFact.parse(kind=item.kind, text=item.text, source=source)
    except InvalidValue as error:
        raise InvalidValue(
            f"facts.{position}.{error.field}", f"Факт {position + 1}: {error.message}"
        ) from error


def _not_found(number: int) -> NotFound:
    return NotFound(f"Факт #{number} не знайдено.")


def _numbers(numbers: list[int]) -> str:
    return ", ".join(f"#{number}" for number in numbers)


def fact_data(fact: Fact) -> FactData:
    return FactData(
        fact_number=fact.number,
        kind=fact.kind,
        text=fact.text,
        confirmed=fact.confirmed,
        created_at=fact.created_at,
        updated_at=fact.updated_at,
        source=fact.source,
        job_id=fact.job_id,
    )
