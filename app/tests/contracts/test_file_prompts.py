"""Адаптер `FilePrompts`: читає `<корінь>/<область>/<імʼя>.md`, кешує на процес."""

from pathlib import Path

import pytest

from application.ports.prompts import PromptKey, PromptsUnavailableError
from infrastructure.prompts.catalog import FilePrompts

# Текст з кирилицею, апострофом, CRLF і без фінального переведення рядка:
# адаптер не нормалізує нічого.
TEXT = "Привіт, світе — ʼапостроф\r\nдругий рядок\n\nостанній"


def _write(root: Path, key: PromptKey, text: bytes) -> Path:
    path = root / f"{key.value}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text)
    return path


def _write_all(root: Path, text: bytes = TEXT.encode()) -> None:
    for key in PromptKey:
        _write(root, key, text)


def test_known_key_returns_the_file_text_byte_for_byte(tmp_path: Path) -> None:
    _write_all(tmp_path)

    prompts = FilePrompts.load(tmp_path)

    assert prompts.get(PromptKey.MCP_INSTRUCTIONS) == TEXT


def test_text_is_cached_for_the_process(tmp_path: Path) -> None:
    _write_all(tmp_path)
    prompts = FilePrompts.load(tmp_path)

    _write(tmp_path, PromptKey.MCP_INSTRUCTIONS, b"changed after load")

    assert prompts.get(PromptKey.MCP_INSTRUCTIONS) == TEXT


def test_missing_file_fails_at_load_and_names_the_file(tmp_path: Path) -> None:
    with pytest.raises(PromptsUnavailableError, match=r"mcp/instructions\.md"):
        FilePrompts.load(tmp_path)


def test_file_that_is_not_utf8_fails_at_load_and_names_the_file(
    tmp_path: Path,
) -> None:
    _write_all(tmp_path, b"\xff\xfe\x00broken")

    with pytest.raises(PromptsUnavailableError, match=r"mcp/instructions\.md"):
        FilePrompts.load(tmp_path)
