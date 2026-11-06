"""Email: нормалізація (регістр, пробіли) і формат. Без Gmail-трюків: крапки й плюс лишаються."""

import pytest

from domain.identity.email import Email
from domain.shared.errors import InvalidValue


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("taras@example.com", "taras@example.com"),
        ("  Taras@Example.COM \n", "taras@example.com"),
        ("v.lad+jobs@mail.example.org", "v.lad+jobs@mail.example.org"),
    ],
)
def test_parse_normalizes(raw: str, expected: str) -> None:
    assert Email.parse(raw).value == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "taras",
        "taras@",
        "@example.com",
        "a@b@example.com",
        "taras @example.com",
        "taras@example",
        "taras@.com",
        "taras@example.",
        f"{'a' * 65}@example.com",
        f"a@{'b' * 250}.com",
    ],
)
def test_parse_rejects_malformed(raw: str) -> None:
    with pytest.raises(InvalidValue) as caught:
        Email.parse(raw)
    assert caught.value.field == "email"


def test_local_part_of_64_characters_is_allowed() -> None:
    assert Email.parse(f"{'a' * 64}@example.com").value == f"{'a' * 64}@example.com"


def test_constructor_does_not_normalize() -> None:
    with pytest.raises(InvalidValue):
        Email("Taras@Example.com")


def test_emails_with_same_normalized_value_are_equal() -> None:
    assert Email.parse("TARAS@example.com") == Email.parse("taras@example.com")


@pytest.mark.parametrize(
    "raw",
    [
        "friend,victim@example.com",
        "friend;victim@example.com",
        "<victim>@example.com",
        "victim@example.com>",
        "(comment)victim@example.com",
        "[victim]@example.com",
        "a:b@example.com",
        '"victim"@example.com',
        "a\\b@example.com",
    ],
)
def test_parse_rejects_address_list_delimiters_that_would_add_recipients(
    raw: str,
) -> None:
    # `a,b@example.com` в заголовку `To:` — це два отримувачі: лист із кодом пішов би й на чужу адресу.
    with pytest.raises(InvalidValue) as caught:
        Email.parse(raw)
    assert caught.value.field == "email"
