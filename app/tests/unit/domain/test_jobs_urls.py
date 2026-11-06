"""Нормалізація URL вакансії: однакова вакансія з різних розсилок дає один URL."""

import pytest

from domain.jobs.urls import normalize_url
from domain.shared.errors import InvalidValue


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://Example.COM/Jobs/42", "https://example.com/Jobs/42"),
        ("https://example.com/jobs/42/", "https://example.com/jobs/42"),
        ("https://example.com", "https://example.com/"),
        ("https://example.com/", "https://example.com/"),
        ("https://example.com/jobs/42#apply", "https://example.com/jobs/42"),
        (
            "https://example.com/jobs/42?utm_source=x&id=7&UTM_Medium=y",
            "https://example.com/jobs/42?id=7",
        ),
        (
            "https://example.com/jobs?gclid=1&fbclid=2&refId=3&trackingId=4&trk=5&id=7",
            "https://example.com/jobs?id=7",
        ),
        ("https://example.com/jobs?id=7&x=", "https://example.com/jobs?id=7&x="),
        ("  http://example.com/a  ", "http://example.com/a"),
        ("HTTPS://example.com/a", "https://example.com/a"),
    ],
)
def test_the_url_is_normalized(raw: str, expected: str) -> None:
    assert normalize_url(raw) == expected


@pytest.mark.parametrize("raw", ["https://example.com/a?utm_source=x#f", "http://a.b/"])
def test_normalizing_twice_changes_nothing(raw: str) -> None:
    once = normalize_url(raw)
    assert normalize_url(once) == once


@pytest.mark.parametrize(
    "raw",
    [
        "example.com/jobs",
        "ftp://example.com/x",
        "javascript:alert(1)",
        "https://",
        "//x.com/a",
        "mailto:a@b.c",
    ],
)
def test_a_url_without_http_or_https_is_rejected(raw: str) -> None:
    with pytest.raises(InvalidValue) as caught:
        normalize_url(raw)
    assert caught.value.field == "url"
    assert caught.value.message == "Посилання має починатися з http:// або https://."
