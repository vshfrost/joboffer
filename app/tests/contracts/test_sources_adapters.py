"""Адаптери Greenhouse, Ashby, Lever, DOU і Djinni на записаних відповідях (sources_fixtures:
синтетичні відповіді тієї самої структури, що в публічних API й стрічок, з вигаданими компаніями) і на інших вигаданих."""

from pathlib import Path

import httpx2
import pytest
from anyio.from_thread import BlockingPortal

from domain.profile.modes import WorkMode
from domain.sources.failure import FailureReason, SourceError
from domain.sources.kinds import FeedSource, Platform, SourceKind
from domain.sources.target import SourceTarget
from infrastructure.sources import build_sources
from infrastructure.sources.http import Fetcher
from infrastructure.sources.lever import TIMEOUT as LEVER_TIMEOUT
from tests.support.sources_net import Scripted, serve_fixture, serve_json

FIXTURES = Path(__file__).parent / "sources_fixtures"
GREENHOUSE = SourceTarget(Platform.GREENHOUSE, "harborpay", "Harborpay")
ASHBY = SourceTarget(Platform.ASHBY, "cobaltledger", "Cobalt Ledger")
LEVER = SourceTarget(Platform.LEVER, "stayhaven", "Stay Haven")
DOU = SourceTarget(FeedSource.DOU, "category=Python&remote")
DJINNI = SourceTarget(FeedSource.DJINNI, "primary_keyword=Python")


def fixture(name: str) -> Scripted:
    return serve_fixture(FIXTURES, name)


def target(kind: SourceKind, slug: str) -> SourceTarget:
    return SourceTarget(kind, slug, "Acme")


def test_build_sources_covers_ats_platforms_and_rss_feeds() -> None:
    adapters = build_sources(Fetcher(httpx2.AsyncClient()))

    assert sorted(adapters) == sorted([*Platform, *FeedSource])


# --- Greenhouse -----------------------------------------------------------------------


def test_greenhouse_requests_the_board_with_content(portal: BlockingPortal) -> None:
    served = fixture("greenhouse.json")

    portal.call(served.source(Platform.GREENHOUSE).fetch, GREENHOUSE)

    (request,) = served.requests
    assert request.url.host == "boards-api.greenhouse.io"
    assert request.url.path == "/v1/boards/harborpay/jobs"
    assert request.url.params["content"] == "true"


def test_greenhouse_escaped_html_is_unescaped_into_plain_text(
    portal: BlockingPortal,
) -> None:
    postings = portal.call(
        fixture("greenhouse.json").source(Platform.GREENHOUSE).fetch, GREENHOUSE
    )

    assert len(postings) == 9
    python = postings[4]
    assert python.title == "Python Software Engineer"
    assert (
        python.url == "https://www.harborpay.example/jobs/9100100065?gh_jid=9100100065"
    )
    assert python.locations == ("Barcelona, Barcelona, Spain",)
    assert python.work_mode is None
    assert python.company is None
    assert python.text.startswith(
        "About Harborpay\nHarborpay is a global, fast-growing"
    )
    assert "<" not in python.text
    assert "&lt;" not in python.text


def test_greenhouse_keeps_text_of_unescaped_markup_and_drops_broken_items(
    portal: BlockingPortal,
) -> None:
    served = serve_json(
        {
            "jobs": [
                {
                    "title": "A",
                    "absolute_url": "https://x.example.com/a",
                    "content": "<p>Fish &amp; chips</p><script>alert(1)</script><p>Bye</p>",
                    "location": {"name": "Madrid"},
                },
                {"title": "", "absolute_url": "https://x.example.com/b"},
                {"title": "No URL"},
                "garbage",
                {"title": "C", "absolute_url": "https://x.example.com/c"},
            ]
        }
    )

    first, last = portal.call(served.source(Platform.GREENHOUSE).fetch, GREENHOUSE)

    assert first.text == "Fish & chips\n\nBye"
    assert (last.title, last.text, last.locations) == ("C", "", ())


def test_postings_come_out_sanitized(portal: BlockingPortal) -> None:
    served = serve_json(
        {
            "jobs": [
                {
                    "title": "Back\u200bend\n  Engineer",
                    "absolute_url": "https://x.example.com/a?utm_source=x#top",
                    "content": "Hi\u200b there",
                    "location": {"name": "Ma\u200bdrid"},
                }
            ]
        }
    )

    (posting,) = portal.call(served.source(Platform.GREENHOUSE).fetch, GREENHOUSE)

    assert posting.title == "Backend Engineer"
    assert posting.url == "https://x.example.com/a"
    assert posting.text == "Hi there"
    assert posting.locations == ("Madrid",)


@pytest.mark.parametrize("data", [[], "x", {"jobs": "x"}, {"jobs": None}, {}])
def test_greenhouse_rejects_unexpected_shapes(
    portal: BlockingPortal, data: object
) -> None:
    with pytest.raises(SourceError) as error:
        portal.call(serve_json(data).source(Platform.GREENHOUSE).fetch, GREENHOUSE)

    assert error.value.reason is FailureReason.INVALID


def test_greenhouse_unknown_board_is_not_found(portal: BlockingPortal) -> None:
    served = Scripted(httpx2.Response(404))

    with pytest.raises(SourceError) as error:
        portal.call(served.source(Platform.GREENHOUSE).fetch, GREENHOUSE)

    assert error.value.reason is FailureReason.NOT_FOUND


@pytest.mark.parametrize(
    ("platform", "host", "path", "body"),
    [
        (
            Platform.GREENHOUSE,
            "boards-api.greenhouse.io",
            b"/v1/boards/..%2Fadmin%3Fx%3D1/jobs?",
            {"jobs": []},
        ),
        (
            Platform.ASHBY,
            "api.ashbyhq.com",
            b"/posting-api/job-board/..%2Fadmin%3Fx%3D1",
            {"jobs": []},
        ),
        (Platform.LEVER, "api.lever.co", b"/v0/postings/..%2Fadmin%3Fx%3D1?", []),
    ],
)
def test_slug_with_slash_or_question_mark_is_escaped_in_the_url(
    portal: BlockingPortal, platform: Platform, host: str, path: bytes, body: object
) -> None:
    served = serve_json(body)

    portal.call(served.source(platform).fetch, target(platform, "../admin?x=1"))

    (request,) = served.requests
    assert request.url.raw_path.startswith(path)
    assert request.url.host == host


# --- Ashby ----------------------------------------------------------------------------


def test_ashby_requests_the_job_board(portal: BlockingPortal) -> None:
    served = fixture("ashby.json")

    portal.call(served.source(Platform.ASHBY).fetch, ASHBY)

    (request,) = served.requests
    assert request.url.host == "api.ashbyhq.com"
    assert request.url.path == "/posting-api/job-board/cobaltledger"


def test_ashby_normalizes_the_recorded_board(portal: BlockingPortal) -> None:
    postings = portal.call(fixture("ashby.json").source(Platform.ASHBY).fetch, ASHBY)

    assert len(postings) == 9
    backend = postings[2]
    assert backend.title == "Senior/Staff - Go Backend Engineer - remote friendly"
    assert backend.url.startswith("https://jobs.ashbyhq.com/cobaltledger/")
    assert backend.locations == ("Barcelona, Spain",)
    assert backend.countries == ("Spain",)
    assert backend.work_mode is WorkMode.REMOTE
    assert backend.text.startswith("- Our mission and customers")
    # workplaceType точніший за isRemote: «Hybrid» приходить з isRemote=true.
    assert postings[0].work_mode is WorkMode.HYBRID
    # Другорядні локації (з адресами офісів) теж збираються: країни — з адреси.
    assert postings[1].locations == (
        "Paris, France",
        "Berlin, Germany",
        "Milan, Italy",
        "Barcelona, Spain",
        "Belgrade, Serbia",
    )
    assert postings[1].countries == ("France", "Germany", "Italy", "Spain", "Serbia")


def test_ashby_workplace_type_beats_is_remote(portal: BlockingPortal) -> None:
    served = serve_json(
        {
            "jobs": [
                {
                    "title": "Hybrid but remote-flagged",
                    "jobUrl": "https://x.example.com/h",
                    "workplaceType": "Hybrid",
                    "isRemote": True,
                },
                {
                    "title": "Onsite but remote-flagged",
                    "jobUrl": "https://x.example.com/o",
                    "workplaceType": "OnSite",
                    "isRemote": True,
                },
            ]
        }
    )

    hybrid, onsite = portal.call(served.source(Platform.ASHBY).fetch, ASHBY)

    assert hybrid.work_mode is WorkMode.HYBRID
    assert onsite.work_mode is WorkMode.ONSITE


def test_ashby_skips_unlisted_and_falls_back_to_html_and_is_remote(
    portal: BlockingPortal,
) -> None:
    served = serve_json(
        {
            "jobs": [
                {
                    "title": "Hidden",
                    "jobUrl": "https://x.example.com/h",
                    "isListed": False,
                },
                {
                    "title": "Remote one",
                    "jobUrl": "https://x.example.com/r",
                    "descriptionHtml": "<p>Hello</p><p>World</p>",
                    "isRemote": True,
                    "location": "Remote",
                },
                {
                    "title": "Unspecified",
                    "jobUrl": "https://x.example.com/u",
                    "workplaceType": "Unspecified",
                    "isRemote": False,
                },
                {
                    "title": "Broken address",
                    "jobUrl": "https://x.example.com/b",
                    "address": 5,
                },
            ]
        }
    )

    remote, unspecified, broken = portal.call(
        served.source(Platform.ASHBY).fetch, ASHBY
    )

    assert (remote.text, remote.work_mode) == ("Hello\n\nWorld", WorkMode.REMOTE)
    assert unspecified.work_mode is None
    assert broken.countries == ()


@pytest.mark.parametrize("data", [[], {"jobs": {}}, {"jobs": None}, 5])
def test_ashby_rejects_unexpected_shapes(portal: BlockingPortal, data: object) -> None:
    with pytest.raises(SourceError) as error:
        portal.call(serve_json(data).source(Platform.ASHBY).fetch, ASHBY)

    assert error.value.reason is FailureReason.INVALID


# --- Lever ----------------------------------------------------------------------------


def test_lever_requests_postings_as_json_with_a_longer_timeout(
    portal: BlockingPortal,
) -> None:
    served = fixture("lever.json")

    portal.call(served.source(Platform.LEVER).fetch, LEVER)

    (request,) = served.requests
    assert request.url.host == "api.lever.co"
    assert request.url.path == "/v0/postings/stayhaven"
    assert request.url.params["mode"] == "json"
    assert request.extensions["timeout"]["read"] == LEVER_TIMEOUT
    assert LEVER_TIMEOUT > 30


def test_lever_normalizes_the_recorded_postings_without_the_country_field(
    portal: BlockingPortal,
) -> None:
    postings = portal.call(fixture("lever.json").source(Platform.LEVER).fetch, LEVER)

    assert len(postings) == 5
    backend = postings[0]
    assert backend.title == "Senior Backend Engineer"
    assert backend.url.startswith("https://jobs.lever.co/stayhaven/")
    assert backend.locations == ("Spain",)
    assert backend.work_mode is WorkMode.REMOTE
    # Країна акаунта (ES) не стає країною вакансії: «LATAM» лишається без країни.
    assert backend.countries == ()
    assert postings[2].locations == ("LATAM",)
    assert postings[2].countries == ()
    assert postings[1].work_mode is WorkMode.HYBRID
    assert backend.text.startswith("⭐ Who we are")
    assert "<" not in backend.text
    assert len(backend.text) > 3000


def test_lever_text_joins_intro_lists_and_closing(portal: BlockingPortal) -> None:
    served = serve_json(
        [
            {
                "text": "Engineer",
                "hostedUrl": "https://jobs.lever.co/acme/1",
                "descriptionPlain": "Intro.",
                "country": "ES",
                "lists": [
                    {"text": "Requirements", "content": "<li>Python</li><li>SQL</li>"},
                    "junk",
                ],
                "additionalPlain": "Bye.",
            },
            "garbage",
        ]
    )

    (posting,) = portal.call(
        served.source(Platform.LEVER).fetch, target(Platform.LEVER, "acme")
    )

    assert posting.text == "Intro.\n\nRequirements\nPython\n\nSQL\n\nBye."
    assert posting.countries == ()


@pytest.mark.parametrize("data", [{"jobs": []}, "x", None])
def test_lever_rejects_unexpected_shapes(portal: BlockingPortal, data: object) -> None:
    with pytest.raises(SourceError) as error:
        portal.call(serve_json(data).source(Platform.LEVER).fetch, LEVER)

    assert error.value.reason is FailureReason.INVALID


def test_lever_rate_limit_is_reported_after_one_retry(portal: BlockingPortal) -> None:
    served = Scripted(httpx2.Response(429))

    with pytest.raises(SourceError) as error:
        portal.call(served.source(Platform.LEVER).fetch, LEVER)

    assert error.value.reason is FailureReason.RATE_LIMITED
    assert len(served.requests) == 2


# --- DOU ------------------------------------------------------------------------------


def test_dou_requests_the_feed_with_the_exact_query(portal: BlockingPortal) -> None:
    served = fixture("dou.xml")

    portal.call(served.source(FeedSource.DOU).fetch, DOU)

    (request,) = served.requests
    assert (
        str(request.url)
        == "https://jobs.dou.ua/vacancies/feeds/?category=Python&remote"
    )


def test_dou_title_gives_position_company_places_and_country_ukraine(
    portal: BlockingPortal,
) -> None:
    postings = portal.call(fixture("dou.xml").source(FeedSource.DOU).fetch, DOU)

    assert len(postings) == 8
    first = postings[0]
    assert first.title == "Senior Python Engineer"
    assert first.company == "Nimbus Forge"
    assert first.url == "https://jobs.dou.ua/companies/nimbus-forge/vacancies/100101"
    assert first.locations == ("віддалено",)
    assert first.countries == ("Ukraine",)
    assert first.work_mode is WorkMode.REMOTE
    assert first.locations_in_text
    assert "<" not in first.text
    assert first.text.startswith("About")
    # Місто й «за кордоном» — серед локацій, зарплата з екрануванням теж розібрана.
    assert postings[3].locations == ("Львів", "за кордоном", "віддалено")
    assert postings[4].locations == ("до $1500", "віддалено")
    assert (
        postings[2].title
        == "QA Automation Engineer (Python / API / Mobile) | Content Hub"
    )


# --- Djinni ---------------------------------------------------------------------------


def test_djinni_requests_the_feed_with_the_exact_query(portal: BlockingPortal) -> None:
    served = fixture("djinni.xml")

    portal.call(served.source(FeedSource.DJINNI).fetch, DJINNI)

    (request,) = served.requests
    assert str(request.url) == "https://djinni.co/jobs/rss/?primary_keyword=Python"


def test_djinni_title_with_company_after_u_and_no_structured_location(
    portal: BlockingPortal,
) -> None:
    postings = portal.call(
        fixture("djinni.xml").source(FeedSource.DJINNI).fetch, DJINNI
    )

    assert len(postings) == 8
    python = postings[0]
    # Трекінг і слеш наприкінці прибрано: це канонічний URL вакансії.
    assert python.url == "https://djinni.co/jobs/900001-python-developer"
    assert (python.title, python.company, python.locations, python.countries) == (
        "Python Developer",
        None,
        (),
        (),
    )
    assert python.locations_in_text
    assert "<" not in python.text
    assert "\xa0" not in python.text
    # «Middle PHP (Symfony) Developer у Brightloop» → посада й компанія.
    brightloop = postings[5]
    assert (brightloop.title, brightloop.company) == (
        "Middle PHP (Symfony) Developer",
        "Brightloop",
    )
    assert postings[3].work_mode is WorkMode.REMOTE
