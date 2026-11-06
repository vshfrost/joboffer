"""Дедуп між джерелами: «компанія + посада» без урахування юридичних форм, регістру й крапок."""

from datetime import timedelta

import pytest

from domain.sources.dedup import DEDUP_WINDOW, RecentJob, company_key, find_same_job
from domain.sources.kinds import FeedSource, Platform, source_label


def job(
    number: int,
    company: str | None = "Acme",
    title: str | None = "Backend Engineer",
    needs_text: bool = False,
) -> RecentJob:
    return RecentJob(number, company, title, needs_text)


def test_the_dedup_window_is_30_days() -> None:
    assert timedelta(days=30) == DEDUP_WINDOW


@pytest.mark.parametrize(
    "company",
    [
        "Acme",
        "ACME",
        "acme inc",
        "Acme Inc.",
        "Acme, Inc.",
        "Acme S.L.",
        "Acme SL",
        "Acme GmbH",
        "Acme Ltd",
        "Acme LLC",
        "Acme Limited",
        "Acme Corp.",
        "Acme  ",
    ],
)
def test_legal_forms_case_and_dots_do_not_change_the_company(company: str) -> None:
    assert company_key(company) == company_key("Acme")


def test_different_companies_have_different_keys() -> None:
    assert company_key("Acme") != company_key("Acme Labs")


def test_diacritics_do_not_change_the_company() -> None:
    assert company_key("Café Solutions S.L.") == company_key("CAFE SOLUTIONS")


def test_the_same_company_and_title_is_found() -> None:
    assert find_same_job([job(1)], "Acme", "Backend Engineer") == job(1)


def test_the_same_pair_is_found_despite_legal_forms_case_and_dots() -> None:
    found = find_same_job(
        [job(1, "Acme S.L.", "Back-end Engineer")], "ACME Inc", "back end engineer"
    )
    assert found == job(1, "Acme S.L.", "Back-end Engineer")


def test_another_company_is_not_the_same_job() -> None:
    assert find_same_job([job(1, "Globex")], "Acme", "Backend Engineer") is None


def test_another_title_is_not_the_same_job() -> None:
    assert (
        find_same_job([job(1, title="Frontend Engineer")], "Acme", "Backend Engineer")
        is None
    )


def test_an_empty_company_matches_nothing() -> None:
    assert find_same_job([job(1, company="")], "", "Backend Engineer") is None


def test_an_empty_title_matches_nothing() -> None:
    assert find_same_job([job(1, title="")], "Acme", "") is None


def test_a_job_without_company_or_title_is_not_matched() -> None:
    recent = [job(1, company=None), job(2, title=None)]
    assert find_same_job(recent, "Acme", "Backend Engineer") is None


def test_among_several_the_one_waiting_for_text_is_preferred() -> None:
    recent = [job(1), job(2, needs_text=True), job(3, needs_text=True)]
    found = find_same_job(recent, "Acme", "Backend Engineer")
    assert found is not None
    assert found.number == 2


def test_among_several_with_text_the_first_is_returned() -> None:
    found = find_same_job([job(4), job(5)], "Acme", "Backend Engineer")
    assert found is not None
    assert found.number == 4


def test_no_recent_jobs_match_nothing() -> None:
    assert find_same_job([], "Acme", "Backend Engineer") is None


@pytest.mark.parametrize(
    ("kind", "label"),
    [
        (Platform.GREENHOUSE, "ats:greenhouse"),
        (Platform.ASHBY, "ats:ashby"),
        (Platform.LEVER, "ats:lever"),
        (FeedSource.DOU, "rss:dou"),
        (FeedSource.DJINNI, "rss:djinni"),
    ],
)
def test_the_source_label_names_the_kind(
    kind: Platform | FeedSource, label: str
) -> None:
    assert source_label(kind) == label
