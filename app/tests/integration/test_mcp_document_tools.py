"""Тули документів через SDK-клієнт: DCR → токен → `tools/list` і виклики на справжньому Postgres і справжньому PDF.

Потрібні pango, harfbuzz і шрифти DejaVu (образ і CI мають їх).
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from mcp.client import Client
from mcp.client.streamable_http import streamable_http_client

from application.contracts.actor import Actor, Channel, Scope
from domain.documents.document import Claim, Cv, CvEntry, CvSection, CvSectionName
from domain.documents.ids import DocumentId
from domain.identity.ids import UserId
from domain.shared.errors import NotFound
from domain.shared.local_time import local_day
from tests.integration.test_agent_http import BASE, PUBLIC, Agent
from tests.integration.test_mcp_analysis_tools import add_fact, seed
from tests.integration.test_mcp_analysis_tools import save as save_analysis
from tests.integration.test_mcp_job_tools import data, error_text
from tests.integration.test_mcp_photo_tools import add_photo
from tests.integration.test_mcp_profile_tools import (
    FULL,
    TOOLS,
    agent,
    anyio_backend,
    call,
    katya,
    taras,
    update_profile,
)

__all__ = ["agent", "anyio_backend"]

pytestmark = pytest.mark.anyio

WEB = BASE  # агент і веб — один origin: адреса агента рахується з web_public_url
NO_NAME = "У профілі нема імені для шапки документа: заповни контакти (update_profile)."
DOCUMENT_TOOLS = (
    "prepare_cv",
    "save_cv",
    "prepare_cover_letter",
    "save_cover_letter",
    "list_documents",
    "check_cv",
    "check_cover_letter",
)


@pytest.fixture(autouse=True)
def documents_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "documents"
    monkeypatch.setenv("JOBOFFER_DOCUMENTS_DIR", str(root))
    monkeypatch.setenv("JOBOFFER_WEB_PUBLIC_URL", WEB)
    return root


def stored_files(root: Path) -> list[Path]:
    return list(root.iterdir()) if root.exists() else []


def claim(text: str, *fact_ids: int) -> dict[str, Any]:
    return {"text": text, "fact_ids": list(fact_ids)}


def cv_arguments(
    fact: int, summary: str = "Payments backend engineer"
) -> dict[str, Any]:
    return {
        "headline": claim("Senior Backend Engineer", fact),
        "summary": claim(summary, fact),
        "sections": [
            {
                "name": "Experience",
                "entries": [
                    {
                        "heading": claim("Engineer · Acme", fact),
                        "meta": claim("2021 - 2024", fact),
                        "subtitle": claim("Payments team of five", fact),
                        "bullets": [claim("Built payment APIs in Python", fact)],
                    }
                ],
            },
            {
                "name": "Skills",
                "entries": [
                    {
                        "heading": claim("Backend", fact),
                        "meta": None,
                        "subtitle": None,
                        "bullets": [claim("Python", fact), claim("Postgres", fact)],
                    }
                ],
            },
        ],
    }


def letter_arguments(fact: int, words: int = 160) -> dict[str, Any]:
    text = (
        "Dear team,\n\n" + " ".join(["word"] * words) + "\n\nBest regards,\nTest User"
    )
    return {"text": text, "fact_ids": [fact]}


async def ready(
    agent: Agent, token: str, who: str = "taras@example.com"
) -> tuple[int, int]:
    """Профіль з іменем, вакансія з текстом і підтверджений факт."""
    await update_profile(agent, token, FULL)
    number = await seed(agent, "Senior Python engineer. Remote.", who=who)
    fact = await add_fact(agent, token, "skill", "Python")
    data(await call(agent, token, "confirm_facts", {"fact_ids": [fact]}))
    return number, fact


async def save_cv(
    agent: Agent, token: str, job: int, cv: dict[str, Any]
) -> dict[str, Any]:
    return data(await call(agent, token, "save_cv", {"job_id": job, "cv": cv}))


async def save_letter(
    agent: Agent, token: str, job: int, letter: dict[str, Any]
) -> dict[str, Any]:
    return data(
        await call(agent, token, "save_cover_letter", {"job_id": job, **letter})
    )


async def test_tools_list_has_the_seven_document_tools_with_the_catalog_descriptions(
    agent: Agent,
) -> None:
    token = await taras(agent)
    async with agent.authed(token) as authed:
        transport = streamable_http_client(PUBLIC, http_client=authed)
        async with Client(transport) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}

    assert set(DOCUMENT_TOOLS) <= set(tools)
    for name in DOCUMENT_TOOLS:
        assert tools[name].description == (TOOLS / f"{name}.md").read_text(
            encoding="utf-8"
        )


async def test_the_cv_brief_has_the_job_analysis_profile_facts_rules_and_photos(
    agent: Agent,
) -> None:
    token = await taras(agent)
    number, fact = await ready(agent, token)

    brief = data(await call(agent, token, "prepare_cv", {"job_id": number}))

    assert set(brief) == {
        "job",
        "analysis",
        "profile",
        "confirmed_facts",
        "rules",
        "previous",
        "photos",
        "ceiling",
    }
    assert brief["ceiling"] is None
    assert brief["photos"] == {
        "photos": [],
        "suggested_photo_id": None,
        "photo_upload_url": f"{WEB}/profile/photos",
    }
    assert brief["job"]["job_id"] == number
    assert brief["analysis"] is None
    assert brief["profile"] == FULL
    assert brief["confirmed_facts"] == [
        {"fact_id": fact, "kind": "skill", "text": "Python", "confirmed": True}
    ]
    assert brief["rules"] == (
        TOOLS.parent.parent / "documents" / "cv_rules.md"
    ).read_text(encoding="utf-8")
    assert brief["previous"] is None


async def test_the_cv_and_letter_briefs_carry_candidate_asks_of_the_analysis(
    agent: Agent,
) -> None:
    token = await taras(agent)
    number, _ = await ready(agent, token)
    asks = ["Send your GitHub", "Skip the list of frameworks"]
    await save_analysis(agent, token, number, candidate_asks=asks)

    cv = data(await call(agent, token, "prepare_cv", {"job_id": number}))
    letter = data(await call(agent, token, "prepare_cover_letter", {"job_id": number}))

    assert cv["analysis"]["candidate_asks"] == asks
    assert letter["analysis"]["candidate_asks"] == asks


async def test_the_cv_brief_carries_the_gap_analogues_of_the_analysis(
    agent: Agent,
) -> None:
    token = await taras(agent)
    number, fact = await ready(agent, token)
    await save_analysis(
        agent,
        token,
        number,
        gaps=["gRPC", "OpenTelemetry"],
        gap_analogues=[
            {
                "gap": "gRPC",
                "analogues": [{"fact_ids": [fact], "explanation": "Python services"}],
            }
        ],
    )

    brief = data(await call(agent, token, "prepare_cv", {"job_id": number}))

    assert brief["analysis"]["gap_analogues"] == [
        {
            "gap": "gRPC",
            "analogues": [{"fact_ids": [fact], "explanation": "Python services"}],
            "no_honest_analogue": False,
        },
        {"gap": "OpenTelemetry", "analogues": [], "no_honest_analogue": True},
    ]


async def test_the_cv_brief_of_an_analysis_without_analogues_shows_null(
    agent: Agent,
) -> None:
    token = await taras(agent)
    number, _ = await ready(agent, token)
    await save_analysis(agent, token, number, gaps=["gRPC"])

    brief = data(await call(agent, token, "prepare_cv", {"job_id": number}))

    assert brief["analysis"]["gap_analogues"] is None


async def test_the_letter_brief_works_without_a_cv_and_then_has_the_last_one(
    agent: Agent,
) -> None:
    token = await taras(agent)
    number, fact = await ready(agent, token)

    first = data(await call(agent, token, "prepare_cover_letter", {"job_id": number}))
    await save_cv(agent, token, number, cv_arguments(fact))
    second = data(await call(agent, token, "prepare_cover_letter", {"job_id": number}))

    assert (first["cv"], first["previous"]) == (None, None)
    assert second["rules"] == (
        TOOLS.parent.parent / "documents" / "cover_letter_rules.md"
    ).read_text(encoding="utf-8")
    assert (second["cv"]["kind"], second["cv"]["version"]) == ("cv", 1)
    assert second["previous"] is None


async def test_a_saved_cv_has_a_pdf_file_a_link_and_a_clean_lint(
    agent: Agent, documents_dir: Path
) -> None:
    token = await taras(agent)
    number, fact = await ready(agent, token)

    saved = await save_cv(agent, token, number, cv_arguments(fact))

    assert saved["created"] == local_day(datetime.now(UTC))
    assert {k: saved[k] for k in ("document_id", "job_id", "kind", "version")} == {
        "document_id": 1,
        "job_id": number,
        "kind": "cv",
        "version": 1,
    }
    assert saved["pdf_url"] == f"{WEB}/api/documents/1/pdf"
    assert saved["cover_letter"] is None
    assert saved["cv"] == cv_arguments(fact)
    assert saved["lint"] == {
        "passed": True,
        "pages": 1,
        "issues": [],
        "keywords_covered": None,
        "keywords_missing": None,
        "keyword_coverage_percent": None,
    }
    assert saved["photo_id"] is None
    [file] = stored_files(documents_dir)
    assert file.read_bytes().startswith(b"%PDF")


async def test_a_saved_letter_has_the_text_a_link_and_a_clean_lint(
    agent: Agent,
) -> None:
    token = await taras(agent)
    number, fact = await ready(agent, token)

    saved = await save_letter(agent, token, number, letter_arguments(fact))

    assert (saved["kind"], saved["version"], saved["cv"]) == ("cl", 1, None)
    assert saved["cover_letter"] == letter_arguments(fact)
    assert saved["pdf_url"] == f"{WEB}/api/documents/1/pdf"
    assert saved["lint"]["passed"] is True
    assert saved["lint"]["pages"] == 1


async def test_the_keywords_of_the_analysis_are_in_the_lint(agent: Agent) -> None:
    token = await taras(agent)
    number, fact = await ready(agent, token)
    data(
        await call(
            agent,
            token,
            "save_analysis",
            {
                "job_id": number,
                "analysis": {
                    "score": 70,
                    "summary": "S.",
                    "keywords": ["payment APIs", "Kafka"],
                },
            },
        )
    )

    saved = await save_cv(agent, token, number, cv_arguments(fact))

    assert saved["lint"]["keywords_covered"] == ["payment APIs"]
    assert saved["lint"]["keywords_missing"] == ["Kafka"]
    assert saved["lint"]["keyword_coverage_percent"] == 50
    assert saved["lint"]["passed"] is True


async def test_an_unknown_or_unconfirmed_fact_is_a_tool_error_and_nothing_is_saved(
    agent: Agent, documents_dir: Path
) -> None:
    token = await taras(agent)
    number, _ = await ready(agent, token)
    rust = await add_fact(agent, token, "skill", "Rust")

    unknown = await call(
        agent, token, "save_cv", {"job_id": number, "cv": cv_arguments(99)}
    )
    unconfirmed = await call(
        agent, token, "save_cv", {"job_id": number, "cv": cv_arguments(rust)}
    )

    assert "Факти не знайдено: #99." in error_text(unknown)
    assert f"Факти не підтверджені: #{rust} — спершу користувач їх підтверджує." in (
        error_text(unconfirmed)
    )
    listed = data(await call(agent, token, "list_documents", {"job_id": number}))
    assert listed["documents"] == []
    assert stored_files(documents_dir) == []


async def test_a_letter_with_a_placeholder_or_the_wrong_length_is_a_tool_error(
    agent: Agent,
) -> None:
    token = await taras(agent)
    number, fact = await ready(agent, token)

    short = await call(
        agent,
        token,
        "save_cover_letter",
        {"job_id": number, **letter_arguments(fact, 20)},
    )
    template = letter_arguments(fact)
    template["text"] = template["text"].replace("Dear team", "Dear [Company]")
    placeholder = await call(
        agent, token, "save_cover_letter", {"job_id": number, **template}
    )

    assert "Лист — 150–250 слів, а тут 26." in error_text(short)
    assert "Незаповнений шаблон у листі: [Company]." in error_text(placeholder)


async def test_a_profile_without_a_name_cannot_save_a_document(agent: Agent) -> None:
    token = await taras(agent)
    number = await seed(agent)
    fact = await add_fact(agent, token, "skill", "Python")
    data(await call(agent, token, "confirm_facts", {"fact_ids": [fact]}))

    result = await call(
        agent, token, "save_cv", {"job_id": number, "cv": cv_arguments(fact)}
    )

    assert NO_NAME in error_text(result)


async def test_a_missing_job_is_a_tool_error_in_every_tool(agent: Agent) -> None:
    token = await taras(agent)
    _, fact = await ready(agent, token)

    for name, arguments in (
        ("prepare_cv", {"job_id": 9}),
        ("prepare_cover_letter", {"job_id": 9}),
        ("save_cv", {"job_id": 9, "cv": cv_arguments(fact)}),
        ("save_cover_letter", {"job_id": 9, **letter_arguments(fact)}),
    ):
        assert "Вакансію 9 не знайдено." in error_text(
            await call(agent, token, name, arguments)
        ), name
    assert data(await call(agent, token, "list_documents", {"job_id": 9})) == {
        "documents": []
    }


async def test_one_cv_and_one_letter_are_listed_newest_first_each_with_its_own_link_and_lint(
    agent: Agent,
) -> None:
    token = await taras(agent)
    number, fact = await ready(agent, token)
    await save_cv(agent, token, number, cv_arguments(fact, "First"))
    await save_letter(agent, token, number, letter_arguments(fact))
    await save_cv(agent, token, number, cv_arguments(fact, "Second"))

    listed = data(await call(agent, token, "list_documents", {"job_id": number}))[
        "documents"
    ]

    assert [(d["document_id"], d["kind"], d["version"]) for d in listed] == [
        (3, "cv", 2),
        (2, "cl", 1),
    ]
    assert [d["pdf_url"] for d in listed] == [
        f"{WEB}/api/documents/{n}/pdf" for n in (3, 2)
    ]
    assert all(d["lint"]["passed"] is True for d in listed)
    assert [d["cv"]["summary"]["text"] for d in listed if d["cv"]] == ["Second"]


async def test_a_user_never_sees_documents_of_another(agent: Agent) -> None:
    owner = await taras(agent)
    other = await katya(agent)
    number, fact = await ready(agent, owner)
    await save_cv(agent, owner, number, cv_arguments(fact))

    listed = data(await call(agent, other, "list_documents", {"job_id": number}))
    brief = await call(agent, other, "prepare_cv", {"job_id": number})

    assert listed == {"documents": []}
    assert "Вакансію" in error_text(brief)


# --- перевірка без збереження (check_cv, check_cover_letter) ---------------------------------


async def check_cv(
    agent: Agent,
    token: str,
    job: int,
    cv: dict[str, Any],
    photo_id: int | None = None,
    must_have_facts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    arguments = {"job_id": job, "cv": cv, "photo_id": photo_id}
    if must_have_facts is not None:
        arguments["must_have_facts"] = must_have_facts
    return data(await call(agent, token, "check_cv", arguments))


async def check_letter(
    agent: Agent, token: str, job: int, letter: dict[str, Any]
) -> dict[str, Any]:
    return data(
        await call(agent, token, "check_cover_letter", {"job_id": job, **letter})
    )


async def nothing_saved(
    agent: Agent, token: str, job: int, documents_dir: Path
) -> None:
    listed = data(await call(agent, token, "list_documents", {"job_id": job}))
    assert listed["documents"] == []
    assert stored_files(documents_dir) == []


def with_bullet(fact: int, bullet: str) -> dict[str, Any]:
    cv = cv_arguments(fact)
    cv["sections"][0]["entries"][0]["bullets"] = [claim(bullet, fact)]
    return cv


async def test_check_cv_reports_a_placeholder_and_saves_nothing(
    agent: Agent, documents_dir: Path
) -> None:
    token = await taras(agent)
    number, fact = await ready(agent, token)

    checked = await check_cv(
        agent, token, number, with_bullet(fact, "Worked at [Company]")
    )

    assert set(checked) == {
        "passed",
        "issues",
        "keywords",
        "gate",
        "must_have_coverage",
    }
    assert checked["passed"] is False
    [issue] = checked["issues"]
    assert issue["code"] == "placeholder"
    assert "[Company]" in issue["message"]
    assert checked["keywords"] is None
    await nothing_saved(agent, token, number, documents_dir)


async def test_check_cv_reports_a_line_break_and_an_unconfirmed_fact_together(
    agent: Agent, documents_dir: Path
) -> None:
    token = await taras(agent)
    number, fact = await ready(agent, token)
    rust = await add_fact(agent, token, "skill", "Rust")
    cv = with_bullet(fact, "Built payment\nAPIs")
    cv["summary"] = claim("Payments backend engineer", fact, rust)

    checked = await check_cv(agent, token, number, cv)

    assert sorted(i["code"] for i in checked["issues"]) == [
        "invalid_value",
        "line_break",
    ]
    [facts] = [i for i in checked["issues"] if i["code"] == "invalid_value"]
    assert facts["message"] == (
        f"Факти не підтверджені: #{rust} — спершу користувач їх підтверджує."
    )
    await nothing_saved(agent, token, number, documents_dir)


async def test_check_cv_returns_the_keyword_coverage_of_the_text(
    agent: Agent,
) -> None:
    token = await taras(agent)
    number, fact = await ready(agent, token)
    analysis = {"score": 70, "summary": "S.", "keywords": ["payment APIs", "Kafka"]}
    data(
        await call(
            agent, token, "save_analysis", {"job_id": number, "analysis": analysis}
        )
    )

    checked = await check_cv(
        agent, token, number, with_bullet(fact, "Built payment APIs in [Place]")
    )

    assert checked["keywords"] == {
        "covered": ["payment APIs"],
        "missing": ["Kafka"],
        "percent": 50,
    }


async def test_check_cv_returns_the_gate_with_the_two_numbers_and_the_named_word(
    agent: Agent,
) -> None:
    token = await taras(agent)
    number, fact = await ready(agent, token)
    analysis = {
        "score": 70,
        "summary": "S.",
        "keywords": ["payment APIs", "Kafka"],
        "keyword_facts": {"payment APIs": [fact], "Kafka": [fact]},
    }
    data(
        await call(
            agent, token, "save_analysis", {"job_id": number, "analysis": analysis}
        )
    )

    checked = await check_cv(
        agent, token, number, with_bullet(fact, "Built payment APIs in [Place]")
    )

    assert checked["gate"] == {
        "status": "failed",
        "evidence_percent": 50,
        "evidence_missing": ["Kafka"],
        "coverage_percent": 50,
    }


async def test_check_cv_returns_the_must_have_coverage_by_the_facts_the_agent_names(
    agent: Agent,
) -> None:
    token = await taras(agent)
    number, fact = await ready(agent, token)
    kafka = await add_fact(agent, token, "skill", "Kafka")
    data(await call(agent, token, "confirm_facts", {"fact_ids": [kafka]}))
    data(
        await call(
            agent,
            token,
            "save_analysis",
            {
                "job_id": number,
                "analysis": {
                    "score": 70,
                    "summary": "S.",
                    "must_have": ["Python", "gRPC", "Rust"],
                },
            },
        )
    )

    checked = await check_cv(
        agent,
        token,
        number,
        with_bullet(fact, "Built payment APIs in [Place]"),
        must_have_facts=[
            {"item": "Python", "fact_ids": [fact], "kind": "fact"},
            {"item": "gRPC", "fact_ids": [fact], "kind": "analogue"},
            {"item": "Rust", "fact_ids": [kafka], "kind": "fact"},
            {"item": "Go", "fact_ids": [fact], "kind": "fact"},
        ],
    )

    assert checked["must_have_coverage"] == {
        "items": [
            {"item": "Python", "status": "covered", "fact_ids": [fact], "reason": None},
            {"item": "gRPC", "status": "analogue", "fact_ids": [fact], "reason": None},
            {
                "item": "Rust",
                "status": "missing",
                "fact_ids": [],
                "reason": f"Жоден рядок CV не спирається на факти [{kafka}].",
            },
        ],
        "unknown": ["Go"],
    }


async def test_check_cv_without_must_have_facts_marks_every_must_have_missing(
    agent: Agent,
) -> None:
    token = await taras(agent)
    number, fact = await ready(agent, token)
    data(
        await call(
            agent,
            token,
            "save_analysis",
            {
                "job_id": number,
                "analysis": {"score": 70, "summary": "S.", "must_have": ["Python"]},
            },
        )
    )

    checked = await check_cv(
        agent, token, number, with_bullet(fact, "Built payment APIs in [Place]")
    )

    assert checked["must_have_coverage"] == {
        "items": [
            {
                "item": "Python",
                "status": "missing",
                "fact_ids": [],
                "reason": "У must_have_facts немає запису для цього пункту.",
            }
        ],
        "unknown": [],
    }


async def test_check_cv_of_a_job_not_analysed_has_null_keywords(agent: Agent) -> None:
    token = await taras(agent)
    number, fact = await ready(agent, token)

    checked = await check_cv(agent, token, number, with_bullet(fact, "Worked [here]"))

    assert checked["keywords"] is None


async def test_check_cover_letter_reports_text_issues_and_saves_nothing(
    agent: Agent, documents_dir: Path
) -> None:
    token = await taras(agent)
    number, fact = await ready(agent, token)
    letter = letter_arguments(fact)
    letter["text"] = letter["text"].replace("Dear team", "Dear  team")

    checked = await check_letter(agent, token, number, letter)

    assert checked["passed"] is False
    assert [i["code"] for i in checked["issues"]] == ["double_space"]
    await nothing_saved(agent, token, number, documents_dir)


async def test_a_check_of_a_missing_job_is_a_tool_error(agent: Agent) -> None:
    token = await taras(agent)
    _, fact = await ready(agent, token)

    for name, arguments in (
        ("check_cv", {"job_id": 9, "cv": cv_arguments(fact)}),
        ("check_cover_letter", {"job_id": 9, **letter_arguments(fact)}),
    ):
        assert "Вакансію 9 не знайдено." in error_text(
            await call(agent, token, name, arguments)
        ), name


async def test_check_cv_of_clean_text_passes_and_leaves_no_trace(
    agent: Agent, documents_dir: Path
) -> None:
    token = await taras(agent)
    number, fact = await ready(agent, token)

    checked = await check_cv(agent, token, number, cv_arguments(fact))

    assert checked == {
        "passed": True,
        "issues": [],
        "keywords": None,
        "gate": {
            "status": "no_data",
            "evidence_percent": None,
            "evidence_missing": [],
            "coverage_percent": None,
        },
        "must_have_coverage": None,
    }
    await nothing_saved(agent, token, number, documents_dir)


async def test_check_cover_letter_of_clean_text_passes_and_leaves_no_trace(
    agent: Agent, documents_dir: Path
) -> None:
    token = await taras(agent)
    number, fact = await ready(agent, token)

    checked = await check_letter(agent, token, number, letter_arguments(fact))

    assert checked == {"passed": True, "issues": [], "keywords": None}
    await nothing_saved(agent, token, number, documents_dir)


async def test_a_cv_of_clean_text_but_two_pages_too_many_reports_the_pages_issue(
    agent: Agent, documents_dir: Path
) -> None:
    token = await taras(agent)
    number, fact = await ready(agent, token)
    cv = cv_arguments(fact)
    cv["sections"][0]["entries"] = [
        {
            "heading": claim(f"Engineer {i} · Acme", fact),
            "meta": claim("2021 - 2024", fact),
            "subtitle": None,
            "bullets": [claim(f"Built service {i} item {n}", fact) for n in range(12)],
        }
        for i in range(10)
    ]

    checked = await check_cv(agent, token, number, cv)

    assert [i["code"] for i in checked["issues"]] == ["pages"]
    await nothing_saved(agent, token, number, documents_dir)


# --- суворе збереження й один документ на вид ---------------------------------------------


async def test_a_cv_with_a_text_issue_is_a_tool_error_and_nothing_is_saved(
    agent: Agent, documents_dir: Path
) -> None:
    token = await taras(agent)
    number, fact = await ready(agent, token)

    result = await call(
        agent,
        token,
        "save_cv",
        {"job_id": number, "cv": with_bullet(fact, "Worked at [Company]")},
    )

    assert "[placeholder]" in error_text(result)
    await nothing_saved(agent, token, number, documents_dir)


async def test_a_letter_with_a_text_issue_is_a_tool_error_and_nothing_is_saved(
    agent: Agent, documents_dir: Path
) -> None:
    token = await taras(agent)
    number, fact = await ready(agent, token)
    letter = letter_arguments(fact)
    letter["text"] = letter["text"].replace("Dear team", "Dear\tteam")

    result = await call(agent, token, "save_cover_letter", {"job_id": number, **letter})

    assert "[line_break]" in error_text(result)
    await nothing_saved(agent, token, number, documents_dir)


async def test_a_second_cv_replaces_the_first_with_its_file_and_its_download_link(
    agent: Agent, documents_dir: Path
) -> None:
    token = await taras(agent)
    number, fact = await ready(agent, token)
    await save_cv(agent, token, number, cv_arguments(fact, "First"))
    [first_file] = stored_files(documents_dir)
    link = data(await call(agent, token, "get_document_download", {"document_id": 1}))

    saved = await save_cv(agent, token, number, cv_arguments(fact, "Second"))

    assert (saved["document_id"], saved["version"]) == (2, 2)
    listed = data(await call(agent, token, "list_documents", {"job_id": number}))
    assert [d["document_id"] for d in listed["documents"]] == [2]
    assert [f.name for f in stored_files(documents_dir)] != [first_file.name]
    assert len(stored_files(documents_dir)) == 1
    with pytest.raises(NotFound):
        await agent.container.document_downloads.redeem(link["url"].rsplit("/", 1)[1])
    gone = await call(agent, token, "get_document_download", {"document_id": 1})
    assert error_text(gone).endswith(": Документ 1 не знайдено.")


async def test_a_second_letter_replaces_the_first_and_the_cv_stays(
    agent: Agent, documents_dir: Path
) -> None:
    token = await taras(agent)
    number, fact = await ready(agent, token)
    await save_cv(agent, token, number, cv_arguments(fact))
    await save_letter(agent, token, number, letter_arguments(fact))

    saved = await save_letter(agent, token, number, letter_arguments(fact, 200))

    assert (saved["document_id"], saved["version"]) == (3, 2)
    listed = data(await call(agent, token, "list_documents", {"job_id": number}))
    assert [(d["document_id"], d["kind"]) for d in listed["documents"]] == [
        (3, "cl"),
        (1, "cv"),
    ]
    assert len(stored_files(documents_dir)) == 2


async def test_a_replacement_leaves_the_documents_of_other_jobs_and_users(
    agent: Agent, documents_dir: Path
) -> None:
    owner = await taras(agent)
    other = await katya(agent)
    number, fact = await ready(agent, owner)
    second_job = await seed(agent, "Another posting.")
    their_number, their_fact = await ready(agent, other, "katya@example.com")
    await save_cv(agent, owner, number, cv_arguments(fact))
    await save_cv(agent, owner, second_job, cv_arguments(fact))
    await save_cv(agent, other, their_number, cv_arguments(their_fact))

    await save_cv(agent, owner, number, cv_arguments(fact, "Replaced"))

    mine = data(await call(agent, owner, "list_documents", {"job_id": second_job}))
    theirs = data(await call(agent, other, "list_documents", {"job_id": their_number}))
    assert [d["document_id"] for d in mine["documents"]] == [2]
    assert [d["document_id"] for d in theirs["documents"]] == [1]
    assert len(stored_files(documents_dir)) == 3


# --- фото в шапці CV ---------------------------------------------------------------------


async def save_cv_with(
    agent: Agent, token: str, job: int, cv: dict[str, Any], photo_id: int | None
) -> Any:
    return await call(
        agent, token, "save_cv", {"job_id": job, "cv": cv, "photo_id": photo_id}
    )


async def photos_of(agent: Agent, token: str) -> dict[str, Any]:
    return data(await call(agent, token, "list_photos"))


async def test_the_cv_brief_offers_the_same_photos_as_list_photos(
    agent: Agent,
) -> None:
    token = await taras(agent)
    number, _ = await ready(agent, token)
    await add_photo(agent, "taras@example.com", "first")
    await add_photo(agent, "taras@example.com", "second")

    brief = data(await call(agent, token, "prepare_cv", {"job_id": number}))

    assert brief["photos"] == await photos_of(agent, token)
    assert brief["photos"]["suggested_photo_id"] == 2


async def test_a_cv_saved_with_a_photo_carries_it_and_marks_it_used(
    agent: Agent, documents_dir: Path
) -> None:
    token = await taras(agent)
    number, fact = await ready(agent, token)
    await add_photo(agent, "taras@example.com")
    await add_photo(agent, "taras@example.com")

    saved = data(await save_cv_with(agent, token, number, cv_arguments(fact), 1))

    assert saved["photo_id"] == 1
    assert saved["lint"]["passed"] is True
    listed = data(await call(agent, token, "list_documents", {"job_id": number}))
    assert [d["photo_id"] for d in listed["documents"]] == [1]
    photos = await photos_of(agent, token)
    assert photos["suggested_photo_id"] == 1
    used = {p["photo_id"]: p["last_used"] for p in photos["photos"]}
    assert used == {1: local_day(datetime.now(UTC)), 2: None}
    [file] = stored_files(documents_dir)
    assert file.read_bytes().startswith(b"%PDF")


async def test_a_cv_saved_with_null_photo_has_none(agent: Agent) -> None:
    token = await taras(agent)
    number, fact = await ready(agent, token)
    await add_photo(agent, "taras@example.com")

    saved = data(await save_cv_with(agent, token, number, cv_arguments(fact), None))

    assert saved["photo_id"] is None
    assert (await photos_of(agent, token))["photos"][0]["last_used"] is None


async def test_another_users_photo_is_a_tool_error_and_nothing_is_saved(
    agent: Agent, documents_dir: Path
) -> None:
    token = await taras(agent)
    number, fact = await ready(agent, token)
    await add_photo(agent, "katya@example.com")

    result = await save_cv_with(agent, token, number, cv_arguments(fact), 1)

    assert "Фото 1 не знайдено в профілі." in error_text(result)
    listed = data(await call(agent, token, "list_documents", {"job_id": number}))
    assert listed["documents"] == []
    assert stored_files(documents_dir) == []


async def test_deleting_the_photo_keeps_the_saved_cv_and_its_pdf(
    agent: Agent, documents_dir: Path
) -> None:
    token = await taras(agent)
    number, fact = await ready(agent, token)
    await add_photo(agent, "taras@example.com")
    await save_cv_with(agent, token, number, cv_arguments(fact), 1)
    [before] = stored_files(documents_dir)
    pdf = before.read_bytes()

    actor = Actor(
        user_id=UserId.parse(agent.user_ids["taras@example.com"]),
        channel=Channel.WEB,
        client_id="web",
        grant_id=None,
        scopes=frozenset(Scope),
        correlation_id="test",
    )
    await agent.container.photos.delete_photo(actor, 1)

    listed = data(await call(agent, token, "list_documents", {"job_id": number}))
    assert [d["photo_id"] for d in listed["documents"]] == [None]
    assert [f.read_bytes() for f in stored_files(documents_dir)] == [pdf]
    assert (await photos_of(agent, token))["photos"] == []


# --- одноразове посилання на PDF (get_document_download) ----------------------------------


async def stored_cv(agent: Agent, token: str, who: str = "taras@example.com") -> int:
    """Документ власника напряму в базі (без рендеру PDF): номер документа."""
    await update_profile(agent, token, FULL)
    number = await seed(agent, "Senior Python engineer. Remote.", who=who)
    user = UserId.parse(agent.user_ids[who])
    async with agent.container.unit_of_work() as tx:
        job = await tx.jobs.get(user, number)
        assert job is not None
        saved = await tx.documents.add(
            user,
            DocumentId(uuid4()),
            job.id,
            Cv(
                Claim("Senior Engineer", (1,)),
                Claim("Summary", (1,)),
                (CvSection(CvSectionName.SKILLS, (CvEntry(Claim("Python", (1,))),)),),
            ),
            datetime.now(UTC),
        )
        await tx.commit()
    return saved.number


async def test_get_document_download_is_listed_with_the_catalog_description(
    agent: Agent,
) -> None:
    token = await taras(agent)

    async with agent.authed(token) as authed:
        transport = streamable_http_client(PUBLIC, http_client=authed)
        async with Client(transport) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}

    assert "get_document_download" in tools
    assert tools["get_document_download"].description == (
        TOOLS / "get_document_download.md"
    ).read_text(encoding="utf-8")


async def test_get_document_download_gives_a_single_use_link_under_the_web_origin(
    agent: Agent,
) -> None:
    token = await taras(agent)
    document = await stored_cv(agent, token)

    link = data(
        await call(agent, token, "get_document_download", {"document_id": document})
    )

    assert set(link) == {"url", "file_name", "expires_at"}
    assert link["url"].startswith(f"{WEB}/api/documents/download/")
    assert len(link["url"]) >= len(f"{WEB}/api/documents/download/") + 43
    assert link["file_name"] == "Test_User_CV.pdf"


async def test_get_document_download_of_another_users_document_is_not_found(
    agent: Agent,
) -> None:
    owner = await taras(agent)
    other = await katya(agent)
    document = await stored_cv(agent, owner)

    result = await call(
        agent, other, "get_document_download", {"document_id": document}
    )

    assert error_text(result).endswith(f": Документ {document} не знайдено.")


async def test_get_document_download_of_a_missing_document_is_not_found(
    agent: Agent,
) -> None:
    token = await taras(agent)

    result = await call(agent, token, "get_document_download", {"document_id": 9})

    assert error_text(result).endswith(": Документ 9 не знайдено.")
