"""Посилання LinkedIn на вакансію: id у будь-якій формі й канонічний вигляд."""

import pytest

from domain.jobs.linkedin import linkedin_job_id, linkedin_job_url


@pytest.mark.parametrize(
    "url",
    [
        "https://www.linkedin.com/jobs/view/4012345678",
        "https://www.linkedin.com/comm/jobs/view/4012345678",
        "https://es.linkedin.com/jobs/view/senior-engineer-at-acme-4012345678",
        "https://www.linkedin.com/comm/jobs/view/4012345678/?trackingId=abc%3D%3D&refId=x&midToken=y",
        "http://linkedin.com/jobs/view/4012345678?utm_source=mail",
    ],
)
def test_the_job_id_is_found_in_any_link_form(url: str) -> None:
    assert linkedin_job_id(url) == "4012345678"


@pytest.mark.parametrize(
    "url",
    [
        "",
        "https://example.com/jobs/view/4012345678",
        "https://www.linkedin.com/in/someone",
        "https://www.linkedin.com/jobs/view/123",
        "not a link",
    ],
)
def test_other_links_have_no_job_id(url: str) -> None:
    assert linkedin_job_id(url) is None


def test_the_canonical_link_has_no_comm_slug_or_tracking() -> None:
    assert (
        linkedin_job_url("4012345678")
        == "https://www.linkedin.com/jobs/view/4012345678"
    )
