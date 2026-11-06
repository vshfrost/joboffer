"""Composition root: промпти перевіряються на старті, а не під час запиту."""

from pathlib import Path

import pytest

from application.ports.prompts import PromptKey, PromptsUnavailableError
from bootstrap.container import build_container
from bootstrap.settings import Settings

CATALOG = Path(__file__).resolve().parents[2] / "prompts"

TEST_DATABASE_URL = "postgresql+psycopg://app:secret-in-test@localhost:5432/app"


@pytest.fixture(autouse=True)
def _database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOBOFFER_DATABASE_URL", TEST_DATABASE_URL)


def test_container_serves_the_repository_prompts_by_default() -> None:
    container = build_container(Settings(environment="test"))

    assert container.prompts.get(PromptKey.MCP_INSTRUCTIONS) == (
        CATALOG / "mcp" / "instructions.md"
    ).read_text(encoding="utf-8")


def test_container_reads_prompts_from_the_configured_directory(
    tmp_path: Path,
) -> None:
    for key in PromptKey:
        path = tmp_path / f"{key.value}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("інші інструкції", encoding="utf-8")

    container = build_container(Settings(environment="test", prompts_dir=tmp_path))

    assert container.prompts.get(PromptKey.MCP_INSTRUCTIONS) == "інші інструкції"


def test_container_fails_at_startup_naming_the_missing_prompt_file(
    tmp_path: Path,
) -> None:
    with pytest.raises(PromptsUnavailableError, match=r"mcp/instructions\.md"):
        build_container(Settings(environment="test", prompts_dir=tmp_path))


def test_container_appends_the_next_step_tail_to_scenario_prompts() -> None:
    container = build_container(Settings(environment="test"))
    cv = (CATALOG / "requests" / "cv.md").read_text(encoding="utf-8")
    tail = (CATALOG / "scenarios" / "next_step.md").read_text(encoding="utf-8")

    assert container.prompts.get(PromptKey.REQUEST_CV) == f"{cv}\n\n{tail}"


def test_container_leaves_the_apply_prompt_without_a_tail() -> None:
    container = build_container(Settings(environment="test"))

    assert container.prompts.get(PromptKey.REQUEST_APPLY) == (
        CATALOG / "requests" / "apply.md"
    ).read_text(encoding="utf-8")
