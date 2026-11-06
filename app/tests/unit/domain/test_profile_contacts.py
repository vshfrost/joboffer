"""Контакти для шапки CV: нормалізація й тексти помилок v1."""

import pytest

from domain.profile.contacts import Contacts, ContactsDraft
from domain.shared.errors import FieldProblem, InvalidFields


def parse(**overrides: str) -> Contacts:
    return Contacts.parse(ContactsDraft(**overrides))


def problems(**overrides: str) -> tuple[FieldProblem, ...]:
    with pytest.raises(InvalidFields) as raised:
        parse(**overrides)
    return raised.value.problems


def test_contacts_are_optional() -> None:
    assert parse() == Contacts()


def test_names_and_cities_collapse_inner_whitespace() -> None:
    contacts = parse(
        full_name="  Taras   Prykladenko ", city="Valencia,\n Spain", phone=" +34  600 "
    )
    assert contacts.full_name == "Taras Prykladenko"
    assert contacts.city == "Valencia, Spain"
    assert contacts.phone == "+34 600"


def test_valid_contacts_are_kept() -> None:
    contacts = parse(
        email=" taras@example.com ",
        linkedin_url="https://www.linkedin.com/in/taras ",
        github_url=" https://github.com/taras",
        work_authorization="Spain / EU work authorization",
    )
    assert contacts.email == "taras@example.com"
    assert contacts.linkedin_url == "https://www.linkedin.com/in/taras"
    assert contacts.github_url == "https://github.com/taras"
    assert contacts.work_authorization == "Spain / EU work authorization"


@pytest.mark.parametrize(
    "email", ["taras", "taras@", "@example.com", "taras@example", "vl ad@example.com"]
)
def test_malformed_email_is_rejected(email: str) -> None:
    assert problems(email=email) == (
        FieldProblem("email", "Email виглядає некоректно, напр. name@example.com."),
    )


def test_linkedin_without_https_is_rejected() -> None:
    assert problems(linkedin_url="http://linkedin.com/in/taras") == (
        FieldProblem("linkedin_url", "LinkedIn — посилання з https://."),
    )


def test_github_without_https_is_rejected() -> None:
    assert problems(github_url="github.com/taras") == (
        FieldProblem("github_url", "GitHub — посилання з https://."),
    )


@pytest.mark.parametrize(
    "field",
    [
        "full_name",
        "phone",
        "city",
        "work_authorization",
    ],
)
def test_text_longer_than_two_hundred_characters_is_rejected(field: str) -> None:
    assert problems(**{field: "x" * 201}) == (
        FieldProblem(field, f"{field} — до 200 символів."),
    )


def test_two_hundred_characters_fit() -> None:
    assert parse(full_name="x" * 200).full_name == "x" * 200


def test_an_overlong_email_has_one_problem() -> None:
    assert problems(email="a" * 201 + "@example.com") == (
        FieldProblem("email", "email — до 200 символів."),
    )


def test_every_bad_field_is_reported() -> None:
    found = problems(email="nope", linkedin_url="x", github_url="y")
    assert [problem.field for problem in found] == [
        "email",
        "linkedin_url",
        "github_url",
    ]


def test_an_overlong_and_malformed_email_is_reported_once() -> None:
    assert problems(email="x" * 201) == (
        FieldProblem("email", "email — до 200 символів."),
    )
