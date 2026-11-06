"""Текст з недовірених джерел: один рядок, невидимі символи, HTML → простий текст."""

import pytest

from domain.shared.text import html_to_text, is_invisible, one_line, tidy_lines


def test_one_line_squeezes_inner_whitespace_and_trims_the_edges() -> None:
    assert one_line("  Re:\n\tnext   steps \r\n") == "Re: next steps"


@pytest.mark.parametrize("char", ["\u200b", "\u202e", "\ufeff", "\x07", "\ue000"])
def test_invisible_characters_are_detected(char: str) -> None:
    assert is_invisible(char)


@pytest.mark.parametrize("char", ["a", "я", " ", "\n", "\t", " ", "-"])
def test_visible_characters_and_whitespace_are_not_invisible(char: str) -> None:
    assert not is_invisible(char)


def test_tidy_lines_keeps_at_most_one_blank_line_and_trims_each_line() -> None:
    lines = ["  Hi  Taras ", "", "   ", "", "Thanks", "", ""]

    assert tidy_lines(lines) == "Hi Taras\n\nThanks"


def test_html_only_text_has_no_markup_scripts_or_styles() -> None:
    html = (
        "<html><head><title>t</title><style>p{color:red}</style></head><body>"
        "<script>alert(1)</script><h1>New jobs</h1><p>Senior   Backend at Acme</p>"
        "<div>Valencia</div><p>Fintech &amp; payments</p></body></html>"
    )

    assert html_to_text(html) == (
        "New jobs\n\nSenior Backend at Acme\n\nValencia\n\nFintech & payments"
    )


def test_html_to_text_handles_unbalanced_skipped_tags() -> None:
    assert html_to_text("</style>Hi<br/>there") == "Hi\n\nthere"
