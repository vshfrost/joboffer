"""Куди вести після входу: лише внутрішній шлях застосунку, решта — на головну (те саме правило, що й у вебі)."""

import pytest

from domain.identity.redirects import safe_next_path


@pytest.mark.parametrize(
    "path", ["/vacancies", "/vacancies?tab=archived", "/vacancies/42#notes", "/profile"]
)
def test_internal_path_is_kept(path: str) -> None:
    assert safe_next_path(path) == path


@pytest.mark.parametrize(
    "raw",
    [
        "https://evil.example",
        "//evil",
        "//evil.example/path",
        "/\\evil.example",
        "\\\\evil.example",
        "/\t/evil.example",
        "/\n/evil.example",
        "javascript:alert(1)",
        "vacancies",
        "",
        None,
    ],
)
def test_anything_else_goes_home(raw: str | None) -> None:
    assert safe_next_path(raw) == "/"


@pytest.mark.parametrize(
    "raw", ["/login", "/login?next=/vacancies", "/login/", "/login#x"]
)
def test_login_screen_is_never_the_target(raw: str) -> None:
    assert safe_next_path(raw) == "/"


def test_a_path_that_only_starts_like_login_is_fine() -> None:
    assert safe_next_path("/logins") == "/logins"
