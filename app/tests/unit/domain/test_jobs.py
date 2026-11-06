"""Нова вакансія, відбиток тексту, пошук і причина приховування."""

from datetime import UTC, datetime

import pytest

from domain.jobs.dismiss import (
    MAX_DISMISS_BATCH,
    MAX_DISMISS_REASON_LENGTH,
    parse_dismiss_reason,
)
from domain.jobs.job import MAX_TEXT_LENGTH, NewJob
from domain.jobs.search import MAX_LIMIT, JobSearch, JobSearchDraft, JobStage
from domain.shared.errors import InvalidFields, InvalidValue
from domain.shared.fingerprint import text_fingerprint

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


def parse(**overrides: str) -> NewJob:
    fields = {"text": "Senior Python engineer", "url": "", "title": "", "company": ""}
    return NewJob.parse(**(fields | overrides))


def test_the_fingerprint_ignores_case_and_whitespace() -> None:
    assert text_fingerprint("  Senior   PYTHON\nengineer ") == text_fingerprint(
        "senior python engineer"
    )


def test_different_texts_have_different_fingerprints() -> None:
    assert text_fingerprint("senior python") != text_fingerprint("senior go")


def test_the_fingerprint_is_a_sha256_hex_digest() -> None:
    assert len(text_fingerprint("x")) == 64


def test_a_job_with_only_text_has_no_other_fields() -> None:
    job = parse()
    assert job == NewJob(text="Senior Python engineer")
    assert job.fingerprint == text_fingerprint("Senior Python engineer")


def test_the_text_is_trimmed_and_optional_fields_are_cleaned() -> None:
    job = parse(
        text="  body \n", url=" https://Acme.com/j/1/ ", title=" Dev ", company=" Acme "
    )
    assert (job.text, job.url, job.title, job.company) == (
        "body",
        "https://acme.com/j/1",
        "Dev",
        "Acme",
    )


def test_a_job_without_a_text_fingerprint_is_none() -> None:
    assert NewJob(text=None).fingerprint is None


@pytest.mark.parametrize("text", ["", "   \n\t"])
def test_an_empty_text_is_rejected_with_the_v1_message(text: str) -> None:
    with pytest.raises(InvalidFields) as caught:
        parse(text=text)
    assert [(p.field, p.message) for p in caught.value.problems] == [
        ("text", "Встав текст опису вакансії.")
    ]


def test_a_text_over_the_limit_is_rejected() -> None:
    with pytest.raises(InvalidFields) as caught:
        parse(text="x" * (MAX_TEXT_LENGTH + 1))
    assert [(p.field, p.message) for p in caught.value.problems] == [
        ("text", "Опис задовгий: більше 100000 символів.")
    ]
    assert parse(text="x" * MAX_TEXT_LENGTH).text == "x" * MAX_TEXT_LENGTH


def test_a_url_without_http_is_rejected_next_to_the_text_error() -> None:
    with pytest.raises(InvalidFields) as caught:
        parse(text="", url="example.com/job")
    assert [p.field for p in caught.value.problems] == ["text", "url"]


def test_a_linkedin_link_becomes_canonical_and_gives_the_id() -> None:
    job = parse(
        url="https://es.linkedin.com/comm/jobs/view/dev-at-acme-4012345678/?trackingId=x"
    )
    assert job.url == "https://www.linkedin.com/jobs/view/4012345678"
    assert job.linkedin_id == "4012345678"


def test_a_plain_link_has_no_linkedin_id() -> None:
    assert parse(url="https://acme.com/j/1").linkedin_id is None


def search(now: datetime = NOW, **fields: object) -> JobSearch:
    return JobSearch.parse(JobSearchDraft(**fields), now)  # type: ignore[arg-type]


def test_an_empty_search_has_no_restrictions() -> None:
    assert search() == JobSearch()


def test_search_fields_are_cleaned() -> None:
    found = search(query="  python   dev ", source=" manual ", days=" 7 ")
    assert (found.query, found.source) == ("python dev", "manual")
    assert found.since == datetime(2026, 10, 14, 12, 0, tzinfo=UTC)


def test_search_flags_and_limit_pass_through() -> None:
    found = search(needs_text=True, dismissed=True, limit=10)
    assert (found.needs_text, found.dismissed, found.limit) == (True, True, 10)


def test_a_search_has_no_stage_and_hides_nothing_by_default() -> None:
    found = search()
    assert (found.stage, found.hide_rejected) == (None, False)


@pytest.mark.parametrize(
    ("raw", "stage"),
    [
        ("open", JobStage.OPEN),
        (" in_progress ", JobStage.IN_PROGRESS),
        ("applied", JobStage.APPLIED),
    ],
)
def test_the_stage_is_parsed(raw: str, stage: JobStage) -> None:
    assert search(stage=raw).stage is stage


def test_hiding_rejected_applications_passes_through() -> None:
    assert search(hide_rejected=True).hide_rejected is True


@pytest.mark.parametrize("stage", ["all", "Open", "in-progress", "rejected"])
def test_an_unknown_stage_is_refused(stage: str) -> None:
    with pytest.raises(InvalidFields) as caught:
        search(stage=stage)
    assert [(p.field, p.message) for p in caught.value.problems] == [
        ("stage", "Етап — один з: open, in_progress, applied.")
    ]


@pytest.mark.parametrize("days", ["0", "-1", "3651", "abc", "1.5", "٣"])
def test_freshness_must_be_whole_days_in_range(days: str) -> None:
    with pytest.raises(InvalidFields) as caught:
        search(days=days)
    assert [(p.field, p.message) for p in caught.value.problems] == [
        ("days", "Свіжість — ціле число днів від 1 до 3650.")
    ]


def test_the_edge_values_of_freshness_are_accepted() -> None:
    assert search(days="1").since is not None
    assert search(days="3650").since is not None


def test_a_query_over_the_limit_is_rejected() -> None:
    with pytest.raises(InvalidFields) as caught:
        search(query="x" * 201)
    assert [(p.field, p.message) for p in caught.value.problems] == [
        ("query", "Запит задовгий: більше 200 символів.")
    ]
    assert search(query="x" * 200).query == "x" * 200


@pytest.mark.parametrize("limit", [0, -5, MAX_LIMIT + 1])
def test_the_limit_must_be_between_one_and_the_maximum(limit: int) -> None:
    with pytest.raises(InvalidFields) as caught:
        search(limit=limit)
    assert [(p.field, p.message) for p in caught.value.problems] == [
        ("limit", "Ліміт — від 1 до 200.")
    ]


def test_all_search_problems_are_reported_together() -> None:
    with pytest.raises(InvalidFields) as caught:
        search(query="x" * 201, days="0", limit=0)
    assert [p.field for p in caught.value.problems] == ["query", "days", "limit"]


def test_the_dismiss_reason_is_collapsed_to_single_spaces() -> None:
    assert parse_dismiss_reason("  не   цікаво\n зовсім ") == "не цікаво зовсім"


@pytest.mark.parametrize("reason", ["", "  \n "])
def test_an_empty_dismiss_reason_is_rejected(reason: str) -> None:
    with pytest.raises(InvalidValue) as caught:
        parse_dismiss_reason(reason)
    assert (caught.value.field, caught.value.message) == (
        "reason",
        "Вкажи причину приховування.",
    )


def test_a_long_dismiss_reason_is_rejected() -> None:
    with pytest.raises(InvalidValue) as caught:
        parse_dismiss_reason("x" * (MAX_DISMISS_REASON_LENGTH + 1))
    assert caught.value.message == "Причина задовга: більше 200 символів."
    assert len(parse_dismiss_reason("x" * MAX_DISMISS_REASON_LENGTH)) == 200


def test_the_batch_limit_is_fifty() -> None:
    assert MAX_DISMISS_BATCH == 50
