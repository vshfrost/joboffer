"""Помилки домену: стабільні унікальні коди, без HTTP-атрибутів."""

from domain.shared.errors import (
    DomainError,
    FieldProblem,
    InvalidFields,
    InvalidValue,
)


def _all_subclasses(cls: type[DomainError]) -> list[type[DomainError]]:
    found: list[type[DomainError]] = []
    for sub in cls.__subclasses__():
        found += [sub, *_all_subclasses(sub)]
    return found


def test_every_error_has_own_stable_code() -> None:
    codes = [sub.code for sub in _all_subclasses(DomainError)]
    assert "invalid_value" in codes
    assert len(codes) == len(set(codes))


def test_invalid_value_carries_field_and_message() -> None:
    error = InvalidValue("title", "Назва порожня")
    assert (error.field, error.message, str(error)) == (
        "title",
        "Назва порожня",
        "Назва порожня",
    )
    assert error.code == "invalid_value"


def test_errors_know_nothing_about_http() -> None:
    error = InvalidValue("title", "x")
    assert not any(
        hasattr(error, name) for name in ("status", "status_code", "http_status")
    )


def test_invalid_fields_lists_every_problem_and_summarizes_them() -> None:
    error = InvalidFields(
        [FieldProblem("a", "Перша помилка."), FieldProblem("b.0.c", "Друга помилка.")]
    )
    assert error.problems == (
        FieldProblem("a", "Перша помилка."),
        FieldProblem("b.0.c", "Друга помилка."),
    )
    assert error.message == "Перша помилка. Друга помилка."
    assert (error.field, error.code) == ("a", "invalid_fields")
    assert isinstance(error, InvalidValue)
