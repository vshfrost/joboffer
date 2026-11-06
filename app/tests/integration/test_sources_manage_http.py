"""Керування джерелами через HTTP наскрізь: сесія й CSRF, список зі станом останнього прогону, додавання
компанії (з пробним запитом до ATS) і стрічки, вимкнення, видалення зі станом, 404 для чужого й
неіснуючого, збої посеред справжнього прогону."""

import re
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any

import httpx2
import pytest
from anyio.from_thread import BlockingPortal
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from application.sources.refresh import SourceRunUseCases
from bootstrap.api import container_of, create_app
from bootstrap.settings import Settings
from domain.sources.failure import FailureReason
from domain.sources.kinds import FeedSource, Platform, SourceKind
from domain.sources.posting import Posting
from domain.sources.run import RefreshReport
from infrastructure.system import RandomIds
from tests.integration.test_profile_http import Session, make_client
from tests.support.clock import FakeClock
from tests.support.source_runs import ScriptedSource, registry

__all__ = ["make_client"]

UUID_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
)
RAN_AT = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
UNKNOWN_ID = "7d444840-9dc0-4f1e-8e44-3f0d3a9e1c11"
type ClientFactory = Callable[[], TestClient]


class ProbeNet:
    """Мережа пробного запиту: слаг (останній сегмент шляху) → відповідь; решта слагів існують."""

    def __init__(self) -> None:
        self.outcomes: dict[str, httpx2.Response | Exception] = {}
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        outcome = self.outcomes.get(request.url.path.rsplit("/", 1)[-1])
        if isinstance(outcome, Exception):
            raise outcome
        return outcome or httpx2.Response(200, content=b"{}")


@pytest.fixture
def probe_net() -> ProbeNet:
    return ProbeNet()


@pytest.fixture
def sources_client(
    make_client: object, database_url: str, probe_net: ProbeNet
) -> Iterator[ClientFactory]:
    """Клієнти застосунку з підміненою мережею пробного запиту (`make_client` чистить базу)."""
    opened: list[TestClient] = []

    def factory() -> TestClient:
        app = create_app(
            Settings(environment="test", database_url=database_url),
            probe_transport=httpx2.MockTransport(probe_net),
        )
        client = TestClient(app, base_url="https://testserver")
        client.__enter__()
        opened.append(client)
        return client

    yield factory
    for client in opened:
        client.__exit__(None, None, None)


COUNTS = {
    "source_company_runs": "SELECT count(*) FROM source_company_runs",
    "source_feed_runs": "SELECT count(*) FROM source_feed_runs",
}


class Db:
    def __init__(self, portal: BlockingPortal, engine: AsyncEngine) -> None:
        self._portal = portal
        self._engine = engine

    def execute(self, sql: str) -> None:
        async def run() -> None:
            async with self._engine.begin() as conn:
                await conn.execute(text(sql))

        self._portal.call(run)

    def count(self, table: str) -> int:
        async def run() -> int:
            async with self._engine.connect() as conn:
                return int((await conn.execute(text(COUNTS[table]))).scalar_one())

        return self._portal.call(run)


class SourcesSession:
    def __init__(self, session: Session, db: Db) -> None:
        self.client = session.client
        self.csrf = session.csrf
        self.db = db

    def listing(self) -> httpx2.Response:
        return self.client.get("/sources")

    def add_company(self, **body: object) -> httpx2.Response:
        return self.client.post("/sources/companies", json=body, headers=self.csrf)

    def add_feed(self, **body: object) -> httpx2.Response:
        return self.client.post("/sources/feeds", json=body, headers=self.csrf)

    def patch(self, kind: str, source_id: str, **body: object) -> httpx2.Response:
        return self.client.patch(
            f"/sources/{kind}/{source_id}", json=body, headers=self.csrf
        )

    def delete(self, kind: str, source_id: str) -> httpx2.Response:
        return self.client.delete(f"/sources/{kind}/{source_id}", headers=self.csrf)

    def company(self, slug: str, platform: str = "greenhouse") -> str:
        response = self.add_company(platform=platform, slug=slug, name=slug.title())
        assert response.status_code == 201, response.text
        return str(response.json()["id"])

    def feed(self, query: str, source: str = "dou") -> str:
        response = self.add_feed(source=source, query=query)
        assert response.status_code == 201, response.text
        return str(response.json()["id"])

    def refresh(
        self, scripts: dict[SourceKind, ScriptedSource] | None = None
    ) -> RefreshReport:
        """Справжній прогін усіх джерел на тій самій базі; час стоїть на `RAN_AT`."""
        everything = scripts or registry([*Platform, *FeedSource], [])
        use_cases = SourceRunUseCases(
            container_of(self.client.app).unit_of_work,  # type: ignore[arg-type]
            everything,
            FakeClock(RAN_AT),
            RandomIds(),
        )
        assert self.client.portal is not None
        return self.client.portal.call(use_cases.refresh_sources)

    def job_sources(self) -> list[str]:
        items = self.client.get("/jobs").json()["items"]
        return [str(item["source"]) for item in items]


@pytest.fixture
def db(portal: BlockingPortal, engine: AsyncEngine) -> Db:
    return Db(portal, engine)


@pytest.fixture
def alice(sources_client: ClientFactory, db: Db) -> SourcesSession:
    return SourcesSession(Session(sources_client(), "alice@example.com"), db)


@pytest.fixture
def bob(sources_client: ClientFactory, db: Db) -> SourcesSession:
    return SourcesSession(Session(sources_client(), "bob@example.com"), db)


def posting(title: str, company: str | None = None) -> Posting:
    return Posting(
        title=title,
        url=f"https://jobs.example/{title.replace(' ', '-')}",
        text=f"Опис вакансії «{title}»",
        company=company,
    )


def status_and_code(response: httpx2.Response) -> tuple[int, object]:
    """Статус і код помилки; у відповіді без коду (напр. 404 неіснуючого маршруту) код — `None`."""
    body = response.json() if response.content else {}
    return response.status_code, body.get("code")


def field_of(response: httpx2.Response) -> str:
    return str(response.json()["field_errors"][0]["field"])


# --- сесія й CSRF ---------------------------------------------------------------------------


def test_every_route_requires_a_session(sources_client: ClientFactory) -> None:
    client = sources_client()
    for method, path in (
        ("GET", "/sources"),
        ("POST", "/sources/companies"),
        ("POST", "/sources/feeds"),
        ("PATCH", f"/sources/companies/{UNKNOWN_ID}"),
        ("PATCH", f"/sources/feeds/{UNKNOWN_ID}"),
        ("DELETE", f"/sources/companies/{UNKNOWN_ID}"),
        ("DELETE", f"/sources/feeds/{UNKNOWN_ID}"),
    ):
        response = client.request(method, path)
        assert status_and_code(response) == (401, "not_authenticated"), (method, path)


def test_unsafe_requests_require_the_csrf_token(
    alice: SourcesSession, probe_net: ProbeNet
) -> None:
    company, feed = alice.company("acme"), alice.feed("category=Python")
    probe_net.requests.clear()
    client = alice.client

    attempts = (
        client.post("/sources/companies", json={"platform": "lever", "slug": "globex"}),
        client.post(
            "/sources/feeds", json={"source": "djinni", "query": "primary_keyword=PHP"}
        ),
        client.patch(f"/sources/companies/{company}", json={"enabled": False}),
        client.patch(f"/sources/feeds/{feed}", json={"enabled": False}),
        client.delete(f"/sources/companies/{company}"),
        client.delete(f"/sources/feeds/{feed}"),
    )

    assert [status_and_code(r) for r in attempts] == [(403, "csrf_failed")] * 6
    assert probe_net.requests == []
    body = alice.listing().json()
    assert [(c["slug"], c["enabled"]) for c in body["companies"]] == [("acme", True)]
    assert [(f["query"], f["enabled"]) for f in body["feeds"]] == [
        ("category=Python", True)
    ]


# --- список ---------------------------------------------------------------------------------


def test_a_new_user_has_no_sources(alice: SourcesSession) -> None:
    response = alice.listing()

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert (body["companies"], body["feeds"]) == ([], [])


def test_sources_without_a_run_have_a_null_last_run(alice: SourcesSession) -> None:
    company, feed = alice.company("acme"), alice.feed("category=Python&remote")

    body = alice.listing().json()

    assert body["companies"] == [
        {
            "id": company,
            "platform": "greenhouse",
            "slug": "acme",
            "name": "Acme",
            "enabled": True,
            "last_run": None,
        }
    ]
    assert body["feeds"] == [
        {
            "id": feed,
            "source": "dou",
            "query": "category=Python&remote",
            "enabled": True,
            "last_run": None,
        }
    ]
    assert UUID_PATTERN.fullmatch(company)
    assert UUID_PATTERN.fullmatch(feed)


def test_last_run_has_counters_utc_time_and_no_error(alice: SourcesSession) -> None:
    alice.company("acme")
    alice.feed("category=Python")
    scripts = registry([*Platform, *FeedSource], [])
    scripts[Platform.GREENHOUSE].postings["acme"] = [
        posting("Backend Engineer"),
        posting("Data Engineer"),
    ]
    scripts[FeedSource.DOU].postings["category=Python"] = [
        posting("Platform Engineer", company="Globex")
    ]

    alice.refresh(scripts)

    body = alice.listing().json()
    assert body["companies"][0]["last_run"] == {
        "ran_at": "2026-01-01T09:00:00Z",
        "found": 2,
        "imported": 2,
        "filtered": 0,
        "duplicate": 0,
        "completed": 0,
        "error": None,
    }
    assert body["feeds"][0]["last_run"]["found"] == 1
    assert sorted(alice.job_sources()) == [
        "ats:greenhouse",
        "ats:greenhouse",
        "rss:dou",
    ]


@pytest.mark.parametrize(
    "code",
    [reason.value for reason in FailureReason],
)
def test_last_run_error_is_one_of_the_seven_codes(
    alice: SourcesSession, code: str
) -> None:
    alice.company("acme")
    scripts = registry([*Platform, *FeedSource], [])
    if code == "unsupported":
        del scripts[Platform.GREENHOUSE]
    else:
        scripts[Platform.GREENHOUSE].failures["acme"] = FailureReason(code)

    alice.refresh(scripts)

    last_run = alice.listing().json()["companies"][0]["last_run"]
    assert last_run["error"] == code
    assert (last_run["found"], last_run["imported"]) == (0, 0)


def test_the_list_shows_only_own_sources(
    alice: SourcesSession, bob: SourcesSession
) -> None:
    alice.company("acme")
    alice.feed("category=Python")
    bob.company("globex", platform="lever")

    assert [c["slug"] for c in bob.listing().json()["companies"]] == ["globex"]
    assert bob.listing().json()["feeds"] == []
    assert [c["slug"] for c in alice.listing().json()["companies"]] == ["acme"]


def test_disabled_sources_stay_in_the_list(alice: SourcesSession) -> None:
    company = alice.company("acme")
    alice.patch("companies", company, enabled=False)

    (row,) = alice.listing().json()["companies"]

    assert (row["slug"], row["enabled"]) == ("acme", False)


# --- додати компанію ------------------------------------------------------------------------


def test_a_company_is_added_after_one_light_probe_request(
    alice: SourcesSession, probe_net: ProbeNet
) -> None:
    response = alice.add_company(platform="greenhouse", slug="acme", name="Acme Inc")

    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert UUID_PATTERN.fullmatch(body["id"])
    assert {k: v for k, v in body.items() if k != "id"} == {
        "platform": "greenhouse",
        "slug": "acme",
        "name": "Acme Inc",
        "enabled": True,
        "last_run": None,
    }
    (request,) = probe_net.requests
    assert (request.url.host, request.url.path) == (
        "boards-api.greenhouse.io",
        "/v1/boards/acme",
    )
    assert alice.listing().json()["companies"] == [body]


@pytest.mark.parametrize(
    "body",
    [
        {"platform": "lever", "slug": "stayhaven"},
        {"platform": "lever", "slug": "stayhaven", "name": ""},
    ],
)
def test_a_company_without_a_name_is_named_after_its_slug(
    alice: SourcesSession, body: dict[str, str]
) -> None:
    response = alice.add_company(**body)

    assert response.status_code == 201
    assert response.json()["name"] == "stayhaven"


def test_an_unknown_platform_is_refused_at_the_platform_field(
    alice: SourcesSession, probe_net: ProbeNet
) -> None:
    response = alice.add_company(platform="workday", slug="acme", name="Acme")

    assert response.status_code == 422
    assert field_of(response) == "platform"
    assert probe_net.requests == []
    assert alice.listing().json()["companies"] == []


def test_a_missing_platform_is_refused_at_the_platform_field(
    alice: SourcesSession,
) -> None:
    response = alice.add_company(slug="acme")

    assert status_and_code(response) == (422, "invalid_request")
    assert field_of(response) == "platform"


@pytest.mark.parametrize(
    "slug", ["", "a b", "../etc/passwd", "acme?x=1", "acme/jobs", "-acme"]
)
def test_a_slug_with_forbidden_characters_is_refused_at_the_slug_field(
    alice: SourcesSession, probe_net: ProbeNet, slug: str
) -> None:
    response = alice.add_company(platform="greenhouse", slug=slug, name="Acme")

    assert response.status_code == 422
    assert field_of(response) == "slug"
    assert probe_net.requests == []
    assert alice.listing().json()["companies"] == []


def test_a_duplicate_company_is_refused_at_the_slug_field_without_a_probe(
    alice: SourcesSession, probe_net: ProbeNet
) -> None:
    alice.company("acme")
    probe_net.requests.clear()

    response = alice.add_company(platform="greenhouse", slug="acme", name="Other")

    assert response.status_code == 422
    assert field_of(response) == "slug"
    assert "вже є" in response.json()["message"]
    assert probe_net.requests == []
    assert len(alice.listing().json()["companies"]) == 1


def test_the_same_slug_on_another_platform_or_for_another_user_is_another_company(
    alice: SourcesSession, bob: SourcesSession
) -> None:
    alice.company("acme")

    assert alice.add_company(platform="lever", slug="acme").status_code == 201
    assert bob.add_company(platform="greenhouse", slug="acme").status_code == 201


def test_a_company_unknown_to_the_platform_is_refused_with_the_exact_text(
    alice: SourcesSession, probe_net: ProbeNet
) -> None:
    probe_net.outcomes["nope"] = httpx2.Response(404)

    response = alice.add_company(platform="greenhouse", slug="nope", name="Nope")

    assert response.status_code == 422
    assert field_of(response) == "slug"
    assert response.json()["message"] == (
        "Компанії зі слагом «nope» на greenhouse не знайдено."
    )
    assert alice.listing().json()["companies"] == []


@pytest.mark.parametrize(
    ("outcome", "code"),
    [
        (httpx2.Response(500), "unavailable"),
        (httpx2.Response(429), "rate_limited"),
        (httpx2.Response(403), "rejected"),
        (httpx2.ReadTimeout("slow"), "timeout"),
    ],
)
def test_a_probe_failure_is_refused_with_the_exact_text(
    alice: SourcesSession,
    probe_net: ProbeNet,
    outcome: httpx2.Response | Exception,
    code: str,
) -> None:
    probe_net.outcomes["acme"] = outcome

    response = alice.add_company(platform="ashby", slug="acme", name="Acme")

    assert response.status_code == 422
    assert field_of(response) == "slug"
    assert response.json()["message"] == (
        f"Не вдалося перевірити слаг ({code}) — спробуй пізніше."
    )
    assert alice.listing().json()["companies"] == []


# --- додати стрічку -------------------------------------------------------------------------


def test_a_feed_is_added_enabled_and_without_a_run(alice: SourcesSession) -> None:
    response = alice.add_feed(source="dou", query="category=Python&remote")

    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert UUID_PATTERN.fullmatch(body["id"])
    assert {k: v for k, v in body.items() if k != "id"} == {
        "source": "dou",
        "query": "category=Python&remote",
        "enabled": True,
        "last_run": None,
    }
    assert alice.listing().json()["feeds"] == [body]


def test_a_djinni_feed_with_a_primary_keyword_is_added(alice: SourcesSession) -> None:
    response = alice.add_feed(
        source="djinni", query="primary_keyword=Python&exp_level=3y"
    )

    assert response.status_code == 201


def test_an_unknown_feed_source_is_refused_at_the_source_field(
    alice: SourcesSession,
) -> None:
    response = alice.add_feed(source="linkedin", query="category=Python")

    assert response.status_code == 422
    assert field_of(response) == "source"
    assert alice.listing().json()["feeds"] == []


@pytest.mark.parametrize(
    "query", ["", "category=Python remote", "category=Python&", "category=Py%thon"]
)
def test_a_query_not_in_name_value_form_is_refused_at_the_query_field(
    alice: SourcesSession, query: str
) -> None:
    response = alice.add_feed(source="dou", query=query)

    assert response.status_code == 422
    assert field_of(response) == "query"
    assert "name=value" in response.json()["message"]
    assert alice.listing().json()["feeds"] == []


@pytest.mark.parametrize(
    ("source", "query", "required"),
    [
        ("dou", "remote", "category"),
        ("djinni", "category=Python", "primary_keyword"),
    ],
)
def test_a_feed_without_its_required_parameter_is_refused_at_the_query_field(
    alice: SourcesSession, source: str, query: str, required: str
) -> None:
    response = alice.add_feed(source=source, query=query)

    assert response.status_code == 422
    assert field_of(response) == "query"
    assert required in response.json()["message"]
    assert alice.listing().json()["feeds"] == []


def test_a_duplicate_feed_is_refused_at_the_query_field(
    alice: SourcesSession, bob: SourcesSession
) -> None:
    alice.feed("category=Python&remote")

    response = alice.add_feed(source="dou", query="category=Python&remote")

    assert response.status_code == 422
    assert field_of(response) == "query"
    assert "вже є" in response.json()["message"]
    assert len(alice.listing().json()["feeds"]) == 1
    # У іншого користувача така стрічка своя.
    assert bob.add_feed(source="dou", query="category=Python&remote").status_code == 201


# --- вимкнути, увімкнути --------------------------------------------------------------------


def test_a_company_is_disabled_and_enabled_and_keeps_its_last_run(
    alice: SourcesSession,
) -> None:
    company = alice.company("acme")
    scripts = registry([*Platform, *FeedSource], [])
    scripts[Platform.GREENHOUSE].postings["acme"] = [posting("Backend Engineer")]
    alice.refresh(scripts)

    off = alice.patch("companies", company, enabled=False)
    on = alice.patch("companies", company, enabled=True)

    assert off.status_code == on.status_code == 200
    assert off.headers["cache-control"] == "no-store"
    assert (off.json()["id"], off.json()["enabled"]) == (company, False)
    assert off.json()["last_run"]["found"] == 1
    assert (on.json()["enabled"], on.json()["last_run"]["found"]) == (True, 1)
    assert alice.listing().json()["companies"] == [on.json()]


def test_a_feed_is_disabled_and_enabled(alice: SourcesSession) -> None:
    feed = alice.feed("category=Python")

    off = alice.patch("feeds", feed, enabled=False)
    on = alice.patch("feeds", feed, enabled=True)

    assert off.status_code == on.status_code == 200
    assert (off.json()["id"], off.json()["enabled"]) == (feed, False)
    assert on.json()["enabled"] is True
    assert alice.listing().json()["feeds"] == [on.json()]


def test_a_disabled_source_is_not_read_by_the_next_run(alice: SourcesSession) -> None:
    company = alice.company("acme")
    alice.patch("companies", company, enabled=False)
    reads: list[Any] = []

    alice.refresh(dict(registry([*Platform, *FeedSource], reads)))

    assert reads == []
    assert alice.listing().json()["companies"][0]["last_run"] is None


@pytest.mark.parametrize("body", [{}, {"enabled": "maybe"}])
def test_a_patch_without_a_boolean_is_refused(
    alice: SourcesSession, body: dict[str, object]
) -> None:
    company = alice.company("acme")

    response = alice.patch("companies", company, **body)

    assert status_and_code(response) == (422, "invalid_request")
    assert field_of(response) == "enabled"
    assert alice.listing().json()["companies"][0]["enabled"] is True


# --- видалити -------------------------------------------------------------------------------


def test_a_deleted_company_goes_with_its_run_state_but_its_jobs_stay(
    alice: SourcesSession, db: Db
) -> None:
    company = alice.company("acme")
    scripts = registry([*Platform, *FeedSource], [])
    scripts[Platform.GREENHOUSE].postings["acme"] = [
        posting("Backend Engineer"),
        posting("Data Engineer"),
    ]
    alice.refresh(scripts)
    assert db.count("source_company_runs") == 1

    response = alice.delete("companies", company)

    assert response.status_code == 204
    assert response.content == b""
    assert alice.listing().json()["companies"] == []
    assert db.count("source_company_runs") == 0
    assert alice.job_sources() == ["ats:greenhouse", "ats:greenhouse"]


def test_a_deleted_feed_goes_with_its_run_state_but_its_jobs_stay(
    alice: SourcesSession, db: Db
) -> None:
    feed = alice.feed("category=Python")
    scripts = registry([*Platform, *FeedSource], [])
    scripts[FeedSource.DOU].postings["category=Python"] = [
        posting("Backend Engineer", company="Globex")
    ]
    alice.refresh(scripts)
    assert db.count("source_feed_runs") == 1

    response = alice.delete("feeds", feed)

    assert response.status_code == 204
    assert alice.listing().json()["feeds"] == []
    assert db.count("source_feed_runs") == 0
    assert alice.job_sources() == ["rss:dou"]


def test_a_second_delete_is_not_found(alice: SourcesSession) -> None:
    company = alice.company("acme")
    alice.delete("companies", company)

    response = alice.delete("companies", company)

    assert status_and_code(response) == (404, "not_found")


# --- чуже й неіснуюче -----------------------------------------------------------------------


def test_another_users_sources_cannot_be_changed_and_look_missing(
    alice: SourcesSession, bob: SourcesSession
) -> None:
    company, feed = alice.company("acme"), alice.feed("category=Python")

    attempts = (
        bob.patch("companies", company, enabled=False),
        bob.patch("feeds", feed, enabled=False),
        bob.delete("companies", company),
        bob.delete("feeds", feed),
    )

    assert [status_and_code(r) for r in attempts] == [(404, "not_found")] * 4
    body = alice.listing().json()
    assert [(c["id"], c["enabled"]) for c in body["companies"]] == [(company, True)]
    assert [(f["id"], f["enabled"]) for f in body["feeds"]] == [(feed, True)]


def test_a_company_id_is_not_a_feed_id_and_vice_versa(alice: SourcesSession) -> None:
    company, feed = alice.company("acme"), alice.feed("category=Python")

    attempts = (
        alice.patch("feeds", company, enabled=False),
        alice.delete("feeds", company),
        alice.patch("companies", feed, enabled=False),
        alice.delete("companies", feed),
    )

    assert [status_and_code(r) for r in attempts] == [(404, "not_found")] * 4
    assert len(alice.listing().json()["companies"]) == 1
    assert len(alice.listing().json()["feeds"]) == 1


@pytest.mark.parametrize("source_id", [UNKNOWN_ID, "42", "not-a-uuid"])
@pytest.mark.parametrize("kind", ["companies", "feeds"])
def test_a_missing_or_malformed_id_is_not_found(
    alice: SourcesSession, kind: str, source_id: str
) -> None:
    patched = alice.patch(kind, source_id, enabled=False)
    deleted = alice.delete(kind, source_id)

    assert [status_and_code(r) for r in (patched, deleted)] == [(404, "not_found")] * 2


# --- збій посеред справжнього прогону -------------------------------------------------------


def test_a_source_deleted_during_a_run_does_not_break_the_run(
    alice: SourcesSession, db: Db
) -> None:
    alice.company("acme")
    alice.company("beta")
    scripts = registry([*Platform, *FeedSource], [])
    scripts[Platform.GREENHOUSE].postings["acme"] = [posting("Backend Engineer")]
    scripts[Platform.GREENHOUSE].postings["beta"] = [posting("Data Engineer")]

    async def delete_acme() -> None:
        db.execute("DELETE FROM source_companies WHERE slug = 'acme'")

    scripts[Platform.GREENHOUSE].during["acme"] = delete_acme

    report = alice.refresh(scripts)

    assert [run.subscription.ref for run in report.runs] == ["beta"]
    (beta,) = alice.listing().json()["companies"]
    assert (beta["slug"], beta["last_run"]["imported"]) == ("beta", 1)
    assert db.count("source_company_runs") == 1
    assert alice.job_sources() == ["ats:greenhouse"]


def test_a_crash_while_reading_is_stored_as_invalid_and_the_run_goes_on(
    alice: SourcesSession,
) -> None:
    alice.company("acme")
    alice.company("beta", platform="lever")
    scripts = registry([*Platform, *FeedSource], [])
    scripts[Platform.GREENHOUSE].crashes["acme"] = RuntimeError("розбір упав")
    scripts[Platform.LEVER].postings["beta"] = [posting("Data Engineer")]

    alice.refresh(scripts)

    rows = {c["slug"]: c["last_run"] for c in alice.listing().json()["companies"]}
    assert rows["acme"]["error"] == "invalid"
    assert (rows["acme"]["found"], rows["acme"]["imported"]) == (0, 0)
    assert (rows["beta"]["error"], rows["beta"]["imported"]) == (None, 1)
    assert alice.job_sources() == ["ats:lever"]
