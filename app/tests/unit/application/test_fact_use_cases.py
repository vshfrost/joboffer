"""Use cases фактів: номери, дублі, пачки, підтвердження, оригінал CV, ізоляція користувачів."""

from datetime import timedelta

import pytest
from anyio.from_thread import BlockingPortal

from application.contracts.actor import Actor, Channel, Scope
from application.contracts.facts import FactInput, SavedFactsData
from application.facts.use_cases import FactUseCases
from domain.facts.errors import DuplicateFact
from domain.facts.fact import MAX_CV_LENGTH, FactKind
from domain.identity.ids import UserId
from domain.shared.errors import InvalidValue, NotFound
from tests.support.clock import FakeClock
from tests.support.facts import InMemoryFactUnitOfWork, Store
from tests.support.ids import SequentialIds

PYTHON = FactInput(kind="skill", text="Python")
LEAD = FactInput(kind="experience", text="Backend Lead at Acme, 2021–2024")
LATENCY = FactInput(kind="achievement", text="Cut p95 latency by 40%")


class World:
    def __init__(
        self, portal: BlockingPortal, clock: FakeClock, ids: SequentialIds
    ) -> None:
        self.portal = portal
        self.clock = clock
        self.ids = ids
        self.store = Store.empty()
        self.alice = self._actor()
        self.bob = self._actor()
        self.use_cases = FactUseCases(
            lambda: InMemoryFactUnitOfWork(self.store), clock, ids
        )

    def _actor(self) -> Actor:
        return Actor(
            user_id=UserId(self.ids.new()),
            channel=Channel.WEB,
            client_id="web",
            grant_id=None,
            scopes=frozenset(Scope),
            correlation_id="test",
        )

    def save(self, actor: Actor, *items: FactInput) -> SavedFactsData:
        return self.portal.call(self.use_cases.save_facts, actor, list(items))

    def numbers(self, actor: Actor) -> list[int]:
        library = self.portal.call(self.use_cases.list_facts, actor)
        return [fact.fact_number for fact in library.facts]

    def confirmed(self, actor: Actor) -> dict[int, bool]:
        library = self.portal.call(self.use_cases.list_facts, actor)
        return {fact.fact_number: fact.confirmed for fact in library.facts}


@pytest.fixture
def world(portal: BlockingPortal, clock: FakeClock, ids: SequentialIds) -> World:
    return World(portal, clock, ids)


def test_new_facts_are_numbered_from_one_and_unconfirmed(world: World) -> None:
    saved = world.save(world.alice, PYTHON, LEAD)
    assert [(f.fact_number, f.kind, f.confirmed) for f in saved.added] == [
        (1, FactKind.SKILL, False),
        (2, FactKind.EXPERIENCE, False),
    ]
    assert saved.skipped == ()


def test_a_duplicate_in_the_base_inside_the_batch_and_of_another_kind_is_skipped(
    world: World,
) -> None:
    world.save(world.alice, PYTHON)
    saved = world.save(
        world.alice,
        LEAD,
        FactInput(kind="skill", text=" PYTHON "),
        FactInput(kind="experience", text="python"),
        LEAD,
    )
    assert [f.fact_number for f in saved.added] == [2]
    assert saved.skipped == ("PYTHON", "python", LEAD.text)
    assert world.numbers(world.alice) == [2, 1]


def test_one_invalid_fact_saves_none_and_names_its_position(world: World) -> None:
    with pytest.raises(InvalidValue) as raised:
        world.save(world.alice, PYTHON, FactInput(kind="hobby", text="Chess"))
    assert raised.value.message == "Факт 2: Невідомий вид факту: 'hobby'."
    assert raised.value.field == "facts.1.kind"
    assert world.numbers(world.alice) == []


@pytest.mark.parametrize(
    ("item", "message"),
    [
        (FactInput(kind="skill", text="  "), "Факт 1: Факт не може бути порожнім."),
        (
            FactInput(kind="skill", text="x" * 501),
            "Факт 1: Факт задовгий: більше 500 символів — розбий на кілька.",
        ),
    ],
)
def test_an_empty_or_too_long_fact_rejects_the_whole_batch(
    world: World, item: FactInput, message: str
) -> None:
    with pytest.raises(InvalidValue) as raised:
        world.save(world.alice, item)
    assert raised.value.message == message


def test_an_empty_batch_adds_nothing(world: World) -> None:
    saved = world.save(world.alice)
    assert (saved.added, saved.skipped) == ((), ())


def test_the_library_is_ordered_by_kind_then_number_with_exact_counts(
    world: World,
) -> None:
    world.save(world.alice, PYTHON, LATENCY, LEAD, FactInput(kind="skill", text="Go"))
    world.portal.call(world.use_cases.confirm_facts, world.alice, [3, 4])
    library = world.portal.call(world.use_cases.list_facts, world.alice)
    assert [f.fact_number for f in library.facts] == [3, 2, 1, 4]
    assert (library.counts.total, library.counts.confirmed) == (4, 2)
    assert library.counts.unconfirmed == 2
    by_kind = {
        k.kind: (k.total, k.confirmed, k.unconfirmed) for k in library.counts.kinds
    }
    assert by_kind[FactKind.SKILL] == (2, 1, 1)
    assert by_kind[FactKind.EXPERIENCE] == (1, 1, 0)
    assert by_kind[FactKind.EDUCATION] == (0, 0, 0)


def test_confirm_marks_only_the_given_facts(world: World) -> None:
    world.save(world.alice, PYTHON, LEAD)
    confirmed = world.portal.call(world.use_cases.confirm_facts, world.alice, [2, 2])
    assert [(f.fact_number, f.confirmed) for f in confirmed] == [(2, True)]
    assert world.confirmed(world.alice) == {2: True, 1: False}


def test_confirm_without_ids_is_an_error_and_changes_nothing(world: World) -> None:
    world.save(world.alice, PYTHON)
    with pytest.raises(InvalidValue) as raised:
        world.portal.call(world.use_cases.confirm_facts, world.alice, [])
    assert (raised.value.field, raised.value.message) == (
        "fact_ids",
        "Не вибрано жодного факту.",
    )
    assert world.confirmed(world.alice) == {1: False}


def test_confirm_with_an_unknown_id_changes_nothing(world: World) -> None:
    world.save(world.alice, PYTHON)
    with pytest.raises(NotFound) as raised:
        world.portal.call(world.use_cases.confirm_facts, world.alice, [1, 99, 98])
    assert raised.value.message == "Факти не знайдено: #98, #99."
    assert world.confirmed(world.alice) == {1: False}


def test_update_replaces_kind_and_text_and_drops_the_confirmation(
    world: World,
) -> None:
    world.save(world.alice, PYTHON)
    world.portal.call(world.use_cases.confirm_facts, world.alice, [1])
    updated = world.portal.call(
        world.use_cases.update_fact,
        world.alice,
        1,
        FactInput(kind="project", text="Python 3.14 migration"),
    )
    assert (updated.fact_number, updated.kind, updated.text, updated.confirmed) == (
        1,
        FactKind.PROJECT,
        "Python 3.14 migration",
        False,
    )
    assert world.confirmed(world.alice) == {1: False}


def test_update_to_its_own_text_in_another_case_is_allowed(world: World) -> None:
    world.save(world.alice, PYTHON)
    updated = world.portal.call(
        world.use_cases.update_fact,
        world.alice,
        1,
        FactInput(kind="skill", text="python"),
    )
    assert updated.text == "python"


def test_update_to_the_text_of_another_fact_names_that_fact(world: World) -> None:
    world.save(world.alice, PYTHON, LEAD)
    with pytest.raises(DuplicateFact) as raised:
        world.portal.call(world.use_cases.update_fact, world.alice, 2, PYTHON)
    assert raised.value.message == "Такий факт уже є: #1."
    library = world.portal.call(world.use_cases.list_facts, world.alice)
    assert library.facts[0].text == LEAD.text


def test_an_invalid_update_has_no_position_prefix(world: World) -> None:
    world.save(world.alice, PYTHON)
    with pytest.raises(InvalidValue) as raised:
        world.portal.call(
            world.use_cases.update_fact,
            world.alice,
            1,
            FactInput(kind="hobby", text="Chess"),
        )
    assert raised.value.message == "Невідомий вид факту: 'hobby'."


def test_update_of_an_unknown_fact_is_not_found(world: World) -> None:
    with pytest.raises(NotFound) as raised:
        world.portal.call(world.use_cases.update_fact, world.alice, 7, PYTHON)
    assert raised.value.message == "Факт #7 не знайдено."


def test_delete_removes_the_fact_for_good_and_its_number_is_not_reused(
    world: World,
) -> None:
    world.save(world.alice, PYTHON, LEAD)
    world.portal.call(world.use_cases.delete_fact, world.alice, 2)
    assert world.numbers(world.alice) == [1]
    with pytest.raises(NotFound) as raised:
        world.portal.call(world.use_cases.delete_fact, world.alice, 2)
    assert raised.value.message == "Факт #2 не знайдено."
    assert world.save(world.alice, LEAD).added[0].fact_number == 3


def test_facts_of_users_are_numbered_and_stored_independently(world: World) -> None:
    world.save(world.alice, PYTHON)
    assert world.save(world.bob, PYTHON).added[0].fact_number == 1
    assert world.numbers(world.bob) == [1]


def test_a_user_cannot_see_or_change_the_facts_of_another(world: World) -> None:
    world.save(world.alice, PYTHON)
    world.save(world.bob, LEAD, LATENCY)
    for action in (
        lambda: world.portal.call(world.use_cases.confirm_facts, world.alice, [2]),
        lambda: world.portal.call(world.use_cases.update_fact, world.alice, 2, LEAD),
        lambda: world.portal.call(world.use_cases.delete_fact, world.alice, 2),
    ):
        with pytest.raises(NotFound):
            action()
    assert world.numbers(world.alice) == [1]
    assert world.confirmed(world.bob) == {1: False, 2: False}


def test_the_original_cv_is_saved_and_a_new_one_replaces_it(world: World) -> None:
    world.portal.call(world.use_cases.save_original_cv, world.alice, "old", "old.pdf")
    world.clock.advance(timedelta(days=1))
    world.portal.call(world.use_cases.save_original_cv, world.alice, " new ", "")
    cv = world.portal.call(world.use_cases.get_original_cv, world.alice)
    assert (cv.text, cv.file_name, cv.saved_at) == ("new", None, world.clock.now())


def test_a_new_original_cv_keeps_the_facts(world: World) -> None:
    world.save(world.alice, PYTHON)
    world.portal.call(world.use_cases.save_original_cv, world.alice, "cv", "")
    assert world.numbers(world.alice) == [1]


def test_without_an_original_cv_reading_it_is_not_found(world: World) -> None:
    with pytest.raises(NotFound) as raised:
        world.portal.call(world.use_cases.get_original_cv, world.alice)
    assert raised.value.message == "Original CV ще не збережено."


def test_the_original_cv_is_per_user(world: World) -> None:
    world.portal.call(world.use_cases.save_original_cv, world.alice, "cv", "")
    with pytest.raises(NotFound):
        world.portal.call(world.use_cases.get_original_cv, world.bob)


@pytest.mark.parametrize("text", ["  ", "x" * (MAX_CV_LENGTH + 1)])
def test_an_invalid_original_cv_saves_nothing(world: World, text: str) -> None:
    world.portal.call(world.use_cases.save_original_cv, world.alice, "keep", "")
    with pytest.raises(InvalidValue):
        world.portal.call(world.use_cases.save_original_cv, world.alice, text, "")
    cv = world.portal.call(world.use_cases.get_original_cv, world.alice)
    assert cv.text == "keep"
