"""План теми підготовки: розбір і межі кроку, ресурси, межі плану разом із виконаними, нотатка.

Тексти помилок і ліміти — як у v1 (`origin/main` `99a2007`, `core/domain/prep.py`).
"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest

from domain.prep.ids import StepId
from domain.prep.plan import (
    MAX_NOTE_LENGTH,
    MAX_RESOURCE_TITLE_LENGTH,
    MAX_RESOURCES,
    MAX_STEP_DETAILS_LENGTH,
    MAX_STEP_MINUTES,
    MAX_STEP_TITLE_LENGTH,
    MAX_STEPS,
    MAX_URL_LENGTH,
    MIN_STEPS,
    NewStep,
    PrepStep,
    Resource,
    StepKind,
    check_plan,
    parse_note,
)
from domain.shared.errors import InvalidValue

DONE = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)


def parse(**fields: Any) -> NewStep:
    values: dict[str, Any] = {
        "kind": "learn",
        "title": "Прочитати документацію",
        "minutes": 60,
        "details": "",
        "resources": [],
    } | fields
    return NewStep.parse(**values)


def rejected(**fields: Any) -> str:
    with pytest.raises(InvalidValue) as error:
        parse(**fields)
    return error.value.message


def new(kind: StepKind) -> NewStep:
    return NewStep(kind, "Крок", 30)


def kept(kind: StepKind, number: int = 1) -> PrepStep:
    return PrepStep(
        id=StepId(UUID(int=number)),
        number=number,
        position=number,
        kind=kind,
        title="Виконаний крок",
        minutes=30,
        details="",
        resources=(),
        done_at=DONE,
    )


def test_limits_are_the_v1_ones() -> None:
    assert (
        MIN_STEPS,
        MAX_STEPS,
        MAX_STEP_TITLE_LENGTH,
        MAX_STEP_DETAILS_LENGTH,
        MAX_RESOURCES,
        MAX_RESOURCE_TITLE_LENGTH,
        MAX_URL_LENGTH,
        MAX_STEP_MINUTES,
        MAX_NOTE_LENGTH,
    ) == (3, 12, 200, 2000, 10, 200, 500, 480, 2000)


def test_step_kinds_are_learn_practice_check() -> None:
    assert [kind.value for kind in StepKind] == ["learn", "practice", "check"]


def test_a_valid_step_is_parsed_with_all_its_fields() -> None:
    step = parse(
        kind="practice",
        title="Написати запит з JOIN",
        minutes=90,
        details="Результат: запит у репозиторії.",
        resources=[("Документація MySQL", "https://dev.mysql.com/doc/")],
    )
    assert step == NewStep(
        StepKind.PRACTICE,
        "Написати запит з JOIN",
        90,
        "Результат: запит у репозиторії.",
        (Resource("Документація MySQL", "https://dev.mysql.com/doc/"),),
    )


def test_details_and_resources_are_optional() -> None:
    step = parse()
    assert (step.details, step.resources) == ("", ())


@pytest.mark.parametrize("kind", ["Practice", " check ", "LEARN"])
def test_a_kind_is_case_and_space_insensitive(kind: str) -> None:
    assert parse(kind=kind).kind.value == kind.strip().lower()


@pytest.mark.parametrize("kind", ["", "read", "learn;check"])
def test_an_unknown_kind_is_rejected_listing_the_allowed_ones(kind: str) -> None:
    assert rejected(kind=kind) == f"kind {kind!r} — допустимо learn, practice, check."


def test_a_title_is_one_line() -> None:
    assert parse(title="  Прочитати \n документацію  ").title == (
        "Прочитати документацію"
    )


@pytest.mark.parametrize("title", ["", "   ", "т" * 201])
def test_a_title_outside_1_to_200_is_rejected(title: str) -> None:
    assert rejected(title=title) == "назва — від 1 до 200 символів."


@pytest.mark.parametrize("length", [1, 200])
def test_a_title_of_1_and_200_characters_is_valid(length: int) -> None:
    assert len(parse(title="т" * length).title) == length


@pytest.mark.parametrize("minutes", [-5, 0, 481, 10_000])
def test_minutes_outside_1_to_480_are_rejected(minutes: int) -> None:
    assert rejected(minutes=minutes) == "minutes — від 1 до 480."


@pytest.mark.parametrize("minutes", [1, 480])
def test_minutes_of_1_and_480_are_valid(minutes: int) -> None:
    assert parse(minutes=minutes).minutes == minutes


def test_details_are_trimmed() -> None:
    assert parse(details="  Що зробити.\n").details == "Що зробити."


def test_details_may_span_lines() -> None:
    assert parse(details="Перший.\nДругий.").details == "Перший.\nДругий."


def test_details_over_2000_characters_are_rejected() -> None:
    assert rejected(details="д" * 2001) == "details — до 2000 символів."


def test_details_of_2000_characters_are_valid() -> None:
    assert len(parse(details="д" * 2000).details) == 2000


def test_ten_resources_are_valid_and_eleven_are_rejected() -> None:
    link = ("Стаття", "https://example.com/a")
    assert len(parse(resources=[link] * 10).resources) == 10
    assert rejected(resources=[link] * 11) == "до 10 ресурсів."


@pytest.mark.parametrize("url", ["http://example.com", "https://example.com/a?b=1#c"])
def test_http_and_https_links_with_a_host_are_valid(url: str) -> None:
    assert parse(resources=[("Стаття", url)]).resources == (Resource("Стаття", url),)


def test_a_resource_title_and_url_are_trimmed() -> None:
    step = parse(resources=[("  Стаття \n про MySQL ", "  https://example.com/a  ")])
    assert step.resources == (Resource("Стаття про MySQL", "https://example.com/a"),)


@pytest.mark.parametrize(
    "url",
    [
        "",
        "example.com",
        "ftp://example.com",
        "javascript:alert(1)",
        "file:///etc/passwd",
        "https://",
        "http:///path",
        "https://exa mple.com",
        "https://example.com/a b",
        "https://example.com/a\tb",
        "https://example.com/" + "a" * 500,
    ],
)
def test_a_link_that_is_not_http_s_with_a_host_without_spaces_is_rejected(
    url: str,
) -> None:
    assert rejected(resources=[("Стаття", url)]) == (
        f"ресурс {url.strip()!r} — лише посилання http(s)://."
    )


def test_a_link_of_500_characters_is_valid() -> None:
    url = "https://example.com/" + "a" * (500 - len("https://example.com/"))
    assert len(url) == 500
    assert parse(resources=[("Стаття", url)]).resources[0].url == url


@pytest.mark.parametrize("title", ["", "   ", "т" * 201])
def test_a_resource_title_outside_1_to_200_is_rejected(title: str) -> None:
    assert rejected(resources=[(title, "https://example.com")]) == (
        "назва ресурсу — від 1 до 200 символів."
    )


def test_a_resource_title_of_200_characters_is_valid() -> None:
    step = parse(resources=[("т" * 200, "https://example.com")])
    assert len(step.resources[0].title) == 200


def test_three_new_steps_with_a_practice_and_a_check_make_a_plan() -> None:
    check_plan([], [new(StepKind.LEARN), new(StepKind.PRACTICE), new(StepKind.CHECK)])


def test_twelve_steps_make_a_plan() -> None:
    steps = [new(StepKind.LEARN)] * 10 + [new(StepKind.PRACTICE), new(StepKind.CHECK)]
    check_plan([], steps)


def test_two_steps_are_too_few() -> None:
    with pytest.raises(InvalidValue) as error:
        check_plan([], [new(StepKind.PRACTICE), new(StepKind.CHECK)])
    assert error.value.message == (
        "У плані 2 кроків (разом із виконаними 0) — треба від 3 до 12."
    )


def test_thirteen_steps_are_too_many() -> None:
    steps = [new(StepKind.LEARN)] * 11 + [new(StepKind.PRACTICE), new(StepKind.CHECK)]
    with pytest.raises(InvalidValue) as error:
        check_plan([], steps)
    assert error.value.message == (
        "У плані 13 кроків (разом із виконаними 0) — треба від 3 до 12."
    )


def test_done_steps_count_towards_the_limits() -> None:
    done = [kept(StepKind.PRACTICE, 1), kept(StepKind.CHECK, 2)]
    check_plan(done, [new(StepKind.LEARN)])
    with pytest.raises(InvalidValue) as error:
        check_plan(done, [new(StepKind.LEARN)] * 11)
    assert error.value.message == (
        "У плані 13 кроків (разом із виконаними 2) — треба від 3 до 12."
    )


def test_a_plan_of_only_done_steps_is_enough_when_it_has_the_kinds() -> None:
    check_plan(
        [kept(StepKind.LEARN, 1), kept(StepKind.PRACTICE, 2), kept(StepKind.CHECK, 3)],
        [],
    )


def test_a_plan_without_a_practice_step_is_rejected() -> None:
    with pytest.raises(InvalidValue) as error:
        check_plan([], [new(StepKind.LEARN), new(StepKind.LEARN), new(StepKind.CHECK)])
    assert error.value.message == "У плані немає жодного кроку practice."


def test_a_plan_without_a_check_step_is_rejected() -> None:
    with pytest.raises(InvalidValue) as error:
        check_plan(
            [], [new(StepKind.LEARN), new(StepKind.PRACTICE), new(StepKind.LEARN)]
        )
    assert error.value.message == "У плані немає жодного кроку check."


def test_a_done_practice_step_satisfies_the_practice_requirement() -> None:
    check_plan([kept(StepKind.PRACTICE)], [new(StepKind.LEARN), new(StepKind.CHECK)])


def test_a_done_check_step_satisfies_the_check_requirement() -> None:
    check_plan([kept(StepKind.CHECK)], [new(StepKind.LEARN), new(StepKind.PRACTICE)])


def test_a_note_is_trimmed() -> None:
    assert parse_note("  Зробив усе.\n") == "Зробив усе."


def test_an_empty_note_is_valid() -> None:
    assert parse_note("   ") == ""


def test_a_note_of_2000_characters_is_valid() -> None:
    assert len(parse_note("н" * 2000)) == 2000


def test_a_note_over_2000_characters_is_rejected() -> None:
    with pytest.raises(InvalidValue) as error:
        parse_note("н" * 2001)
    assert error.value.message == "Нотатка — до 2000 символів."
