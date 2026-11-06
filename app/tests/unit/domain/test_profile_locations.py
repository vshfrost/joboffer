"""Локації пошуку: нормалізація, порядок, ліміти й тексти помилок v1."""

import pytest

from domain.profile.locations import LocationDraft, Locations, SearchLocation
from domain.profile.modes import WorkMode
from domain.shared.errors import FieldProblem, InvalidFields

ALL_MODES = ["remote", "hybrid", "onsite"]


def draft(
    place: str = "Valencia",
    aliases: tuple[str, ...] = (),
    work_modes: tuple[str, ...] = ("hybrid",),
) -> LocationDraft:
    return LocationDraft(place=place, aliases=aliases, work_modes=work_modes)


def parse(
    locations: list[LocationDraft] | None = None,
    work_modes: tuple[str, ...] = (),
    include_unknown_mode: bool = True,
    relocation: bool = False,
) -> Locations:
    return Locations.parse(
        work_modes=work_modes,
        locations=locations or [],
        include_unknown_mode=include_unknown_mode,
        relocation=relocation,
    )


def problems(**kwargs: object) -> tuple[FieldProblem, ...]:
    with pytest.raises(InvalidFields) as raised:
        parse(**kwargs)  # type: ignore[arg-type]
    return raised.value.problems


def test_an_empty_section_means_anywhere() -> None:
    assert parse() == Locations()
    assert parse().include_unknown_mode is True
    assert parse().relocation is False


def test_flags_and_global_modes_are_kept() -> None:
    parsed = parse(
        work_modes=("remote", "hybrid"), include_unknown_mode=False, relocation=True
    )
    assert parsed.work_modes == frozenset({WorkMode.REMOTE, WorkMode.HYBRID})
    assert parsed.include_unknown_mode is False
    assert parsed.relocation is True


def test_unknown_global_mode_is_rejected() -> None:
    assert problems(work_modes=("remote", "office")) == (
        FieldProblem("work_modes", "Невідомий формат роботи."),
    )


def test_locations_keep_the_order_they_were_given_in() -> None:
    parsed = parse([draft("Madrid"), draft("Barcelona"), draft("Valencia")])
    assert [location.place for location in parsed.locations] == [
        "Madrid",
        "Barcelona",
        "Valencia",
    ]


def test_a_location_is_normalized() -> None:
    parsed = parse(
        [
            draft(
                place="  Valencia   Spain ",
                aliases=("Валенсія", " валенсія ", "", "Valencia  Spain", "Valéncia"),
                work_modes=("onsite", "hybrid", "onsite"),
            )
        ]
    )
    assert parsed.locations == (
        SearchLocation(
            place="Valencia Spain",
            aliases=("Валенсія", "Valéncia"),
            work_modes=frozenset({WorkMode.HYBRID, WorkMode.ONSITE}),
        ),
    )


def test_a_blank_row_is_skipped() -> None:
    parsed = parse([draft("Madrid"), draft("", (), ()), draft("   ", ("  ",), ())])
    assert [location.place for location in parsed.locations] == ["Madrid"]


def test_a_blank_row_does_not_shift_the_index_of_later_errors() -> None:
    found = problems(
        locations=[draft("Madrid"), draft("", (), ()), draft("Cádiz", (), ())]
    )
    assert found == (
        FieldProblem(
            "locations.2.work_modes",
            "Для місця «Cádiz» обери хоч один формат: remote, hybrid чи onsite.",
        ),
    )


def test_a_location_without_a_mode_is_rejected_at_its_row() -> None:
    found = problems(locations=[draft("Madrid"), draft("Valencia", (), ())])
    assert found == (
        FieldProblem(
            "locations.1.work_modes",
            "Для місця «Valencia» обери хоч один формат: remote, hybrid чи onsite.",
        ),
    )


def test_an_unknown_mode_in_a_row_is_rejected_at_its_row() -> None:
    found = problems(locations=[draft("Madrid", (), ("remote", "office"))])
    assert found == (
        FieldProblem("locations.0.work_modes", "Невідомий формат роботи."),
    )


def test_aliases_without_a_place_are_rejected() -> None:
    found = problems(locations=[draft("", ("Валенсія",), ("remote",))])
    assert found == (
        FieldProblem(
            "locations.0.place", "Місце — від 1 до 100 символів, напр. Valencia."
        ),
    )


def test_a_place_over_one_hundred_characters_is_rejected() -> None:
    found = problems(locations=[draft("x" * 101)])
    assert found == (
        FieldProblem(
            "locations.0.place", "Місце — від 1 до 100 символів, напр. Valencia."
        ),
    )


def test_too_many_or_too_long_aliases_are_rejected() -> None:
    message = "Синонімів місця «Valencia» — до 20, кожен до 100 символів."
    many = tuple(f"alias-{number}" for number in range(21))
    assert problems(locations=[draft(aliases=many)]) == (
        FieldProblem("locations.0.aliases", message),
    )
    assert problems(locations=[draft(aliases=("y" * 101,))]) == (
        FieldProblem("locations.0.aliases", message),
    )


def test_the_same_place_in_another_case_is_rejected_at_the_second_row() -> None:
    found = problems(locations=[draft("Valencia"), draft("Madrid"), draft("VALENCIA")])
    assert found == (
        FieldProblem(
            "locations.2.place", "Місця в локаціях пошуку не мають повторюватись."
        ),
    )


def test_fifty_locations_fit_and_fifty_one_do_not() -> None:
    places = [draft(f"Place {number}") for number in range(51)]
    assert len(parse(places[:50]).locations) == 50
    assert problems(locations=places) == (
        FieldProblem("locations", "Локацій пошуку — до 50."),
    )


def test_problems_of_several_rows_are_all_reported() -> None:
    found = problems(
        locations=[draft("Madrid", (), ()), draft("Cádiz", (), ()), draft("madrid")]
    )
    assert [problem.field for problem in found] == [
        "locations.0.work_modes",
        "locations.1.work_modes",
        "locations.2.place",
    ]
