"""Підготовка через HTTP наскрізь: сесія й CSRF, реєстр тем із квізом, сторінка теми, «виконано» з
нотаткою (422 біля note, повтор лишає першу дату), «готово», підготовка до вакансії і пакет до
інтерв'ю, 404 для чужого й неіснуючого, ключ оцінки питань не віддається ніде.

Теми, плани, питання й пакети в житті створює лише Claude через MCP — тут вони сідають напряму через
use cases застосунку, на справжньому Postgres."""

import re
from collections.abc import Awaitable, Callable
from datetime import datetime
from functools import partial
from typing import Any

import httpx2
import pytest
from sqlalchemy import text

from application.contracts.actor import Actor, Channel, Scope
from application.contracts.analysis import AnalysisInput
from application.contracts.facts import FactInput
from application.contracts.kit import KitInput, KitQuestionInput, StoryInput
from application.contracts.prep import ResourceInput, StepInput, TopicInput
from application.contracts.quiz import AnswerInput, QuestionInput
from bootstrap.api import container_of
from domain.identity.ids import UserId
from domain.shared.local_time import local_day
from tests.integration.test_jobs_http import JobsSession, make_client
from tests.integration.test_profile_http import ClientFactory, Session

__all__ = ["make_client"]

SECRET = "SECRET-KEY-POINT"
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z")
BAD_NOTE = "Нотатка — до 2000 символів."


class PrepSession:
    """Користувач, що увійшов, і засіб посадити йому теми, плани, питання й пакети (як це робить Claude)."""

    def __init__(self, make: ClientFactory, email: str) -> None:
        session = Session(make(), email)
        self.jobs = JobsSession(session)
        self.client = session.client
        self.csrf = session.csrf
        self.container = container_of(self.client.app)  # type: ignore[arg-type]
        self.actor = Actor(
            user_id=self.call(self.user_id, email),
            channel=Channel.CLI,
            client_id="test",
            grant_id=None,
            scopes=frozenset(Scope),
            correlation_id="test",
        )

    def call[T](self, function: Callable[..., Awaitable[T]], *args: object) -> T:
        assert self.client.portal is not None
        return self.client.portal.call(partial(function, *args))

    async def user_id(self, email: str) -> UserId:
        async with self.container.engine.connect() as conn:
            row = await conn.execute(
                text("SELECT id FROM users WHERE email = :email"), {"email": email}
            )
            return UserId(row.scalar_one())

    # --- посів -----------------------------------------------------------------------------

    def job(self, title: str, company: str, score: int, *gaps: str) -> int:
        added = self.jobs.add(
            text=f"{title} at {company}", title=title, company=company
        )
        number = int(added.json()["job_id"])
        analysis = AnalysisInput(score=score, summary="Підсумок.", gaps=gaps)
        self.call(self.container.analysis.save_analysis, self.actor, number, analysis)
        return number

    def topic(
        self, job: int, slug: str, gap: str, kind: str = "tech", deadline: str = ""
    ) -> int:
        item = TopicInput(
            slug=slug,
            title=f"Тема {slug}",
            kind=kind,
            gap=gap,
            summary=f"Про {slug}.",
            deadline=deadline,
        )
        saved = self.call(self.container.prep.save_prep_topics, self.actor, job, [item])
        return saved[0].topic_number

    def plan(
        self, topic: int, *, details: str = "", note_resource: bool = False
    ) -> None:
        resources = (
            [ResourceInput(title="Доки", url="https://example.com/docs")]
            if note_resource
            else []
        )
        steps = [
            StepInput(
                kind="learn",
                title="Прочитати",
                minutes=60,
                details=details,
                resources=resources,
            ),
            StepInput(kind="practice", title="Написати", minutes=120),
            StepInput(kind="check", title="Відповісти", minutes=30),
        ]
        self.call(self.container.prep.save_topic_plan, self.actor, topic, steps)

    def questions(self, topic: int, *questions: str) -> None:
        items = [QuestionInput(question=q, answer_points=[SECRET]) for q in questions]
        self.call(self.container.quiz.save_questions, self.actor, topic, items)

    def answer(self, question: int, grade: int) -> None:
        data = AnswerInput(grade=grade, answer="Моя відповідь.", feedback=SECRET)
        self.call(self.container.quiz.record_answer, self.actor, question, data)

    def kit(self, job: int, tag: str = "", topic: int | None = None) -> None:
        saved = self.call(
            self.container.facts.save_facts,
            self.actor,
            [FactInput(kind="skill", text=f"Python {tag}")],
        )
        fact = saved.added[0].fact_number
        self.call(self.container.facts.confirm_facts, self.actor, [fact])
        data = KitInput(
            questions=[
                KitQuestionInput(
                    kind="technical" if n % 2 else "behavioral",
                    question=f"{tag}Question {n}?",
                    topic_number=topic if n == 1 else None,
                )
                for n in range(1, 6)
            ],
            stories=[
                StoryInput(
                    title=f"{tag}Story {n}",
                    situation=f"Situation {n}",
                    task=f"Task {n}",
                    action=f"Action {n}",
                    result=f"Result {n}",
                    fact_ids=[fact],
                )
                for n in range(1, 4)
            ],
            company_questions=[f"{tag}Ask {n}?" for n in range(1, 4)],
        )
        self.call(
            self.container.interview_kits.save_interview_kit, self.actor, job, data
        )

    # --- запити ----------------------------------------------------------------------------

    def board(self) -> httpx2.Response:
        return self.client.get("/prep/topics")

    def page(self, topic: object) -> httpx2.Response:
        return self.client.get(f"/prep/topics/{topic}")

    def done(self, step: object, **body: object) -> httpx2.Response:
        return self.client.post(
            f"/prep/steps/{step}/done", json=body, headers=self.csrf
        )

    def ready(self, topic: object, **body: object) -> httpx2.Response:
        return self.client.put(
            f"/prep/topics/{topic}/ready", json=body, headers=self.csrf
        )

    def job_prep(self, job: object) -> httpx2.Response:
        return self.client.get(f"/jobs/{job}/prep")

    def interview_kit(self, job: object) -> httpx2.Response:
        return self.client.get(f"/jobs/{job}/interview-kit")


@pytest.fixture
def alice(make_client: ClientFactory) -> PrepSession:
    return PrepSession(make_client, "alice@example.com")


@pytest.fixture
def bob(make_client: ClientFactory) -> PrepSession:
    return PrepSession(make_client, "bob@example.com")


@pytest.fixture
def prepared(alice: PrepSession) -> PrepSession:
    """Дві вакансії; mysql — з обох (140), kafka — з першої (80); mysql з планом із трьох кроків."""
    alice.job("Backend", "Acme", 80, "MySQL", "Kafka")
    alice.job("Platform", "Zeta", 60, "InnoDB")
    alice.topic(1, "mysql", "MySQL", deadline="2026-12-01")
    alice.topic(2, "mysql", "InnoDB", deadline="2026-12-01")
    alice.topic(1, "kafka", "Kafka", kind="behavioral")
    alice.plan(1, details="Розділ про індекси.", note_resource=True)
    return alice


def field_errors(response: httpx2.Response) -> list[tuple[str, str]]:
    return [
        (item["field"], item["message"]) for item in response.json()["field_errors"]
    ]


def ok(response: httpx2.Response) -> Any:
    """Тіло успішної відповіді."""
    assert response.status_code == 200, response.text
    return response.json()


def without(body: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {key: value for key, value in body.items() if key not in keys}


# --- сесія, CSRF, 404 ------------------------------------------------------------------------


def test_every_route_requires_a_session(make_client: ClientFactory) -> None:
    client = make_client()
    for method, path in (
        ("GET", "/prep/topics"),
        ("GET", "/prep/topics/1"),
        ("POST", "/prep/steps/1/done"),
        ("PUT", "/prep/topics/1/ready"),
        ("GET", "/jobs/1/prep"),
        ("GET", "/jobs/1/interview-kit"),
    ):
        response = client.request(method, path)
        assert (response.status_code, response.json()["code"]) == (
            401,
            "not_authenticated",
        ), (method, path)


def test_done_and_ready_require_the_csrf_token(prepared: PrepSession) -> None:
    done = prepared.client.post("/prep/steps/1/done", json={"note": "x"})
    ready = prepared.client.put("/prep/topics/1/ready", json={"ready": True})
    for response in (done, ready):
        assert (response.status_code, response.json()["code"]) == (403, "csrf_failed")
    page = ok(prepared.page(1))
    assert page["status"] == "planned"
    assert page["steps"][0]["done_at"] is None


@pytest.mark.parametrize("number", [99, 0, -1, 10**30])
def test_a_missing_topic_step_or_job_is_404(prepared: PrepSession, number: int) -> None:
    for response in (
        prepared.page(number),
        prepared.done(number, note=""),
        prepared.ready(number, ready=True),
        prepared.job_prep(number),
        prepared.interview_kit(number),
    ):
        assert (response.status_code, response.json()["code"]) == (404, "not_found")


def test_a_number_that_is_not_an_integer_is_422(prepared: PrepSession) -> None:
    for response in (
        prepared.page("abc"),
        prepared.done("abc", note=""),
        prepared.ready("abc", ready=True),
        prepared.job_prep("abc"),
        prepared.interview_kit("abc"),
    ):
        assert response.status_code == 422
        assert response.json()["code"] == "invalid_request"


def test_another_users_topics_steps_and_jobs_are_404(
    prepared: PrepSession, bob: PrepSession
) -> None:
    for response in (
        bob.page(1),
        bob.done(1, note="hijack"),
        bob.ready(1, ready=True),
        bob.job_prep(1),
        bob.interview_kit(1),
    ):
        assert response.status_code == 404
    page = ok(prepared.page(1))
    assert (page["status"], page["steps"][0]["done_at"]) == ("planned", None)


def test_a_new_user_has_an_empty_registry(alice: PrepSession) -> None:
    response = alice.board()
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"topics": [], "quiz": {"total": 0, "due": 0}}


def test_the_registry_does_not_show_another_users_topics(
    prepared: PrepSession, bob: PrepSession
) -> None:
    assert ok(bob.board())["topics"] == []
    assert len(ok(prepared.board())["topics"]) == 2


# --- реєстр ----------------------------------------------------------------------------------


def test_the_registry_lists_topics_by_priority_with_every_field(
    prepared: PrepSession,
) -> None:
    prepared.questions(1, "What is an index?", "What is a join?", "What is a view?")
    prepared.questions(2, "What is a topic?")
    prepared.answer(1, 5)

    response = prepared.board()

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "topics": [
            {
                "topic_id": 1,
                "slug": "mysql",
                "title": "Тема mysql",
                "kind": "tech",
                "summary": "Про mysql.",
                "status": "planned",
                "percent": 0,
                "steps_done": 0,
                "steps_total": 3,
                "minutes_left": 210,
                "deadline": "2026-12-01",
                "priority": 140,
                "jobs": [
                    {
                        "job_id": 1,
                        "title": "Backend",
                        "company": "Acme",
                        "score": 80,
                        "gap": "MySQL",
                    },
                    {
                        "job_id": 2,
                        "title": "Platform",
                        "company": "Zeta",
                        "score": 60,
                        "gap": "InnoDB",
                    },
                ],
                "quiz": {"total": 3, "due": 2},
            },
            {
                "topic_id": 2,
                "slug": "kafka",
                "title": "Тема kafka",
                "kind": "behavioral",
                "summary": "Про kafka.",
                "status": "new",
                "percent": 0,
                "steps_done": 0,
                "steps_total": 0,
                "minutes_left": 0,
                "deadline": None,
                "priority": 80,
                "jobs": [
                    {
                        "job_id": 1,
                        "title": "Backend",
                        "company": "Acme",
                        "score": 80,
                        "gap": "Kafka",
                    }
                ],
                "quiz": {"total": 1, "due": 1},
            },
        ],
        "quiz": {"total": 4, "due": 3},
    }


def test_the_registry_follows_progress(prepared: PrepSession) -> None:
    assert prepared.done(1, note="").status_code == 200
    mysql = ok(prepared.board())["topics"][0]
    assert (mysql["status"], mysql["percent"], mysql["steps_done"]) == (
        "learning",
        33,
        1,
    )
    assert mysql["minutes_left"] == 150


# --- сторінка теми ---------------------------------------------------------------------------


def test_the_topic_page_has_steps_with_details_resources_and_the_quiz(
    prepared: PrepSession,
) -> None:
    prepared.questions(1, "What is an index?", "What is a join?")

    response = prepared.page(1)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert without(body, "steps") == {
        "topic_id": 1,
        "slug": "mysql",
        "title": "Тема mysql",
        "kind": "tech",
        "summary": "Про mysql.",
        "status": "planned",
        "percent": 0,
        "steps_done": 0,
        "steps_total": 3,
        "minutes_left": 210,
        "deadline": "2026-12-01",
        "priority": 140,
        "jobs": [
            {
                "job_id": 1,
                "title": "Backend",
                "company": "Acme",
                "score": 80,
                "gap": "MySQL",
            },
            {
                "job_id": 2,
                "title": "Platform",
                "company": "Zeta",
                "score": 60,
                "gap": "InnoDB",
            },
        ],
        "quiz": {"total": 2, "due": 2},
        "next_step_id": 1,
    }
    assert body["steps"] == [
        {
            "step_id": 1,
            "position": 1,
            "kind": "learn",
            "title": "Прочитати",
            "minutes": 60,
            "details": "Розділ про індекси.",
            "resources": [{"title": "Доки", "url": "https://example.com/docs"}],
            "done_at": None,
            "done_on": None,
            "note": "",
        },
        {
            "step_id": 2,
            "position": 2,
            "kind": "practice",
            "title": "Написати",
            "minutes": 120,
            "details": "",
            "resources": [],
            "done_at": None,
            "done_on": None,
            "note": "",
        },
        {
            "step_id": 3,
            "position": 3,
            "kind": "check",
            "title": "Відповісти",
            "minutes": 30,
            "details": "",
            "resources": [],
            "done_at": None,
            "done_on": None,
            "note": "",
        },
    ]


def test_a_topic_without_a_plan_has_no_steps_and_no_next_step(
    prepared: PrepSession,
) -> None:
    body = ok(prepared.page(2))
    assert (body["steps"], body["next_step_id"], body["status"]) == ([], None, "new")


# --- «виконано» ------------------------------------------------------------------------------


def test_done_returns_the_topic_with_the_step_done_on_the_madrid_day(
    prepared: PrepSession,
) -> None:
    prepared.questions(1, "What is an index?")

    response = prepared.done(1, note="Зрозумів B-tree")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert (body["topic_id"], body["status"], body["percent"]) == (1, "learning", 33)
    assert (body["steps_done"], body["minutes_left"], body["next_step_id"]) == (
        1,
        150,
        2,
    )
    assert body["quiz"] == {"total": 1, "due": 1}
    first = body["steps"][0]
    assert TIMESTAMP.fullmatch(first["done_at"])
    assert first["done_on"] == local_day(datetime.fromisoformat(first["done_at"]))
    assert first["note"] == "Зрозумів B-tree"
    assert body["steps"][1]["done_at"] is None


def test_done_without_a_note_leaves_the_note_empty(prepared: PrepSession) -> None:
    body = ok(prepared.done(1, note=""))
    assert body["steps"][0]["note"] == ""
    assert body["steps"][0]["done_at"] is not None


def test_done_again_keeps_the_first_date_and_replaces_the_note(
    prepared: PrepSession,
) -> None:
    first = ok(prepared.done(1, note="Перша"))["steps"][0]
    second = ok(prepared.done(1, note="Друга"))["steps"][0]
    assert second["done_at"] == first["done_at"]
    assert second["done_on"] == first["done_on"]
    assert second["note"] == "Друга"
    third = ok(prepared.done(1, note=""))["steps"][0]
    assert (third["done_at"], third["note"]) == (first["done_at"], "Друга")


def test_a_note_of_2000_characters_is_accepted(prepared: PrepSession) -> None:
    response = prepared.done(1, note="а" * 2000)
    assert response.status_code == 200
    assert response.json()["steps"][0]["note"] == "а" * 2000


def test_a_note_of_2001_characters_is_422_at_note_and_the_step_stays_pending(
    prepared: PrepSession,
) -> None:
    response = prepared.done(1, note="а" * 2001)
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_value"
    assert field_errors(response) == [("note", BAD_NOTE)]
    assert ok(prepared.page(1))["steps"][0]["done_at"] is None


@pytest.mark.parametrize(
    "body", [{}, {"note": None}, {"note": 5}, {"note": "x", "extra": 1}]
)
def test_a_malformed_done_body_is_422_invalid_request(
    prepared: PrepSession, body: dict[str, object]
) -> None:
    response = prepared.done(1, **body)
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"
    assert ok(prepared.page(1))["steps"][0]["done_at"] is None


# --- «готово» --------------------------------------------------------------------------------


def test_ready_marks_the_topic_100_percent_and_unmarking_restores_the_status(
    prepared: PrepSession,
) -> None:
    prepared.done(1, note="")

    marked = prepared.ready(1, ready=True)
    assert marked.status_code == 200
    assert marked.headers["cache-control"] == "no-store"
    body = marked.json()
    assert (body["status"], body["percent"], body["steps_done"]) == ("ready", 100, 1)

    again = ok(prepared.ready(1, ready=True))
    assert (again["status"], again["percent"]) == ("ready", 100)

    unmarked = ok(prepared.ready(1, ready=False))
    assert (unmarked["status"], unmarked["percent"]) == ("learning", 33)


@pytest.mark.parametrize("body", [{}, {"ready": None}, {"ready": True, "extra": 1}])
def test_a_malformed_ready_body_is_422_invalid_request(
    prepared: PrepSession, body: dict[str, object]
) -> None:
    response = prepared.ready(1, **body)
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"
    assert ok(prepared.page(1))["status"] == "planned"


# --- підготовка до вакансії ------------------------------------------------------------------


def test_a_job_without_topics_has_no_readiness(alice: PrepSession) -> None:
    alice.job("Docs", "Acme", 50)
    response = alice.job_prep(1)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"readiness": None, "topics": []}


def test_a_job_without_analysis_has_no_topics_and_is_not_an_error(
    alice: PrepSession,
) -> None:
    alice.jobs.add(text="Raw posting", title="Raw")
    assert ok(alice.job_prep(1)) == {"readiness": None, "topics": []}


def test_a_job_shows_only_its_topics_and_their_readiness(
    prepared: PrepSession,
) -> None:
    prepared.ready(1, ready=True)

    second = ok(prepared.job_prep(2))
    assert [t["slug"] for t in second["topics"]] == ["mysql"]
    assert second["readiness"] == 100

    first = ok(prepared.job_prep(1))
    assert [t["slug"] for t in first["topics"]] == ["mysql", "kafka"]
    assert first["readiness"] == 50
    assert [job["job_id"] for job in first["topics"][0]["jobs"]] == [1, 2]


def test_the_readiness_of_a_job_rounds_half_up(prepared: PrepSession) -> None:
    prepared.done(1, note="")
    prepared.ready(2, ready=True)
    assert ok(prepared.job_prep(1))["readiness"] == 67


def test_the_topics_of_a_job_carry_progress_and_the_quiz(
    prepared: PrepSession,
) -> None:
    prepared.questions(2, "What is a topic?")
    kafka = ok(prepared.job_prep(1))["topics"][1]
    assert (kafka["slug"], kafka["status"], kafka["percent"]) == ("kafka", "new", 0)
    assert kafka["quiz"] == {"total": 1, "due": 1}
    assert "steps" not in kafka


# --- пакет до інтерв'ю -----------------------------------------------------------------------


def test_a_job_without_a_kit_is_404(prepared: PrepSession) -> None:
    response = prepared.interview_kit(1)
    assert (response.status_code, response.json()["code"]) == (404, "not_found")


def test_the_latest_kit_comes_back_whole(prepared: PrepSession) -> None:
    prepared.kit(1, tag="old ", topic=1)
    prepared.kit(1, tag="", topic=2)

    response = prepared.interview_kit(1)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert TIMESTAMP.fullmatch(body["created_at"])
    assert body["created_on"] == local_day(datetime.fromisoformat(body["created_at"]))
    assert without(body, "created_at", "created_on") == {
        "kit_id": 2,
        "job_id": 1,
        "version": 2,
        "questions": [
            {"kind": "technical", "question": "Question 1?", "topic_id": 2},
            {"kind": "behavioral", "question": "Question 2?", "topic_id": None},
            {"kind": "technical", "question": "Question 3?", "topic_id": None},
            {"kind": "behavioral", "question": "Question 4?", "topic_id": None},
            {"kind": "technical", "question": "Question 5?", "topic_id": None},
        ],
        "stories": [
            {
                "title": f"Story {n}",
                "situation": f"Situation {n}",
                "task": f"Task {n}",
                "action": f"Action {n}",
                "result": f"Result {n}",
                "fact_ids": [2],
            }
            for n in range(1, 4)
        ],
        "company_questions": ["Ask 1?", "Ask 2?", "Ask 3?"],
    }


def test_a_kit_belongs_to_its_job(prepared: PrepSession) -> None:
    prepared.kit(1)
    assert prepared.interview_kit(1).status_code == 200
    assert prepared.interview_kit(2).status_code == 404


def test_another_users_kit_is_not_visible(
    prepared: PrepSession, bob: PrepSession
) -> None:
    prepared.kit(1)
    bob.job("Backend", "Acme", 70)
    assert bob.interview_kit(1).status_code == 404


# --- ключ оцінки -----------------------------------------------------------------------------


def test_the_answer_key_is_never_returned(prepared: PrepSession) -> None:
    prepared.questions(1, "What is an index?", "What is a join?")
    prepared.answer(1, 5)
    prepared.kit(1, topic=1)

    responses = (
        prepared.board(),
        prepared.page(1),
        prepared.done(2, note="Зроблено"),
        prepared.ready(1, ready=True),
        prepared.job_prep(1),
        prepared.interview_kit(1),
    )

    for response in responses:
        assert response.status_code == 200, response.text
        assert SECRET not in response.text
        assert "answer_points" not in response.text
        assert "Моя відповідь." not in response.text
