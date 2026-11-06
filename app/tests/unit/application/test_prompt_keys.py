"""Ключі промптів — типізований набір, значення якого безпечно мапиться на файл."""

import re

from application.ports.prompts import PromptKey

AREA_AND_NAME = re.compile(r"^[a-z0-9_-]+(/[a-z0-9_-]+)+$")


def test_every_key_is_an_area_a_name_and_optional_subfolders() -> None:
    bad = [key.value for key in PromptKey if not AREA_AND_NAME.fullmatch(key.value)]
    assert bad == []


def test_mcp_instructions_key_points_to_the_mcp_area() -> None:
    assert PromptKey.MCP_INSTRUCTIONS.value == "mcp/instructions"
