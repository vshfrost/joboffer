"""Гігієна тексту документа до рендеру: невидимі символи, переноси й табуляції всередині поля,
подвійні пробіли, маркери списку, шаблони «[…]»; покриття ключових слів по задуманому тексту."""

import pytest

from domain.documents.lint import (
    KeywordCoverage,
    LintCode,
    LintIssue,
    cv_text_issues,
    keyword_coverage,
    letter_text_issues,
)


def codes(issues: tuple[LintIssue, ...]) -> list[LintCode]:
    return [issue.code for issue in issues]


def test_a_clean_cv_has_no_issues() -> None:
    issues = cv_text_issues(
        ["Senior Backend Engineer", "Payments engineer", "Engineer · Acme"],
        ["Built payment APIs in Python", "Python · Postgres"],
    )

    assert issues == ()


def test_an_invisible_character_is_reported_with_its_code_point() -> None:
    issues = cv_text_issues(["Built\u200bAPIs"], [])

    assert codes(issues) == [LintCode.INVISIBLE_CHARS]
    assert "U+200B" in issues[0].message


@pytest.mark.parametrize("separator", ["\n", "\r\n", "\t", " ", " "])
def test_a_line_break_a_tab_or_an_odd_space_inside_a_bullet_is_reported(
    separator: str,
) -> None:
    issues = cv_text_issues([], [f"Built{separator}payment APIs"])

    assert codes(issues) == [LintCode.LINE_BREAK]
    assert "Built payment APIs" in issues[0].message


def test_a_double_space_inside_a_field_is_reported_but_outer_spaces_are_not() -> None:
    assert codes(cv_text_issues(["Payments  engineer"], [])) == [LintCode.DOUBLE_SPACE]
    assert cv_text_issues(["  Payments engineer  "], []) == ()


@pytest.mark.parametrize("marker", ["•", "- ", "– ", "— ", "* ", "· "])
def test_a_leading_list_marker_of_a_bullet_is_reported(marker: str) -> None:
    issues = cv_text_issues([], [f"{marker}Built payment APIs"])

    assert codes(issues) == [LintCode.LIST_MARKER]


def test_a_dash_inside_a_bullet_or_a_leading_dash_of_a_heading_is_not_a_marker() -> (
    None
):
    assert cv_text_issues(["- Engineer"], ["Built APIs - fast", "-5% latency"]) == ()


def test_a_placeholder_in_any_field_is_reported_with_its_text() -> None:
    issues = cv_text_issues(["Engineer · [Company]"], ["Built APIs"])

    assert codes(issues) == [LintCode.PLACEHOLDER]
    assert "[Company]" in issues[0].message


def test_one_issue_per_kind_lists_a_few_fields_and_counts_the_rest() -> None:
    bullets = [f"Built  service{i}" for i in range(5)]

    issues = cv_text_issues([], bullets)

    assert codes(issues) == [LintCode.DOUBLE_SPACE]
    assert issues[0].message.endswith("і ще 2.")


def test_different_problems_are_reported_together_in_a_stable_order() -> None:
    issues = cv_text_issues(
        ["Engineer · [Company]"], ["• Built\napis", "Built\u200bAPIs  fast"]
    )

    assert codes(issues) == [
        LintCode.INVISIBLE_CHARS,
        LintCode.LINE_BREAK,
        LintCode.DOUBLE_SPACE,
        LintCode.LIST_MARKER,
        LintCode.PLACEHOLDER,
    ]


def test_a_clean_letter_keeps_paragraphs_and_a_signoff_line_break() -> None:
    text = "Dear team,\n\nI build payment APIs.\nTwo lines here.\n\nBest regards,\nAlex"

    assert letter_text_issues(text) == ()


def test_a_letter_with_a_tab_a_double_space_or_an_invisible_char_is_reported() -> None:
    text = "Dear team,\n\nI build\tAPIs.\nI  like Python\u200b.\n\nBest regards,\nAlex"

    assert codes(letter_text_issues(text)) == [
        LintCode.INVISIBLE_CHARS,
        LintCode.LINE_BREAK,
        LintCode.DOUBLE_SPACE,
    ]


def test_a_letter_line_that_starts_with_a_list_marker_is_reported() -> None:
    text = "Dear team,\n\n- I build APIs.\n• I like Python.\n\nBest regards,\nAlex"

    issues = letter_text_issues(text)

    assert codes(issues) == [LintCode.LIST_MARKER]


def test_a_letter_placeholder_is_left_to_the_letter_itself() -> None:
    assert letter_text_issues("Dear [Hiring Manager],\n\nBest regards,\nAlex") == ()


def test_keyword_coverage_is_counted_on_whole_words_of_the_text() -> None:
    lines = ("Senior Backend Engineer", "Built Kafka pipelines at Google")

    coverage = keyword_coverage(("Kafka", "Backend", "Go", "kafka"), lines)

    assert coverage == KeywordCoverage(("Kafka", "Backend"), ("Go",))
    assert coverage.percent == 67


def test_keyword_coverage_spans_lines_and_ignores_case() -> None:
    coverage = keyword_coverage(
        ("continuous integration (ci)",), ("Continuous", "Integration (CI)")
    )

    assert coverage == KeywordCoverage(("continuous integration (ci)",), ())


def test_a_requirement_with_several_spellings_is_covered_by_any_one_of_them() -> None:
    coverage = keyword_coverage(
        ("Java | TypeScript | Python",), ("Built services in Python",)
    )

    assert coverage == KeywordCoverage(("Java | TypeScript | Python",), ())
    assert coverage.percent == 100


def test_a_requirement_with_no_spelling_in_the_cv_is_one_missing_keyword() -> None:
    coverage = keyword_coverage(
        ("Java | TypeScript | Python",), ("Built services in Go",)
    )

    assert coverage == KeywordCoverage((), ("Java | TypeScript | Python",))
    assert coverage.percent == 0


def test_a_spanish_spelling_is_covered_by_the_english_one_in_an_english_cv() -> None:
    coverage = keyword_coverage(
        ("gestión de estado | state management",), ("Owned frontend state management",)
    )

    assert coverage == KeywordCoverage(("gestión de estado | state management",), ())


def test_two_spellings_present_in_the_cv_count_as_one_covered_requirement() -> None:
    coverage = keyword_coverage(
        ("evals | evaluation", "Kafka"), ("Wrote evals and evaluation harnesses",)
    )

    assert coverage == KeywordCoverage(("evals | evaluation",), ("Kafka",))
    assert coverage.percent == 50


def test_java_is_not_found_in_javascript_inside_a_group() -> None:
    coverage = keyword_coverage(("Java | Kotlin",), ("Wrote JavaScript daily",))

    assert coverage == KeywordCoverage((), ("Java | Kotlin",))


def test_a_group_spelled_with_uneven_spaces_around_the_bar_still_matches() -> None:
    coverage = keyword_coverage(("Java|Kotlin",), ("Wrote Kotlin daily",))

    assert coverage == KeywordCoverage(("Java|Kotlin",), ())


def test_an_old_analysis_without_groups_keeps_its_coverage_percent() -> None:
    keywords = ("Kafka", "payment latency", "Node.js", "C#", "Go", "Backend")
    lines = ("Senior Backend Engineer", "Kafka, Node.js and C# at Google")

    coverage = keyword_coverage(keywords, lines)

    assert coverage == KeywordCoverage(
        ("Kafka", "Node.js", "C#", "Backend"), ("payment latency", "Go")
    )
    assert coverage.percent == 67


def test_without_keywords_there_is_no_coverage() -> None:
    assert keyword_coverage((), ("Senior Backend Engineer",)) is None
