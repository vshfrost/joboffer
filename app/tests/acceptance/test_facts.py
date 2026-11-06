"""Кроки для features/facts_*.feature: use cases фактів і оригіналу CV + in-memory адаптери через портал.

Значення в кроках — у лапках і можуть бути порожніми, тому кроки — регулярні вирази з іменованими
групами; `\\n` у тексті — перенесення рядка. «Припустимо я додав …» і «Якщо я додаю …» — один і той
самий крок; у «Припустимо» додатково перевіряється, що дія вдалася. Номер факту — `fact_id`,
лічильник на користувача; внутрішній UUID у сценаріях не фігурує.
"""

import functools
import re
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from anyio.from_thread import BlockingPortal
from pytest_bdd import given as bdd_given
from pytest_bdd import parsers, scenarios
from pytest_bdd import then as bdd_then
from pytest_bdd import when as bdd_when

from application.contracts.actor import Actor, Channel, Scope
from application.contracts.facts import (
    FactData,
    FactInput,
    FactLibraryData,
    OriginalCvData,
    SavedFactsData,
)
from application.facts.use_cases import FactUseCases
from domain.identity.ids import UserId
from domain.shared.errors import DomainError, InvalidValue
from domain.shared.local_time import local_day
from tests.support.clock import FakeClock
from tests.support.facts import InMemoryFactUnitOfWork, Store
from tests.support.ids import SequentialIds

scenarios(
    "features/facts_save.feature",
    "features/facts_source.feature",
    "features/facts_library.feature",
    "features/facts_update.feature",
    "features/facts_confirm.feature",
    "features/facts_delete.feature",
    "features/facts_original_cv.feature",
    "features/facts_users.feature",
)

Step = Callable[..., Any]

PAIR = re.compile(r'(?P<kind>[^\s";]+) "(?P<text>[^"]*)"')


def rx(pattern: str) -> Any:
    return parsers.re(pattern)


def text_of(raw: str) -> str:
    """У feature-файлі перенесення рядка записано як `\\n`."""
    return raw.replace("\\n", "\n")


def succeeded(step: Step) -> Step:
    """Крок-передумова: дія має вдатися, інакше сценарій не про те."""

    @functools.wraps(step)
    def wrapper(*args: Any, **kwargs: Any) -> None:
        step(*args, **kwargs)
        world: World = kwargs["world"]
        assert world.error is None, world.error

    return wrapper


def action(pattern: str) -> Callable[[Step], Step]:
    """Один текст — і «Припустимо я додав …», і «Якщо я додаю …» (дієслово в `(?:додаю|додав)`)."""

    def decorate(step: Step) -> Step:
        bdd_given(rx(pattern), stacklevel=2)(succeeded(step))
        bdd_when(rx(pattern), stacklevel=2)(step)
        return step

    return decorate


class World:
    def __init__(
        self, portal: BlockingPortal, clock: FakeClock, ids: SequentialIds
    ) -> None:
        self.portal = portal
        self.clock = clock
        self.ids = ids
        self.store = Store.empty()
        self.use_cases = FactUseCases(
            lambda: InMemoryFactUnitOfWork(self.store), clock, ids
        )
        self.actors: dict[str, Actor] = {}
        self.current = ""
        self.saved: SavedFactsData | None = None
        self.confirmed: tuple[FactData, ...] | None = None
        self.cv: OriginalCvData | None = None
        self.error: DomainError | None = None

    def become(self, name: str) -> None:
        if name not in self.actors:
            self.actors[name] = Actor(
                user_id=UserId(self.ids.new()),
                channel=Channel.WEB,
                client_id="web",
                grant_id=None,
                scopes=frozenset(Scope),
                correlation_id="test",
            )
        self.current = name
        self.reset_outcome()

    @property
    def actor(self) -> Actor:
        return self.actors[self.current]

    def reset_outcome(self) -> None:
        self.saved = None
        self.confirmed = None
        self.cv = None
        self.error = None

    def attempt(self, call: Callable[[], Any]) -> Any:
        """Виконує дію; помилка домену запамʼятовується для кроків «Тоді»."""
        self.reset_outcome()
        try:
            return self.portal.call(call)
        except DomainError as error:
            self.error = error
            return None

    def save(self, items: list[FactInput], source: str = "cv") -> None:
        self.saved = self.attempt(
            lambda: self.use_cases.save_facts(self.actor, items, source)
        )

    def library(self) -> FactLibraryData:
        """Бібліотека, як її бачить поточний користувач (без запису в результат кроку)."""
        return self.portal.call(self.use_cases.list_facts, self.actor)

    def fact(self, number: int) -> FactData:
        found = [f for f in self.library().facts if f.fact_number == number]
        assert found, f"факту {number} нема в бібліотеці"
        return found[0]

    def save_cv(self, text: str, file_name: str) -> None:
        self.attempt(
            lambda: self.use_cases.save_original_cv(self.actor, text, file_name)
        )

    def open_cv(self) -> OriginalCvData:
        return self.portal.call(self.use_cases.get_original_cv, self.actor)


@pytest.fixture
def world(portal: BlockingPortal, clock: FakeClock, ids: SequentialIds) -> World:
    return World(portal, clock, ids)


def numbers(text: str) -> list[int]:
    return [] if text.strip() == "" else [int(part) for part in text.split(";")]


def texts(text: str) -> tuple[str, ...]:
    return () if text == "" else tuple(text.split(";"))


# --- хто я, час -------------------------------------------------------------------------------


@bdd_given(rx(r'^я — користувач "(?P<name>[^"]*)"$'))
@bdd_when(rx(r'^я стаю користувачем "(?P<name>[^"]*)"$'))
def become_user(world: World, name: str) -> None:
    world.become(name)


@bdd_given(rx(r"^минає (?P<days>\d+) (?:доба|доби|діб)$"))
@bdd_when(rx(r"^минає (?P<days>\d+) (?:доба|доби|діб)$"))
def days_pass(world: World, days: str) -> None:
    world.clock.advance(timedelta(days=int(days)))


# --- додавання --------------------------------------------------------------------------------


@action(r'^я (?:додаю|додав) факт (?P<kind>[^\s"]+) "(?P<text>[^"]*)"$')
def add_one(world: World, kind: str, text: str) -> None:
    world.save([FactInput(kind=kind, text=text_of(text))])


@action(
    r'^я (?:додаю|додав) з джерелом "(?P<source>[^"]*)" факт (?P<kind>[^\s"]+) "(?P<text>[^"]*)"$'
)
def add_one_with_source(world: World, source: str, kind: str, text: str) -> None:
    world.save([FactInput(kind=kind, text=text_of(text))], source)


@action(r'^я вручну (?:створюю|створив) факт (?P<kind>[^\s"]+) "(?P<text>[^"]*)"$')
def create_manual(world: World, kind: str, text: str) -> None:
    data = FactInput(kind=kind, text=text_of(text))
    world.attempt(lambda: world.use_cases.create_fact(world.actor, data))


@action(r"^я вручну (?:створюю|створив) факт із (?P<length>\d+) символів$")
def create_manual_long(world: World, length: str) -> None:
    data = FactInput(kind="skill", text="x" * int(length))
    world.attempt(lambda: world.use_cases.create_fact(world.actor, data))


@action(r"^я (?:додаю|додав) пачку: (?P<items>.+)$")
def add_pack(world: World, items: str) -> None:
    pairs = PAIR.findall(items)
    assert pairs, f"у пачці нема жодного факту: {items}"
    world.save([FactInput(kind=kind, text=text_of(text)) for kind, text in pairs])


@action(r"^я (?:додаю|додав) порожню пачку$")
def add_empty_pack(world: World) -> None:
    world.save([])


@action(r"^я (?:додаю|додав) факт із (?P<length>\d+) символів$")
def add_long(world: World, length: str) -> None:
    world.save([FactInput(kind="skill", text="x" * int(length))])


@action(r"^я (?:додаю|додав) пачку з довгим фактом на другому місці$")
def add_pack_with_long(world: World) -> None:
    world.save(
        [
            FactInput(kind="skill", text="Python"),
            FactInput(kind="skill", text="x" * 501),
            FactInput(kind="skill", text="Go"),
        ]
    )


@bdd_then(rx(r'^додано факти з номерами "(?P<ids>[^"]*)"$'))
def added(world: World, ids: str) -> None:
    assert world.error is None, world.error
    assert world.saved is not None
    assert [f.fact_number for f in world.saved.added] == numbers(ids)


@bdd_then("нічого не додано")
def nothing_added(world: World) -> None:
    assert world.error is None, world.error
    assert world.saved is not None
    assert world.saved.added == ()


@bdd_then("нічого не пропущено")
def nothing_skipped(world: World) -> None:
    assert world.saved is not None
    assert world.saved.skipped == ()


@bdd_then(rx(r'^пропущено "(?P<skipped>[^"]*)"$'))
def skipped(world: World, skipped: str) -> None:
    assert world.saved is not None
    assert world.saved.skipped == texts(skipped)


# --- бібліотека -------------------------------------------------------------------------------


@bdd_when("я переглядаю бібліотеку")
def view_library(world: World) -> None:
    world.attempt(lambda: world.use_cases.list_facts(world.actor))


@bdd_then(rx(r"^у бібліотеці (?P<count>\d+) (?:факт|факти|фактів)$"))
def library_size(world: World, count: str) -> None:
    assert len(world.library().facts) == int(count)


@bdd_then(rx(r'^порядок номерів "(?P<ids>[^"]*)"$'))
def library_order(world: World, ids: str) -> None:
    assert [f.fact_number for f in world.library().facts] == numbers(ids)


@bdd_then(
    rx(
        r"^лічильники: усього (?P<total>\d+), підтверджених (?P<confirmed>\d+),"
        r" на перевірці (?P<pending>\d+)$"
    )
)
def counts(world: World, total: str, confirmed: str, pending: str) -> None:
    found = world.library().counts
    assert (found.total, found.confirmed, found.unconfirmed) == (
        int(total),
        int(confirmed),
        int(pending),
    )


@bdd_then(rx(r'^види в лічильниках: "(?P<kinds>[^"]*)"$'))
def count_kinds(world: World, kinds: str) -> None:
    assert [k.kind.value for k in world.library().counts.kinds] == list(texts(kinds))


@bdd_then(
    rx(r'^вид "(?P<kind>[^"]*)": усього (?P<total>\d+), на перевірці (?P<pending>\d+)$')
)
def kind_counts(world: World, kind: str, total: str, pending: str) -> None:
    (found,) = [k for k in world.library().counts.kinds if k.kind.value == kind]
    assert (found.total, found.unconfirmed) == (int(total), int(pending))


# --- факт -------------------------------------------------------------------------------------


@bdd_then(
    rx(r'^факт (?P<number>\d+) має вид "(?P<kind>[^"]*)" і текст "(?P<text>[^"]*)"$')
)
def fact_has(world: World, number: str, kind: str, text: str) -> None:
    fact = world.fact(int(number))
    assert (fact.kind.value, fact.text) == (kind, text_of(text))


@bdd_then(rx(r'^факт (?P<number>\d+) має джерело "(?P<source>[^"]*)"$'))
def fact_source(world: World, number: str, source: str) -> None:
    assert world.fact(int(number)).source.value == source


@bdd_then(rx(r"^факт (?P<number>\d+) без вакансії$"))
def fact_without_job(world: World, number: str) -> None:
    assert world.fact(int(number)).job_id is None


@bdd_then(rx(r"^факт (?P<number>\d+) підтверджений$"))
def fact_confirmed(world: World, number: str) -> None:
    assert world.fact(int(number)).confirmed is True


@bdd_then(rx(r"^факт (?P<number>\d+) не підтверджений$"))
def fact_unconfirmed(world: World, number: str) -> None:
    assert world.fact(int(number)).confirmed is False


@bdd_then(rx(r'^факт (?P<number>\d+) створено "(?P<moment>[^"]*)"$'))
def fact_created(world: World, number: str, moment: str) -> None:
    assert world.fact(int(number)).created_at.isoformat() == moment


@bdd_then(rx(r'^факт (?P<number>\d+) змінено "(?P<moment>[^"]*)"$'))
def fact_updated(world: World, number: str, moment: str) -> None:
    assert world.fact(int(number)).updated_at.isoformat() == moment


# --- зміна, підтвердження, видалення ---------------------------------------------------------


@action(
    r'^я (?:змінюю|змінив) факт (?P<number>-?\d+) на вид "(?P<kind>[^"]*)"'
    r' з текстом "(?P<text>[^"]*)"$'
)
def update(world: World, number: str, kind: str, text: str) -> None:
    data = FactInput(kind=kind, text=text_of(text))
    world.attempt(lambda: world.use_cases.update_fact(world.actor, int(number), data))


@action(
    r'^я (?:змінюю|змінив) факт (?P<number>\d+) на вид "(?P<kind>[^"]*)"'
    r" з текстом із (?P<length>\d+) символ\S*$"
)
def update_long(world: World, number: str, kind: str, length: str) -> None:
    data = FactInput(kind=kind, text="x" * int(length))
    world.attempt(lambda: world.use_cases.update_fact(world.actor, int(number), data))


@action(r'^я (?:підтверджую|підтвердив) факти "(?P<ids>[^"]*)"$')
def confirm(world: World, ids: str) -> None:
    world.confirmed = world.attempt(
        lambda: world.use_cases.confirm_facts(world.actor, numbers(ids))
    )


@bdd_when("я підтверджую без жодного факту")
def confirm_none(world: World) -> None:
    world.attempt(lambda: world.use_cases.confirm_facts(world.actor, []))


@bdd_then(rx(r'^підтверджено факти "(?P<ids>[^"]*)"$'))
def confirmed(world: World, ids: str) -> None:
    assert world.error is None, world.error
    assert world.confirmed is not None
    assert [f.fact_number for f in world.confirmed] == numbers(ids)
    assert all(f.confirmed for f in world.confirmed)


@action(r"^я (?:видаляю|видалив) факт (?P<number>\d+)$")
def delete(world: World, number: str) -> None:
    world.attempt(lambda: world.use_cases.delete_fact(world.actor, int(number)))


@bdd_then("видалення вдалося")
def deleted(world: World) -> None:
    assert world.error is None, world.error


# --- оригінал CV -----------------------------------------------------------------------------


@action(
    r'^я (?:зберігаю|зберіг) оригінал CV "(?P<text>[^"]*)" з файлом "(?P<name>[^"]*)"$'
)
def save_cv_with_file(world: World, text: str, name: str) -> None:
    world.save_cv(text_of(text), name)


@action(r'^я (?:зберігаю|зберіг) оригінал CV "(?P<text>[^"]*)" без файлу$')
def save_cv_without_file(world: World, text: str) -> None:
    world.save_cv(text_of(text), "")


@action(r"^я (?:зберігаю|зберіг) оригінал CV із (?P<length>\d+) символ\S*$")
def save_long_cv(world: World, length: str) -> None:
    world.save_cv("x" * int(length), "")


@action(
    r'^я (?:зберігаю|зберіг) оригінал CV "(?P<text>[^"]*)" з файлом із (?P<length>\d+) символ\S*$'
)
def save_cv_with_long_name(world: World, text: str, length: str) -> None:
    world.save_cv(text, "n" * int(length))


@bdd_when("я відкриваю оригінал CV")
def open_cv(world: World) -> None:
    world.cv = world.attempt(lambda: world.use_cases.get_original_cv(world.actor))


@bdd_then("оригінал збережено")
def cv_saved(world: World) -> None:
    assert world.error is None, world.error


def opened(world: World) -> OriginalCvData:
    assert world.error is None, world.error
    assert world.cv is not None, "оригінал не відкривали"
    return world.cv


@bdd_then(rx(r'^оригінал CV має текст "(?P<text>[^"]*)"$'))
def cv_text(world: World, text: str) -> None:
    assert opened(world).text == text_of(text)


@bdd_then(rx(r'^оригінал CV має назву файлу "(?P<name>[^"]*)"$'))
def cv_file_name(world: World, name: str) -> None:
    assert opened(world).file_name == name


@bdd_then("оригінал CV без назви файлу")
def cv_no_file_name(world: World) -> None:
    assert opened(world).file_name is None


@bdd_then(rx(r'^оригінал CV збережено "(?P<moment>[^"]*)"$'))
def cv_saved_at(world: World, moment: str) -> None:
    assert opened(world).saved_at.isoformat() == moment


@bdd_then(rx(r'^оригінал CV збережено в день "(?P<day>[^"]*)" за Мадридом$'))
def cv_saved_day(world: World, day: str) -> None:
    assert local_day(opened(world).saved_at) == day


@bdd_then(rx(r'^збережений оригінал CV має текст "(?P<text>[^"]*)"$'))
def stored_cv_text(world: World, text: str) -> None:
    assert world.open_cv().text == text_of(text)


# --- помилки ----------------------------------------------------------------------------------


@bdd_then(rx(r'^отримую помилку "(?P<code>[^"]*)"$'))
def error_code(world: World, code: str) -> None:
    assert world.error is not None, "помилки не було"
    assert world.error.code == code


@bdd_then(rx(r'^отримую помилку "(?P<code>[^"]*)" з текстом "(?P<message>[^"]*)"$'))
def error_message(world: World, code: str, message: str) -> None:
    assert world.error is not None, "помилки не було"
    assert (world.error.code, world.error.message) == (code, message)


@bdd_then(
    rx(
        r'^отримую помилку "(?P<code>[^"]*)" для поля "(?P<field>[^"]*)" з текстом "(?P<message>[^"]*)"$'
    )
)
def error_field_message(world: World, code: str, field: str, message: str) -> None:
    error = world.error
    assert isinstance(error, InvalidValue), error
    assert (error.code, error.field, error.message) == (code, field, message)
