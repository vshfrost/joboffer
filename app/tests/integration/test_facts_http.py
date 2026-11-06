"""Факти через HTTP наскрізь: сесія й CSRF, 422 за полями, 404 для чужих, ізоляція користувачів."""

from datetime import datetime

import httpx2
import pytest
from anyio.from_thread import BlockingPortal
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from application.contracts.actor import Actor, Channel, Scope
from application.contracts.facts import FactInput
from bootstrap.api import container_of
from domain.identity.ids import UserId
from tests.integration.test_profile_http import ClientFactory, Session, make_client

__all__ = ["make_client"]

PYTHON = {"kind": "skill", "text": "Python"}
LEAD = {"kind": "experience", "text": "Backend Lead at Acme, 2021–2024"}
LATENCY = {"kind": "achievement", "text": "Cut p95 latency by 40%"}


class FactsSession:
    def __init__(
        self, session: Session, portal: BlockingPortal, engine: AsyncEngine, email: str
    ) -> None:
        self.client = session.client
        self.csrf = session.csrf
        self._portal = portal
        self._engine = engine
        self._email = email

    def _actor(self) -> Actor:
        async def user_id() -> UserId:
            async with self._engine.connect() as conn:
                row = await conn.execute(
                    text("SELECT id FROM users WHERE email = :email"),
                    {"email": self._email},
                )
                return UserId(row.scalar_one())

        return Actor(
            user_id=self._portal.call(user_id),
            channel=Channel.WEB,
            client_id="web",
            grant_id=None,
            scopes=frozenset(Scope),
            correlation_id="test",
        )

    def seed(self, *items: dict[str, str]) -> None:
        """Факти додає лише MCP — тут через use case, як це робить тул."""
        facts = container_of(self.client.app).facts  # type: ignore[arg-type]
        self._portal.call(
            facts.save_facts,
            self._actor(),
            [FactInput(kind=i["kind"], text=i["text"]) for i in items],
        )

    def seed_cv(self, cv: str, file_name: str = "") -> None:
        facts = container_of(self.client.app).facts  # type: ignore[arg-type]
        self._portal.call(facts.save_original_cv, self._actor(), cv, file_name)

    def library(self) -> httpx2.Response:
        return self.client.get("/facts")

    def cv(self) -> httpx2.Response:
        return self.client.get("/facts/original-cv")

    def confirm(self, fact_ids: list[int]) -> httpx2.Response:
        return self.client.post(
            "/facts/confirm", json={"fact_ids": fact_ids}, headers=self.csrf
        )

    def create(self, **body: object) -> httpx2.Response:
        return self.client.post("/facts", json=body, headers=self.csrf)

    def update(self, fact_id: object, **body: object) -> httpx2.Response:
        return self.client.put(f"/facts/{fact_id}", json=body, headers=self.csrf)

    def delete(self, fact_id: object) -> httpx2.Response:
        return self.client.delete(f"/facts/{fact_id}", headers=self.csrf)

    def numbers(self) -> list[int]:
        return [item["fact_id"] for item in self.library().json()["facts"]]

    def confirmed(self) -> dict[int, bool]:
        return {i["fact_id"]: i["confirmed"] for i in self.library().json()["facts"]}


@pytest.fixture
def alice(
    make_client: ClientFactory, portal: BlockingPortal, engine: AsyncEngine
) -> FactsSession:
    email = "alice@example.com"
    return FactsSession(Session(make_client(), email), portal, engine, email)


@pytest.fixture
def bob(
    make_client: ClientFactory, portal: BlockingPortal, engine: AsyncEngine
) -> FactsSession:
    email = "bob@example.com"
    return FactsSession(Session(make_client(), email), portal, engine, email)


def test_every_route_requires_a_session(make_client: ClientFactory) -> None:
    client = make_client()
    for method, path in (
        ("GET", "/facts"),
        ("GET", "/facts/original-cv"),
        ("POST", "/facts/confirm"),
        ("PUT", "/facts/1"),
        ("DELETE", "/facts/1"),
    ):
        response = client.request(method, path)
        assert (response.status_code, response.json()["code"]) == (
            401,
            "not_authenticated",
        ), (method, path)


def test_unsafe_requests_require_the_csrf_token(alice: FactsSession) -> None:
    alice.seed(PYTHON)
    for method, path, body in (
        ("POST", "/facts/confirm", {"fact_ids": [1]}),
        ("PUT", "/facts/1", LEAD),
        ("DELETE", "/facts/1", None),
    ):
        response = alice.client.request(method, path, json=body)
        assert (response.status_code, response.json()["code"]) == (403, "csrf_failed")
    assert alice.confirmed() == {1: False}
    assert alice.library().json()["facts"][0]["text"] == "Python"


def test_a_new_user_has_an_empty_library_with_zero_counts(alice: FactsSession) -> None:
    response = alice.library()
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["facts"] == []
    assert body["counts"]["total"] == 0
    assert [k["kind"] for k in body["counts"]["kinds"]] == [
        "experience",
        "achievement",
        "project",
        "skill",
        "education",
        "language",
    ]


def test_the_library_returns_facts_in_section_order_with_their_fields(
    alice: FactsSession,
) -> None:
    alice.seed(PYTHON, LATENCY, LEAD)
    facts = alice.library().json()["facts"]
    assert [f["fact_id"] for f in facts] == [3, 2, 1]
    first = facts[0]
    created_at = datetime.fromisoformat(first.pop("created_at"))
    assert datetime.fromisoformat(first.pop("updated_at")) == created_at
    assert first == {
        "fact_id": 3,
        "kind": "experience",
        "text": LEAD["text"],
        "confirmed": False,
        "source": "cv",
        "job_id": None,
    }


def test_the_counts_are_exact_by_kind_and_status_in_one_request(
    alice: FactsSession,
) -> None:
    alice.seed(PYTHON, LATENCY, LEAD, {"kind": "skill", "text": "Go"})
    alice.confirm([1, 3])
    counts = alice.library().json()["counts"]
    by_kind = {
        k["kind"]: (k["total"], k["confirmed"], k["unconfirmed"])
        for k in counts["kinds"]
    }
    assert (counts["total"], counts["confirmed"], counts["unconfirmed"]) == (4, 2, 2)
    assert by_kind == {
        "experience": (1, 1, 0),
        "achievement": (1, 0, 1),
        "project": (0, 0, 0),
        "skill": (2, 1, 1),
        "education": (0, 0, 0),
        "language": (0, 0, 0),
    }


def test_the_numbers_of_users_are_independent(
    alice: FactsSession, bob: FactsSession
) -> None:
    alice.seed(PYTHON, LEAD)
    bob.seed(PYTHON)
    assert alice.numbers() == [2, 1]
    assert bob.numbers() == [1]


def test_confirming_marks_only_the_chosen_facts_and_returns_them(
    alice: FactsSession,
) -> None:
    alice.seed(PYTHON, LEAD, LATENCY)
    response = alice.confirm([3, 1, 3])
    assert response.status_code == 200
    assert [(f["fact_id"], f["confirmed"]) for f in response.json()["facts"]] == [
        (1, True),
        (3, True),
    ]
    assert alice.confirmed() == {2: False, 3: True, 1: True}


def test_confirming_without_ids_is_422_and_changes_nothing(alice: FactsSession) -> None:
    alice.seed(PYTHON)
    response = alice.confirm([])
    assert (response.status_code, response.json()["code"]) == (422, "invalid_value")
    assert response.json()["message"] == "Не вибрано жодного факту."
    assert response.json()["field_errors"] == [
        {"field": "fact_ids", "message": "Не вибрано жодного факту."}
    ]
    assert alice.confirmed() == {1: False}


def test_confirming_with_an_unknown_or_foreign_id_is_404_and_changes_nothing(
    alice: FactsSession, bob: FactsSession
) -> None:
    alice.seed(PYTHON)
    bob.seed(LEAD, LATENCY)
    for ids in ([1, 99], [1, 2]):
        response = alice.confirm(ids)
        assert (response.status_code, response.json()["code"]) == (404, "not_found")
    assert alice.confirmed() == {1: False}
    assert bob.confirmed() == {1: False, 2: False}


def test_updating_changes_kind_and_text_and_drops_the_confirmation(
    alice: FactsSession,
) -> None:
    alice.seed(PYTHON)
    alice.confirm([1])
    response = alice.update(1, kind="project", text="  Migration to\n Python 3.14 ")
    assert response.status_code == 200
    body = response.json()
    assert (body["fact_id"], body["kind"], body["text"], body["confirmed"]) == (
        1,
        "project",
        "Migration to Python 3.14",
        False,
    )
    assert alice.confirmed() == {1: False}
    counts = alice.library().json()["counts"]
    assert counts["kinds"][2] == {
        "kind": "project",
        "total": 1,
        "confirmed": 0,
        "unconfirmed": 1,
    }


def test_updating_to_the_text_of_another_fact_is_409_naming_it(
    alice: FactsSession,
) -> None:
    alice.seed(PYTHON, LEAD)
    response = alice.update(2, **PYTHON)
    assert (response.status_code, response.json()["code"]) == (409, "duplicate_fact")
    assert response.json()["message"] == "Такий факт уже є: #1."


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (
            {"kind": "hobby", "text": "Chess"},
            [("kind", "Невідомий вид факту: 'hobby'.")],
        ),
        ({"kind": "skill", "text": "  "}, [("text", "Факт не може бути порожнім.")]),
        (
            {"kind": "skill", "text": "x" * 501},
            [("text", "Факт задовгий: більше 500 символів — розбий на кілька.")],
        ),
    ],
)
def test_an_invalid_update_is_422_with_the_v1_text_and_changes_nothing(
    alice: FactsSession, body: dict[str, str], expected: list[tuple[str, str]]
) -> None:
    alice.seed(PYTHON)
    alice.confirm([1])
    response = alice.update(1, **body)
    assert response.status_code == 422
    assert [
        (e["field"], e["message"]) for e in response.json()["field_errors"]
    ] == expected
    assert alice.confirmed() == {1: True}


def test_an_unexpected_body_field_is_422(alice: FactsSession) -> None:
    alice.seed(PYTHON)
    response = alice.update(1, kind="skill", text="Go", confirmed=True)
    assert response.status_code == 422
    assert alice.confirmed() == {1: False}


def test_updating_or_deleting_an_unknown_or_foreign_fact_is_404(
    alice: FactsSession, bob: FactsSession
) -> None:
    alice.seed(PYTHON)
    bob.seed(LEAD, LATENCY)
    for number in (2, 99, 0, 2**40):
        assert alice.update(number, **PYTHON).status_code == 404
        assert alice.delete(number).status_code == 404
    assert alice.numbers() == [1]
    assert bob.numbers() == [1, 2]


def test_a_non_numeric_fact_id_is_422(alice: FactsSession) -> None:
    assert alice.update("abc", **PYTHON).status_code == 422
    assert alice.delete("abc").status_code == 422


def test_deleting_removes_the_fact_for_good_and_the_number_is_not_reused(
    alice: FactsSession,
) -> None:
    alice.seed(PYTHON, LEAD)
    response = alice.delete(2)
    assert (response.status_code, response.content) == (204, b"")
    assert alice.numbers() == [1]
    assert alice.delete(2).status_code == 404
    alice.seed(LATENCY)
    assert alice.numbers() == [3, 1]
    assert alice.library().json()["counts"]["total"] == 2


def test_the_original_cv_is_returned_with_name_text_and_day(
    alice: FactsSession,
) -> None:
    alice.seed_cv("Taras Prykladenko\nSenior Backend", "cv.pdf")
    response = alice.cv()
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    saved_at = body.pop("saved_at")
    assert saved_at.endswith(("Z", "+00:00"))
    assert body == {"file_name": "cv.pdf", "text": "Taras Prykladenko\nSenior Backend"}


def test_a_new_original_cv_replaces_the_old_one_and_keeps_the_facts(
    alice: FactsSession,
) -> None:
    alice.seed(PYTHON)
    alice.seed_cv("old", "old.pdf")
    alice.seed_cv("new")
    body = alice.cv().json()
    assert (body["text"], body["file_name"]) == ("new", None)
    assert alice.numbers() == [1]


def test_without_an_original_cv_it_is_404(alice: FactsSession) -> None:
    response = alice.cv()
    assert (response.status_code, response.json()["code"]) == (404, "not_found")


def test_the_original_cv_of_a_user_is_not_visible_to_another(
    alice: FactsSession, bob: FactsSession
) -> None:
    alice.seed_cv("secret")
    assert bob.cv().status_code == 404


def test_a_valid_fact_is_created_201_as_a_confirmed_manual_fact(
    alice: FactsSession,
) -> None:
    response = alice.create(**PYTHON)
    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body.pop("created_at") == body.pop("updated_at")
    assert body == {
        "fact_id": 1,
        "kind": "skill",
        "text": "Python",
        "confirmed": True,
        "source": "manual",
        "job_id": None,
    }
    assert alice.confirmed() == {1: True}


def test_creating_a_fact_with_a_known_text_is_409_naming_it(
    alice: FactsSession,
) -> None:
    alice.seed(PYTHON)
    response = alice.create(kind="experience", text="  PYTHON ")
    assert (response.status_code, response.json()["code"]) == (409, "duplicate_fact")
    assert response.json()["message"] == "Такий факт уже є: #1."
    assert alice.numbers() == [1]


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (
            {"kind": "hobby", "text": "Chess"},
            [("kind", "Невідомий вид факту: 'hobby'.")],
        ),
        ({"kind": "skill", "text": "  "}, [("text", "Факт не може бути порожнім.")]),
        (
            {"kind": "skill", "text": "x" * 501},
            [("text", "Факт задовгий: більше 500 символів — розбий на кілька.")],
        ),
    ],
)
def test_an_invalid_new_fact_is_422_at_the_field_and_nothing_is_saved(
    alice: FactsSession, body: dict[str, str], expected: list[tuple[str, str]]
) -> None:
    response = alice.create(**body)
    assert response.status_code == 422
    assert [
        (e["field"], e["message"]) for e in response.json()["field_errors"]
    ] == expected
    assert alice.numbers() == []


def test_creating_a_fact_requires_a_session(make_client: ClientFactory) -> None:
    response = make_client().post("/facts", json=PYTHON)
    assert (response.status_code, response.json()["code"]) == (
        401,
        "not_authenticated",
    )


def test_creating_a_fact_requires_the_csrf_token(alice: FactsSession) -> None:
    response = alice.client.post("/facts", json=PYTHON)
    assert (response.status_code, response.json()["code"]) == (403, "csrf_failed")
    assert alice.numbers() == []


def test_the_source_of_a_new_fact_cannot_be_chosen_in_the_body(
    alice: FactsSession,
) -> None:
    response = alice.create(source="cv", **PYTHON)
    assert response.status_code == 422
    assert alice.numbers() == []


def test_there_are_no_endpoints_to_save_the_cv(
    alice: FactsSession,
) -> None:
    for method, path in (
        ("PUT", "/facts/original-cv"),
        ("POST", "/facts/original-cv"),
    ):
        response = alice.client.request(
            method, path, json={"kind": "skill", "text": "x"}, headers=alice.csrf
        )
        assert response.status_code in (404, 405, 422), (method, path)
    assert alice.numbers() == []
