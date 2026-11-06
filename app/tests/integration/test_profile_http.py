"""Профіль через HTTP наскрізь: сесія й CSRF, розділи окремо, 422 за полями, ізоляція користувачів."""

from collections.abc import Callable, Iterator
from copy import deepcopy
from typing import Any

import httpx2
import pytest
from anyio.from_thread import BlockingPortal
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from application.contracts.identity import CreateUser
from bootstrap.api import container_of, create_app
from bootstrap.settings import Settings
from infrastructure.http.auth import CSRF_HEADER

PASSWORD = "correct horse battery"

EMPTY: dict[str, Any] = {
    "target": {
        "roles": [],
        "seniority": [],
        "min_salary_eur": None,
        "target_domains": [],
    },
    "locations": {
        "work_modes": [],
        "locations": [],
        "include_unknown_mode": True,
        "relocation": False,
    },
    "rules": {"title_keywords": [], "title_exclude": [], "stop_words": []},
    "contacts": {
        "full_name": "",
        "email": "",
        "phone": "",
        "linkedin_url": "",
        "city": "",
        "github_url": "",
        "work_authorization": "",
    },
}

SECTIONS: dict[str, dict[str, Any]] = {
    "target": {
        "roles": ["Backend Engineer", "SRE"],
        "seniority": ["senior", "lead"],
        "min_salary_eur": 70000,
        "target_domains": ["fintech"],
    },
    "locations": {
        "work_modes": ["remote", "hybrid"],
        "locations": [
            {"place": "Valencia", "aliases": ["Валенсія"], "work_modes": ["hybrid"]},
            {"place": "Madrid", "aliases": [], "work_modes": ["remote", "onsite"]},
        ],
        "include_unknown_mode": False,
        "relocation": True,
    },
    "rules": {
        "title_keywords": ["backend"],
        "title_exclude": ["junior", "intern"],
        "stop_words": ["crypto"],
    },
    "contacts": {
        "full_name": "Taras Prykladenko",
        "email": "taras@example.com",
        "phone": "+34 600 000 000",
        "linkedin_url": "https://linkedin.com/in/taras",
        "city": "Valencia, Spain",
        "github_url": "https://github.com/taras",
        "work_authorization": "Spain / EU work authorization",
    },
}

CHANGED: dict[str, dict[str, Any]] = {
    "target": {
        "roles": ["QA"],
        "seniority": [],
        "min_salary_eur": None,
        "target_domains": [],
    },
    "locations": {
        "work_modes": [],
        "locations": [{"place": "Cádiz", "aliases": [], "work_modes": ["onsite"]}],
        "include_unknown_mode": True,
        "relocation": False,
    },
    "rules": {"title_keywords": [], "title_exclude": [], "stop_words": ["gambling"]},
    "contacts": {**SECTIONS["contacts"], "city": "Madrid"},
}

type ClientFactory = Callable[[], TestClient]


@pytest.fixture
def make_client(
    portal: BlockingPortal, engine: AsyncEngine, database_url: str
) -> Iterator[ClientFactory]:
    async def clean() -> None:
        async with engine.begin() as conn:
            await conn.execute(text("TRUNCATE users CASCADE"))
            await conn.execute(text("TRUNCATE login_failures"))

    portal.call(clean)
    opened: list[TestClient] = []

    def factory() -> TestClient:
        app = create_app(Settings(environment="test", database_url=database_url))
        client = TestClient(app, base_url="https://testserver")
        client.__enter__()
        opened.append(client)
        return client

    yield factory
    for client in opened:
        client.__exit__(None, None, None)


class Session:
    """Користувач, що увійшов: клієнт із cookie й CSRF-заголовком для небезпечних методів."""

    def __init__(self, client: TestClient, email: str) -> None:
        identity = container_of(client.app).identity  # type: ignore[arg-type]
        assert client.portal is not None
        client.portal.call(
            identity.create_user,
            CreateUser(email=email, display_name="Користувач", password=PASSWORD),
        )
        login = client.post("/auth/login", json={"email": email, "password": PASSWORD})
        self.client = client
        self.csrf = {CSRF_HEADER: str(login.json()["csrf_token"])}

    def get(self) -> httpx2.Response:
        return self.client.get("/profile")

    def put(self, section: str, body: object) -> httpx2.Response:
        return self.client.put(f"/profile/{section}", json=body, headers=self.csrf)


@pytest.fixture
def alice(make_client: ClientFactory) -> Session:
    return Session(make_client(), "alice@example.com")


@pytest.fixture
def bob(make_client: ClientFactory) -> Session:
    return Session(make_client(), "bob@example.com")


def fill(session: Session) -> None:
    for section, body in SECTIONS.items():
        assert session.put(section, body).status_code == 200


def test_the_profile_requires_a_session(make_client: ClientFactory) -> None:
    client = make_client()
    response = client.get("/profile")
    assert (response.status_code, response.json()["code"]) == (401, "not_authenticated")
    response = client.put("/profile/target", json=SECTIONS["target"])
    assert response.status_code == 401


@pytest.mark.parametrize("section", list(SECTIONS))
def test_saving_a_section_requires_the_csrf_token(alice: Session, section: str) -> None:
    response = alice.client.put(f"/profile/{section}", json=SECTIONS[section])
    assert (response.status_code, response.json()["code"]) == (403, "csrf_failed")
    assert alice.get().json() == EMPTY


def test_a_new_user_gets_an_empty_profile_and_no_row_is_created(
    alice: Session, portal: BlockingPortal, engine: AsyncEngine
) -> None:
    response = alice.get()
    assert response.status_code == 200
    assert response.json() == EMPTY
    assert response.headers["cache-control"] == "no-store"

    async def rows() -> object:
        async with engine.connect() as conn:
            return (await conn.execute(text("SELECT count(*) FROM profiles"))).scalar()

    assert portal.call(rows) == 0


@pytest.mark.parametrize("section", list(SECTIONS))
def test_a_section_saves_alone_and_returns_the_whole_profile(
    alice: Session, section: str
) -> None:
    response = alice.put(section, SECTIONS[section])
    assert response.status_code == 200
    assert response.json() == {**EMPTY, section: SECTIONS[section]}
    assert alice.get().json() == {**EMPTY, section: SECTIONS[section]}


@pytest.mark.parametrize("section", list(SECTIONS))
def test_saving_a_section_leaves_the_others_as_they_were(
    alice: Session, section: str
) -> None:
    fill(alice)
    response = alice.put(section, CHANGED[section])
    expected = deepcopy(SECTIONS) | {section: CHANGED[section]}
    assert response.json() == expected
    assert alice.get().json() == expected


def test_locations_come_back_in_the_order_they_were_saved(alice: Session) -> None:
    places = ["Madrid", "Barcelona", "Valencia", "Alicante"]
    body = {
        **SECTIONS["locations"],
        "locations": [
            {"place": place, "aliases": [], "work_modes": ["remote"]}
            for place in places
        ],
    }
    alice.put("locations", body)
    saved = alice.get().json()["locations"]["locations"]
    assert [location["place"] for location in saved] == places


def test_values_are_normalized_on_save(alice: Session) -> None:
    body = {
        **SECTIONS["target"],
        "roles": ["  SRE ", "sre", ""],
        "seniority": ["lead", "junior"],
    }
    saved = alice.put("target", body).json()["target"]
    assert saved["roles"] == ["SRE"]
    assert saved["seniority"] == ["junior", "lead"]


def field_errors(response: httpx2.Response) -> list[tuple[str, str]]:
    return [
        (item["field"], item["message"]) for item in response.json()["field_errors"]
    ]


def test_a_negative_salary_is_422_with_the_v1_text(alice: Session) -> None:
    response = alice.put("target", {**SECTIONS["target"], "min_salary_eur": -1})
    assert (response.status_code, response.json()["code"]) == (422, "invalid_fields")
    assert field_errors(response) == [
        ("min_salary_eur", "Мінімальна зарплата не може бути від'ємною.")
    ]


def test_an_unknown_seniority_is_422(alice: Session) -> None:
    response = alice.put("target", {**SECTIONS["target"], "seniority": ["wizard"]})
    assert response.status_code == 422
    assert field_errors(response) == [("seniority", "Невідомий рівень.")]


def test_a_place_repeated_in_another_case_is_422_at_the_second_row(
    alice: Session,
) -> None:
    rows = [
        {"place": "Valencia", "aliases": [], "work_modes": ["remote"]},
        {"place": "VALENCIA", "aliases": [], "work_modes": ["remote"]},
    ]
    response = alice.put("locations", {**SECTIONS["locations"], "locations": rows})
    assert response.status_code == 422
    assert field_errors(response) == [
        ("locations.1.place", "Місця в локаціях пошуку не мають повторюватись.")
    ]


def test_a_location_without_a_format_is_422_at_its_row(alice: Session) -> None:
    rows = [
        {"place": "Madrid", "aliases": [], "work_modes": ["remote"]},
        {"place": "Valencia", "aliases": [], "work_modes": []},
    ]
    response = alice.put("locations", {**SECTIONS["locations"], "locations": rows})
    assert response.status_code == 422
    assert field_errors(response) == [
        (
            "locations.1.work_modes",
            "Для місця «Valencia» обери хоч один формат: remote, hybrid чи onsite.",
        )
    ]


def test_fifty_one_locations_are_422(alice: Session) -> None:
    rows = [
        {"place": f"Place {number}", "aliases": [], "work_modes": ["remote"]}
        for number in range(51)
    ]
    response = alice.put("locations", {**SECTIONS["locations"], "locations": rows})
    assert response.status_code == 422
    assert field_errors(response) == [("locations", "Локацій пошуку — до 50.")]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("linkedin_url", "linkedin.com/in/taras", "LinkedIn — посилання з https://."),
        ("github_url", "http://github.com/taras", "GitHub — посилання з https://."),
        ("email", "not-an-email", "Email виглядає некоректно, напр. name@example.com."),
        ("city", "c" * 201, "city — до 200 символів."),
    ],
)
def test_invalid_contacts_are_422_at_their_field(
    alice: Session, field: str, value: str, message: str
) -> None:
    response = alice.put("contacts", {**SECTIONS["contacts"], field: value})
    assert response.status_code == 422
    assert field_errors(response) == [(field, message)]


def test_every_problem_is_reported_at_once(alice: Session) -> None:
    body = {**SECTIONS["contacts"], "email": "x", "linkedin_url": "y"}
    response = alice.put("contacts", body)
    assert [field for field, _ in field_errors(response)] == ["email", "linkedin_url"]


def test_a_rejected_save_changes_nothing(alice: Session) -> None:
    fill(alice)
    alice.put("contacts", {**CHANGED["contacts"], "email": "x"})
    assert alice.get().json() == SECTIONS


@pytest.mark.parametrize(
    "body",
    [
        {**SECTIONS["rules"], "title_keywords": "backend"},
        {"title_keywords": [], "title_exclude": []},
        {**SECTIONS["rules"], "surprise": 1},
    ],
)
def test_a_malformed_body_is_422_invalid_request(alice: Session, body: object) -> None:
    response = alice.put("rules", body)
    assert (response.status_code, response.json()["code"]) == (422, "invalid_request")


def test_an_unknown_section_is_404(alice: Session) -> None:
    assert alice.put("photos", {}).status_code == 404


def test_a_profile_is_invisible_to_another_user(alice: Session, bob: Session) -> None:
    fill(alice)
    assert bob.get().json() == EMPTY


def test_saving_for_one_user_does_not_touch_another(
    alice: Session, bob: Session
) -> None:
    fill(alice)
    bob.put("rules", CHANGED["rules"])
    assert alice.get().json() == SECTIONS
    assert bob.get().json() == {**EMPTY, "rules": CHANGED["rules"]}
