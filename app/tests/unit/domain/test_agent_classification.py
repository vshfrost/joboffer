"""Вид і назва агента за DCR-клієнтом: назва + хост redirect_uri."""

import pytest

from domain.agents.agent import AgentIdentity, AgentKind
from domain.agents.classification import classify_agent

CLIENT_ID = "11111111-1111-4111-8111-111111111111"
CLAUDE_AI = ("https://claude.ai/api/mcp/auth_callback",)
LOCALHOST = ("http://localhost:53682/callback",)


def classify(name: str | None, uris: tuple[str, ...]) -> AgentIdentity:
    return classify_agent(CLIENT_ID, name, uris)


def test_claude_ai_host_is_claude() -> None:
    assert classify("Claude", CLAUDE_AI) == AgentIdentity(AgentKind.CLAUDE, "Claude")


def test_claude_com_host_is_claude() -> None:
    uris = ("https://claude.com/api/mcp/auth_callback",)
    assert classify("Claude", uris) == AgentIdentity(AgentKind.CLAUDE, "Claude")


def test_claude_host_gives_claude_whatever_the_client_calls_itself() -> None:
    assert classify("My connector", CLAUDE_AI) == AgentIdentity(
        AgentKind.CLAUDE, "Claude"
    )


def test_claude_host_without_a_name_is_claude() -> None:
    assert classify(None, CLAUDE_AI) == AgentIdentity(AgentKind.CLAUDE, "Claude")


def test_subdomain_of_claude_ai_is_claude() -> None:
    uris = ("https://www.claude.ai/cb",)
    assert classify("Claude", uris) == AgentIdentity(AgentKind.CLAUDE, "Claude")


def test_lookalike_host_is_not_claude() -> None:
    uris = ("https://evilclaude.ai/cb",)
    assert classify("Mallory", uris) == AgentIdentity(AgentKind.OTHER, "Mallory")


def test_claude_host_with_a_code_name_is_not_claude() -> None:
    assert classify("VS Code", CLAUDE_AI) == AgentIdentity(AgentKind.OTHER, "VS Code")


def test_claude_code_by_name() -> None:
    assert classify("Claude Code", LOCALHOST) == AgentIdentity(
        AgentKind.CLAUDE_CODE, "Claude Code"
    )


def test_claude_code_name_is_case_insensitive_and_normalised() -> None:
    assert classify("claude CODE (my-laptop)", LOCALHOST) == AgentIdentity(
        AgentKind.CLAUDE_CODE, "Claude Code"
    )


def test_claude_code_on_the_claude_host_is_claude_code() -> None:
    assert classify("Claude Code", CLAUDE_AI) == AgentIdentity(
        AgentKind.CLAUDE_CODE, "Claude Code"
    )


def test_chatgpt_com_host_is_chatgpt() -> None:
    uris = ("https://chatgpt.com/connector_platform_oauth_redirect",)
    assert classify("ChatGPT", uris) == AgentIdentity(AgentKind.CHATGPT, "ChatGPT")


def test_openai_com_host_is_chatgpt() -> None:
    uris = ("https://platform.openai.com/apps-manage/oauth",)
    assert classify("Some app", uris) == AgentIdentity(AgentKind.CHATGPT, "ChatGPT")


def test_codex_by_name() -> None:
    assert classify("Codex", LOCALHOST) == AgentIdentity(AgentKind.CODEX, "Codex")


def test_codex_name_is_case_insensitive_and_normalised() -> None:
    assert classify("OpenAI CODEX CLI", LOCALHOST) == AgentIdentity(
        AgentKind.CODEX, "Codex"
    )


def test_codex_on_the_chatgpt_host_is_chatgpt() -> None:
    uris = ("https://chatgpt.com/cb",)
    assert classify("Codex", uris) == AgentIdentity(AgentKind.CHATGPT, "ChatGPT")


def test_unknown_client_keeps_its_name() -> None:
    assert classify("Cursor", LOCALHOST) == AgentIdentity(AgentKind.OTHER, "Cursor")


def test_other_name_is_trimmed_of_whitespace() -> None:
    assert classify("  Cursor \n", LOCALHOST) == AgentIdentity(
        AgentKind.OTHER, "Cursor"
    )


def test_other_name_is_cut_to_80_characters() -> None:
    assert classify("a" * 90, LOCALHOST) == AgentIdentity(AgentKind.OTHER, "a" * 80)


def test_other_name_of_exactly_80_characters_is_kept() -> None:
    assert classify("b" * 80, LOCALHOST) == AgentIdentity(AgentKind.OTHER, "b" * 80)


@pytest.mark.parametrize("name", [None, "", "   "])
def test_other_without_a_name_falls_back_to_the_client_id(name: str | None) -> None:
    assert classify(name, LOCALHOST) == AgentIdentity(AgentKind.OTHER, CLIENT_ID)


def test_malformed_redirect_does_not_break_classification() -> None:
    assert classify("Cursor", ("not a url",)) == AgentIdentity(
        AgentKind.OTHER, "Cursor"
    )
