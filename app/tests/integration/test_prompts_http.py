"""Тексти запитів до агента через HTTP: веб бере їх із сервера дослівно, лише для користувача із сесією."""

from pathlib import Path

from tests.integration.test_profile_http import (
    ClientFactory,
    Session,
    alice,
    make_client,
)

__all__ = ["alice", "make_client"]

CATALOG = Path(__file__).resolve().parents[2] / "prompts"

SERVED = [
    "onboarding/setup",
    "requests/analysis",
    "requests/triage",
    "requests/cv",
    "requests/cover_letter",
    "requests/plan",
    "requests/questions",
    "requests/quiz",
    "requests/quiz_topic",
    "requests/topics",
    "requests/job_prep",
    "requests/interview_kit",
    "requests/gaps",
    "requests/facts",
    "requests/add_job",
    "requests/reanalysis",
    "requests/apply",
]

# Кроки ланцюжка сценаріїв, що пропонують наступний: сервер дописує до них однаковий хвіст.
TAILED = [
    "requests/add_job",
    "requests/analysis",
    "requests/gaps",
    "requests/reanalysis",
    "requests/cv",
    "requests/cover_letter",
]


def test_prompts_require_a_session(make_client: ClientFactory) -> None:
    response = make_client().get("/prompts")

    assert (response.status_code, response.json()["code"]) == (401, "not_authenticated")


def test_the_response_names_exactly_the_web_prompts(alice: Session) -> None:
    response = alice.client.get("/prompts")

    assert response.status_code == 200, response.text
    assert sorted(response.json()) == sorted(SERVED)


def test_each_template_is_returned_verbatim(alice: Session) -> None:
    served = alice.client.get("/prompts").json()

    for key in SERVED:
        if key in TAILED:
            continue
        file = CATALOG / f"{key}.md"
        assert served[key] == file.read_bytes().decode("utf-8"), key


def test_each_scenario_template_is_followed_by_the_next_step_tail(
    alice: Session,
) -> None:
    served = alice.client.get("/prompts").json()
    tail = (CATALOG / "scenarios" / "next_step.md").read_bytes().decode("utf-8")

    for key in TAILED:
        file = CATALOG / f"{key}.md"
        assert served[key] == f"{file.read_bytes().decode('utf-8')}\n\n{tail}", key


def test_the_apply_template_has_no_tail(alice: Session) -> None:
    served = alice.client.get("/prompts").json()

    assert served["requests/apply"] == (CATALOG / "requests" / "apply.md").read_text(
        encoding="utf-8"
    )


def test_the_response_is_not_cached(alice: Session) -> None:
    response = alice.client.get("/prompts")

    assert response.headers["Cache-Control"] == "no-store"


def test_agent_rules_are_not_served_to_the_web(alice: Session) -> None:
    response = alice.client.get("/prompts")

    assert response.status_code == 200, response.text
    served = response.json()
    assert "mcp/instructions" not in served
    assert "analysis/rubric" not in served
    assert "triage/rules" not in served
    assert "scenarios/next_step" not in served
