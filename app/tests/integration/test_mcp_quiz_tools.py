"""Тули квізу через SDK-клієнт: DCR → токен → `tools/list` і виклики на справжньому Postgres."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client

from domain.shared.local_time import local_today
from tests.integration.test_agent_http import PUBLIC, Agent
from tests.integration.test_mcp_job_tools import data, error_text
from tests.integration.test_mcp_prep_plan_tools import PLAN, complete, plan
from tests.integration.test_mcp_prep_tools import MYSQL, STAR, analysed, save
from tests.integration.test_mcp_profile_tools import (
    TOOLS,
    agent,
    anyio_backend,
    call,
    katya,
    taras,
)

__all__ = ["agent", "anyio_backend"]

pytestmark = pytest.mark.anyio

NAMES = ("prepare_questions", "save_questions", "due_questions", "record_answer")
INDEX: dict[str, Any] = {
    "question": "What is a covering index?",
    "answer_points": ["Holds every column the query needs", "No table lookup"],
}
EXPLAIN: dict[str, Any] = {
    "question": "How do you read EXPLAIN in MySQL?",
    "answer_points": ["type", "rows", "Extra"],
}


async def topics(agent: Agent, token: str) -> tuple[int, int]:
    """Вакансія 1 з темами `mysql-query-optimization` (1) і `star-conflict` (2)."""
    job = await analysed(agent, token, 82)
    saved = await save(agent, token, job, MYSQL, STAR)
    first, second = (t["topic_id"] for t in saved["topics"])
    return int(first), int(second)


async def add_questions(
    agent: Agent, token: str, topic: int, *questions: dict[str, Any]
) -> dict[str, Any]:
    return data(
        await call(
            agent,
            token,
            "save_questions",
            {"topic_id": topic, "questions": list(questions)},
        )
    )


async def answer(
    agent: Agent, token: str, question: int, grade: int, text: str = "", note: str = ""
) -> dict[str, Any]:
    return data(
        await call(
            agent,
            token,
            "record_answer",
            {"question_id": question, "grade": grade, "answer": text, "feedback": note},
        )
    )


async def due(agent: Agent, token: str, **arguments: Any) -> dict[str, Any]:
    return data(await call(agent, token, "due_questions", arguments))


def days(first: date, last: date, offset: int) -> set[str]:
    """Дні `сьогодні + offset` для обох боків можливої північі в Мадриді під час виклику."""
    return {
        (first + timedelta(days=offset)).isoformat(),
        (last + timedelta(offset)).isoformat(),
    }


async def test_tools_list_has_the_four_quiz_tools_with_the_catalog_descriptions(
    agent: Agent,
) -> None:
    token = await taras(agent)
    async with agent.authed(token) as authed:
        transport = streamable_http_client(PUBLIC, http_client=authed)
        async with Client(transport) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}

    for name in NAMES:
        assert name in tools
        assert tools[name].description == (TOOLS / f"{name}.md").read_text(
            encoding="utf-8"
        )


async def test_the_questions_brief_has_the_topic_the_questions_and_the_rules(
    agent: Agent,
) -> None:
    token = await taras(agent)
    mysql, _ = await topics(agent, token)
    await plan(agent, token, mysql, PLAN)
    await complete(agent, token, 1, "Прочитав про B-tree")
    await add_questions(agent, token, mysql, INDEX)

    brief = data(await call(agent, token, "prepare_questions", {"topic_id": mysql}))

    assert brief["topic"]["slug"] == "mysql-query-optimization"
    assert [s["note"] for s in brief["topic"]["steps"]][:1] == ["Прочитав про B-tree"]
    assert [q["question"] for q in brief["questions"]] == ["What is a covering index?"]
    assert brief["rules"].startswith(
        "Write interview questions for this topic in English"
    )
    assert "Taras" not in brief["rules"]


async def test_saved_questions_start_in_box_1_and_are_due_today_in_madrid(
    agent: Agent,
) -> None:
    token = await taras(agent)
    mysql, _ = await topics(agent, token)

    before = local_today(datetime.now(UTC))
    saved = await add_questions(agent, token, mysql, INDEX, EXPLAIN)
    after = local_today(datetime.now(UTC))

    assert [a["due"] in days(before, after, 0) for a in saved["added"]] == [True, True]
    assert [{k: v for k, v in a.items() if k != "due"} for a in saved["added"]] == [
        {
            "question_id": 1,
            "topic_id": mysql,
            "topic_title": "Оптимізація запитів MySQL",
            "question": "What is a covering index?",
            "box": 1,
        },
        {
            "question_id": 2,
            "topic_id": mysql,
            "topic_title": "Оптимізація запитів MySQL",
            "question": "How do you read EXPLAIN in MySQL?",
            "box": 1,
        },
    ]
    assert saved["skipped_duplicates"] == []


async def test_a_question_the_topic_already_has_is_skipped(agent: Agent) -> None:
    token = await taras(agent)
    mysql, star = await topics(agent, token)
    await add_questions(agent, token, mysql, INDEX)

    again = {**INDEX, "question": "  what is a COVERING   index? "}
    saved = await add_questions(agent, token, mysql, again, EXPLAIN)
    other = await add_questions(agent, token, star, INDEX)

    assert [a["question_id"] for a in saved["added"]] == [2]
    assert saved["skipped_duplicates"] == ["what is a COVERING index?"]
    assert [a["question_id"] for a in other["added"]] == [3]


async def test_an_invalid_question_rejects_the_whole_call(agent: Agent) -> None:
    token = await taras(agent)
    mysql, _ = await topics(agent, token)

    bad = await call(
        agent,
        token,
        "save_questions",
        {
            "topic_id": mysql,
            "questions": [INDEX, {"question": "q" * 501, "answer_points": ["x"]}],
        },
    )
    empty = await call(
        agent, token, "save_questions", {"topic_id": mysql, "questions": []}
    )
    many = await call(
        agent,
        token,
        "save_questions",
        {
            "topic_id": mysql,
            "questions": [
                {"question": f"Q{n}?", "answer_points": ["x"]} for n in range(21)
            ],
        },
    )

    assert "Питання 2: питання — від 1 до 500 символів." in error_text(bad)
    assert "Список питань порожній." in error_text(empty)
    assert "За раз — до 20 питань." in error_text(many)
    brief = data(await call(agent, token, "prepare_questions", {"topic_id": mysql}))
    assert brief["questions"] == []


async def test_a_missing_or_foreign_topic_is_a_tool_error(agent: Agent) -> None:
    taras_token, katya_token = await taras(agent), await katya(agent)
    await topics(agent, taras_token)

    for name, arguments in (
        ("prepare_questions", {"topic_id": 1}),
        ("save_questions", {"topic_id": 1, "questions": [INDEX]}),
        ("due_questions", {"topic_id": 1}),
    ):
        result = await call(agent, katya_token, name, arguments)
        assert "Тему 1 не знайдено." in error_text(result), name
    mine = data(await call(agent, taras_token, "prepare_questions", {"topic_id": 1}))
    assert mine["questions"] == []


async def test_due_questions_carry_the_key_and_the_quiz_rules(agent: Agent) -> None:
    token = await taras(agent)
    mysql, _ = await topics(agent, token)
    await add_questions(agent, token, mysql, INDEX, EXPLAIN)

    quiz = await due(agent, token)

    assert quiz["total_due"] == 2
    first = quiz["questions"][0]
    assert first["question_id"] == 1
    assert first["answer_points"] == [
        "Holds every column the query needs",
        "No table lookup",
    ]
    assert (first["box"], first["topic_title"]) == (1, "Оптимізація запитів MySQL")
    assert quiz["rules"].startswith("Run the quiz one question at a time.")
    assert "Taras" not in quiz["rules"]


async def test_the_key_is_shown_only_in_due_questions(agent: Agent) -> None:
    token = await taras(agent)
    mysql, _ = await topics(agent, token)

    saved = await add_questions(agent, token, mysql, INDEX)
    brief = data(await call(agent, token, "prepare_questions", {"topic_id": mysql}))
    quiz = await due(agent, token)
    answered = await answer(agent, token, 1, 3)

    assert "answer_points" not in saved["added"][0]
    assert "answer_points" not in brief["questions"][0]
    assert "answer_points" not in answered
    assert "answer_points" in quiz["questions"][0]


async def test_due_questions_honour_the_limit_the_topic_and_the_order(
    agent: Agent,
) -> None:
    token = await taras(agent)
    mysql, star = await topics(agent, token)
    await add_questions(agent, token, mysql, INDEX, EXPLAIN)
    await add_questions(
        agent, token, star, {"question": "Conflict?", "answer_points": ["STAR"]}
    )
    await answer(agent, token, 1, 5)

    everything = await due(agent, token)
    limited = await due(agent, token, limit=1)
    in_star = await due(agent, token, topic_id=star)

    assert [q["question_id"] for q in everything["questions"]] == [2, 3]
    assert [q["question_id"] for q in limited["questions"]] == [2]
    assert (limited["total_due"], in_star["total_due"]) == (2, 1)
    assert [q["question_id"] for q in in_star["questions"]] == [3]


async def test_a_limit_outside_1_to_50_is_a_tool_error(agent: Agent) -> None:
    token = await taras(agent)
    await topics(agent, token)

    assert (await call(agent, token, "due_questions", {"limit": 0})).is_error
    assert (await call(agent, token, "due_questions", {"limit": 51})).is_error
    assert (await call(agent, token, "due_questions", {"limit": 50})).is_error is False


async def test_a_pass_moves_the_question_up_a_box_and_a_fail_sends_it_back(
    agent: Agent,
) -> None:
    token = await taras(agent)
    mysql, _ = await topics(agent, token)
    await add_questions(agent, token, mysql, INDEX)

    before = local_today(datetime.now(UTC))
    passed = await answer(agent, token, 1, 4, "A covering index.", "Добре.")
    mid = local_today(datetime.now(UTC))
    failed = await answer(agent, token, 1, 1, "No idea.", "Повтори.")
    after = local_today(datetime.now(UTC))

    assert (passed["question_id"], passed["box"]) == (1, 2)
    assert passed["due"] in days(before, mid, 2)
    assert (failed["box"], failed["due"] in days(mid, after, 1)) == (1, True)
    assert set(passed) == {
        "question_id",
        "topic_id",
        "topic_title",
        "question",
        "box",
        "due",
    }


async def test_an_answered_question_leaves_the_quiz_until_its_day(agent: Agent) -> None:
    token = await taras(agent)
    mysql, _ = await topics(agent, token)
    await add_questions(agent, token, mysql, INDEX)

    await answer(agent, token, 1, 3)

    quiz = await due(agent, token)
    assert (quiz["questions"], quiz["total_due"]) == ([], 0)


async def test_an_invalid_answer_is_a_tool_error_and_changes_nothing(
    agent: Agent,
) -> None:
    token = await taras(agent)
    mysql, _ = await topics(agent, token)
    await add_questions(agent, token, mysql, INDEX)

    too_long = await call(
        agent,
        token,
        "record_answer",
        {"question_id": 1, "grade": 3, "answer": "a" * 4001, "feedback": ""},
    )
    long_feedback = await call(
        agent,
        token,
        "record_answer",
        {"question_id": 1, "grade": 3, "answer": "", "feedback": "f" * 2001},
    )
    bad_grade = await call(
        agent,
        token,
        "record_answer",
        {"question_id": 1, "grade": 6, "answer": "", "feedback": ""},
    )

    assert "Відповідь — до 4000 символів." in error_text(too_long)
    assert "Фідбек — до 2000 символів." in error_text(long_feedback)
    assert bad_grade.is_error
    quiz = await due(agent, token)
    assert [(q["question_id"], q["box"]) for q in quiz["questions"]] == [(1, 1)]


async def test_a_missing_or_foreign_question_is_a_tool_error(agent: Agent) -> None:
    taras_token, katya_token = await taras(agent), await katya(agent)
    mysql, _ = await topics(agent, taras_token)
    await add_questions(agent, taras_token, mysql, INDEX)

    foreign = await call(
        agent,
        katya_token,
        "record_answer",
        {"question_id": 1, "grade": 5, "answer": "", "feedback": ""},
    )
    missing = await call(
        agent,
        taras_token,
        "record_answer",
        {"question_id": 9, "grade": 5, "answer": "", "feedback": ""},
    )

    assert "Питання 1 не знайдено." in error_text(foreign)
    assert "Питання 9 не знайдено." in error_text(missing)
    assert (await due(agent, taras_token))["questions"][0]["box"] == 1


async def test_every_user_has_their_own_questions_and_numbers(agent: Agent) -> None:
    taras_token, katya_token = await taras(agent), await katya(agent)
    mysql, _ = await topics(agent, taras_token)
    await add_questions(agent, taras_token, mysql, INDEX)
    job = await analysed(agent, katya_token, 70, who="katya@example.com")
    saved = await save(agent, katya_token, job, MYSQL)
    theirs = int(saved["topics"][0]["topic_id"])

    own = await add_questions(agent, katya_token, theirs, INDEX)

    assert [a["question_id"] for a in own["added"]] == [1]
    assert own["skipped_duplicates"] == []
    assert (await due(agent, katya_token))["total_due"] == 1
