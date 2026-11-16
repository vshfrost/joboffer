"""Адаптери Greenhouse, Ashby, Lever, SmartRecruiters, Workable, DOU і Djinni на записаних відповідях (sources_fixtures:
синтетичні відповіді тієї самої структури, що в публічних API й стрічок, з вигаданими компаніями) і на інших вигаданих."""

from pathlib import Path

import httpx2
import pytest
from anyio.from_thread import BlockingPortal

from domain.profile.modes import WorkMode
from domain.sources.failure import FailureReason, SourceError
from domain.sources.kinds import FeedSource, Platform, SourceKind
from domain.sources.posting import Posting
from domain.sources.target import SourceTarget
from infrastructure.sources import build_sources
from infrastructure.sources.http import Fetcher
from infrastructure.sources.lever import TIMEOUT as LEVER_TIMEOUT
from tests.support.sources_net import (
    PAUSE,
    Routed,
    Scripted,
    ok,
    serve_fixture,
    serve_json,
)

FIXTURES = Path(__file__).parent / "sources_fixtures"
GREENHOUSE = SourceTarget(Platform.GREENHOUSE, "harborpay", "Harborpay")
ASHBY = SourceTarget(Platform.ASHBY, "cobaltledger", "Cobalt Ledger")
LEVER = SourceTarget(Platform.LEVER, "stayhaven", "Stay Haven")
SMARTRECRUITERS = SourceTarget(
    Platform.SMARTRECRUITERS, "lumenfreight", "Lumen Freight"
)
WORKABLE = SourceTarget(Platform.WORKABLE, "brightharbor", "Brightharbor")
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


# --- SmartRecruiters ------------------------------------------------------------------

BACKEND, DESIGNER, PLATFORM = (
    "744000900000001",
    "744000900000002",
    "744000900000003",
)
SR_PAGES = {"0": "smartrecruiters_list_1.json", "2": "smartrecruiters_list_2.json"}


def smartrecruiters() -> Routed:
    """Записані відповіді SmartRecruiters: список на двох сторінках (offset 0 і 2) і деталі кожної вакансії."""

    def route(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/v1/companies/lumenfreight/postings":
            return ok((FIXTURES / SR_PAGES[request.url.params["offset"]]).read_bytes())
        posting_id = request.url.path.rsplit("/", 1)[1]
        return ok((FIXTURES / f"smartrecruiters_detail_{posting_id}.json").read_bytes())

    return Routed(route)


def lists(served: Scripted) -> list[httpx2.Request]:
    return [r for r in served.requests if r.url.path.endswith("/postings")]


def details(served: Scripted) -> list[str]:
    return [
        r.url.path.rsplit("/", 1)[1] for r in served.requests if r not in lists(served)
    ]


def test_smartrecruiters_requests_the_list_in_pages_of_100(
    portal: BlockingPortal,
) -> None:
    served = smartrecruiters()

    portal.call(served.source(Platform.SMARTRECRUITERS).fetch, SMARTRECRUITERS)

    first = served.requests[0]
    assert first.url.host == "api.smartrecruiters.com"
    assert first.url.path == "/v1/companies/lumenfreight/postings"
    assert dict(first.url.params) == {"limit": "100", "offset": "0"}


def test_smartrecruiters_normalizes_the_recorded_posting(
    portal: BlockingPortal,
) -> None:
    postings = portal.call(
        smartrecruiters().source(Platform.SMARTRECRUITERS).fetch, SMARTRECRUITERS
    )

    backend = postings[0]
    assert backend.title == "Senior Backend Engineer"
    assert backend.url == (
        "https://jobs.smartrecruiters.com/LumenFreight/744000900000001-senior-backend-engineer"
    )
    assert backend.locations == ("Madrid, Madrid, Spain",)
    assert backend.countries == ("ES",)
    assert backend.work_mode is WorkMode.HYBRID
    assert backend.text == (
        "Company Description\nLumen Freight moves parcels across Europe.\n\n"
        "Job Description\nYou will build the routing service in Python.\n\n"
        "Design APIs\n\nOwn on-call\n\n"
        "Qualifications\n5+ years of backend work\n\n"
        "Additional Information\nHybrid: three days a week in Madrid."
    )
    assert "<" not in backend.text


def test_smartrecruiters_remote_flag_gives_remote_and_no_flag_gives_unknown(
    portal: BlockingPortal,
) -> None:
    backend, designer, platform = portal.call(
        smartrecruiters().source(Platform.SMARTRECRUITERS).fetch, SMARTRECRUITERS
    )

    assert platform.work_mode is WorkMode.REMOTE
    assert designer.work_mode is None
    assert designer.locations == ("Valencia, Valencia, Spain",)
    assert backend.work_mode is WorkMode.HYBRID


def test_smartrecruiters_collects_postings_from_two_pages(
    portal: BlockingPortal,
) -> None:
    served = smartrecruiters()

    postings = portal.call(
        served.source(Platform.SMARTRECRUITERS).fetch, SMARTRECRUITERS
    )

    assert [p.title for p in postings] == [
        "Senior Backend Engineer",
        "Junior Product Designer",
        "Platform Engineer",
    ]
    assert [r.url.params["offset"] for r in lists(served)] == ["0", "2"]
    assert details(served) == [BACKEND, DESIGNER, PLATFORM]


def test_smartrecruiters_asks_details_only_for_postings_that_pass_keep(
    portal: BlockingPortal,
) -> None:
    served = smartrecruiters()
    seen: list[Posting] = []

    def keep(posting: Posting) -> bool:
        seen.append(posting)
        return "junior" not in posting.title.lower()

    postings = portal.call(
        served.source(Platform.SMARTRECRUITERS).fetch, SMARTRECRUITERS, keep
    )

    assert [p.title for p in postings] == [
        "Senior Backend Engineer",
        "Platform Engineer",
    ]
    assert details(served) == [BACKEND, PLATFORM]
    # Фільтр бачить вакансію зі списку: назва й місце, ще без тексту.
    assert [(p.title, p.locations, p.work_mode, p.text) for p in seen[:1]] == [
        ("Senior Backend Engineer", ("Madrid, Madrid, Spain",), WorkMode.HYBRID, "")
    ]
    assert len(seen) == 3


def test_smartrecruiters_company_with_no_postings_is_not_found(
    portal: BlockingPortal,
) -> None:
    served = fixture("smartrecruiters_empty.json")

    with pytest.raises(SourceError) as error:
        portal.call(served.source(Platform.SMARTRECRUITERS).fetch, SMARTRECRUITERS)

    assert error.value.reason is FailureReason.NOT_FOUND
    assert len(served.requests) == 1


def test_smartrecruiters_stops_at_an_empty_page_even_if_total_is_larger(
    portal: BlockingPortal,
) -> None:
    served = Scripted(
        ok(b'{"totalFound": 5, "content": [{"id": "1", "name": "Engineer"}]}'),
        ok(b'{"totalFound": 5, "content": []}'),
        ok(b'{"postingUrl": "https://jobs.smartrecruiters.com/Acme/1-engineer"}'),
    )

    postings = portal.call(
        served.source(Platform.SMARTRECRUITERS).fetch,
        target(Platform.SMARTRECRUITERS, "acme"),
    )

    assert [r.url.params.get("offset") for r in served.requests[:2]] == ["0", "1"]
    assert [p.title for p in postings] == ["Engineer"]


def test_smartrecruiters_without_details_falls_back_to_the_canonical_url_and_no_text(
    portal: BlockingPortal,
) -> None:
    served = Scripted(
        ok(b'{"totalFound": 1, "content": [{"id": "77", "name": "Engineer"}]}'),
        ok(b"{}"),
    )

    (posting,) = portal.call(
        served.source(Platform.SMARTRECRUITERS).fetch,
        target(Platform.SMARTRECRUITERS, "Acme Inc"),
    )

    assert posting.url == "https://jobs.smartrecruiters.com/Acme%20Inc/77"
    assert posting.text == ""
    assert posting.locations == ()
    assert posting.work_mode is None


def test_smartrecruiters_drops_list_items_without_id_or_title(
    portal: BlockingPortal,
) -> None:
    served = serve_json(
        {"totalFound": 3, "content": ["junk", {"name": "No id"}, {"id": "5"}]}
    )

    postings = portal.call(
        served.source(Platform.SMARTRECRUITERS).fetch,
        target(Platform.SMARTRECRUITERS, "acme"),
    )

    assert postings == []
    assert len(served.requests) == 1


@pytest.mark.parametrize(
    "data",
    [
        [],
        "x",
        None,
        {"content": []},
        {"totalFound": "3", "content": []},
        {"totalFound": 1},
    ],
)
def test_smartrecruiters_rejects_unexpected_shapes(
    portal: BlockingPortal, data: object
) -> None:
    with pytest.raises(SourceError) as error:
        portal.call(
            serve_json(data).source(Platform.SMARTRECRUITERS).fetch, SMARTRECRUITERS
        )

    assert error.value.reason is FailureReason.INVALID


# --- Workable -------------------------------------------------------------------------


def test_workable_requests_the_widget_with_details(portal: BlockingPortal) -> None:
    served = fixture("workable.json")

    portal.call(served.source(Platform.WORKABLE).fetch, WORKABLE)

    (request,) = served.requests
    assert request.url.host == "apply.workable.com"
    assert request.url.path == "/api/v1/widget/accounts/brightharbor"
    assert dict(request.url.params) == {"details": "true"}


def test_workable_normalizes_the_recorded_account(portal: BlockingPortal) -> None:
    backend, data = portal.call(
        fixture("workable.json").source(Platform.WORKABLE).fetch, WORKABLE
    )

    assert backend.title == "Backend Engineer (Python)"
    assert backend.url == "https://apply.workable.com/j/A1B2C3D4E5"
    assert backend.text == "Build port tracking APIs.\n\nPython\n\nPostgreSQL"
    assert backend.locations == ("Valencia",)
    assert backend.countries == ("Spain",)
    assert backend.work_mode is None
    assert data.title == "Data Engineer"
    assert data.locations == ()
    assert data.countries == ("Portugal",)


def test_workable_telecommuting_is_remote(portal: BlockingPortal) -> None:
    backend, data = portal.call(
        fixture("workable.json").source(Platform.WORKABLE).fetch, WORKABLE
    )

    assert data.work_mode is WorkMode.REMOTE
    assert backend.work_mode is None


def test_workable_takes_the_place_from_top_level_fields_without_locations(
    portal: BlockingPortal,
) -> None:
    served = serve_json(
        {
            "jobs": [
                {
                    "title": "Engineer",
                    "url": "https://apply.workable.com/j/X1",
                    "description": "<p>Work.</p>",
                    "city": "Lisbon",
                    "country": "Portugal",
                }
            ]
        }
    )

    (posting,) = portal.call(served.source(Platform.WORKABLE).fetch, WORKABLE)

    assert (posting.locations, posting.countries) == (("Lisbon",), ("Portugal",))


def test_workable_rate_limit_is_retried_once_after_a_pause(
    portal: BlockingPortal,
) -> None:
    served = Scripted(
        httpx2.Response(429), ok((FIXTURES / "workable.json").read_bytes())
    )

    postings = portal.call(served.source(Platform.WORKABLE).fetch, WORKABLE)

    assert len(postings) == 2
    assert len(served.requests) == 2
    assert served.pauses == [PAUSE]


def test_workable_two_rate_limits_in_a_row_are_reported(portal: BlockingPortal) -> None:
    served = Scripted(httpx2.Response(429))

    with pytest.raises(SourceError) as error:
        portal.call(served.source(Platform.WORKABLE).fetch, WORKABLE)

    assert error.value.reason is FailureReason.RATE_LIMITED
    assert len(served.requests) == 2


def test_workable_account_without_vacancies_is_not_an_error(
    portal: BlockingPortal,
) -> None:
    served = fixture("workable_empty.json")

    assert portal.call(served.source(Platform.WORKABLE).fetch, WORKABLE) == []


@pytest.mark.parametrize("data", [[], "x", None, {"name": "Acme"}, {"jobs": {}}])
def test_workable_rejects_unexpected_shapes(
    portal: BlockingPortal, data: object
) -> None:
    with pytest.raises(SourceError) as error:
        portal.call(serve_json(data).source(Platform.WORKABLE).fetch, WORKABLE)

    assert error.value.reason is FailureReason.INVALID


def test_workable_unknown_account_is_not_found(portal: BlockingPortal) -> None:
    served = Scripted(httpx2.Response(404))

    with pytest.raises(SourceError) as error:
        portal.call(served.source(Platform.WORKABLE).fetch, WORKABLE)

    assert error.value.reason is FailureReason.NOT_FOUND


# --- keep: лише SmartRecruiters економить на деталях ----------------------------------


@pytest.mark.parametrize(
    ("kind", "name", "wanted"),
    [
        (Platform.GREENHOUSE, "greenhouse.json", GREENHOUSE),
        (Platform.ASHBY, "ashby.json", ASHBY),
        (Platform.LEVER, "lever.json", LEVER),
        (Platform.WORKABLE, "workable.json", WORKABLE),
        (FeedSource.DOU, "dou.xml", DOU),
        (FeedSource.DJINNI, "djinni.xml", DJINNI),
    ],
)
def test_other_adapters_ignore_keep(
    portal: BlockingPortal, kind: SourceKind, name: str, wanted: SourceTarget
) -> None:
    everything = portal.call(fixture(name).source(kind).fetch, wanted)

    kept = portal.call(fixture(name).source(kind).fetch, wanted, lambda _: False)

    assert kept == everything
    assert everything


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
