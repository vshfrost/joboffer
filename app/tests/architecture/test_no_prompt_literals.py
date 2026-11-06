"""Текст промптів лежить у `app/prompts/`, а не в Python.

Правило (документація для людей і для тесту): у `domain`, `application`, `infrastructure`
і `bootstrap` жоден рядковий літерал, що не є docstring, не може бути:
  - довшим за 160 символів, або
  - багаторядковим (містить переведення рядка) і довшим за 80 символів.
Тести правилом не охоплені. Довгий текст для моделі — це файл `app/prompts/<область>/<імʼя>.md`
за ключем `PromptKey`; шаблони (PDF, HTML) — `app/templates/…`.
"""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LAYERS = ("domain", "application", "infrastructure", "bootstrap")

MAX_LITERAL = 160
MAX_MULTILINE_LITERAL = 80

PLANTED_PROMPT = (
    "You are a careful recruiter. Read the job posting below and rate how well the "
    "candidate matches it, then explain each gap in one short sentence for the candidate. "
    "Never invent facts that are not in the confirmed list."
)


def _docstring_nodes(tree: ast.Module) -> set[int]:
    ids = set()
    for node in ast.walk(tree):
        if isinstance(
            node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
        ):
            first = node.body[0] if node.body else None
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                ids.add(id(first.value))
    return ids


def find_prompt_like_literals(
    root: Path, layers: tuple[str, ...] = LAYERS
) -> list[str]:
    found = []
    for layer in layers:
        for path in sorted((root / layer).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            docstrings = _docstring_nodes(tree)
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                    continue
                if id(node) in docstrings:
                    continue
                size = len(node.value)
                too_long = size > MAX_LITERAL
                too_long_multiline = "\n" in node.value and size > MAX_MULTILINE_LITERAL
                if too_long or too_long_multiline:
                    found.append(
                        f"{path.relative_to(root)}:{node.lineno}: {size} символів"
                    )
    return found


def test_no_prompt_like_literals_in_the_app() -> None:
    assert find_prompt_like_literals(ROOT) == [], (
        "Схоже на промпт у коді — винеси в app/prompts/:"
    )


@pytest.mark.parametrize("layer", ["domain", "application"])
def test_planted_long_literal_is_caught_in_core(tmp_path: Path, layer: str) -> None:
    module = tmp_path / layer / "planted.py"
    module.parent.mkdir()
    module.write_text(f"RULES = {PLANTED_PROMPT!r}\n", encoding="utf-8")

    assert find_prompt_like_literals(tmp_path, (layer,)) == [
        f"{layer}/planted.py:1: {len(PLANTED_PROMPT)} символів"
    ]


def test_planted_multiline_literal_is_caught(tmp_path: Path) -> None:
    text = "Rate the job posting.\nUse only the confirmed facts of the candidate.\nAnswer in Ukrainian."
    module = tmp_path / "application" / "planted.py"
    module.parent.mkdir()
    module.write_text(f"RULES = {text!r}\n", encoding="utf-8")

    assert len(find_prompt_like_literals(tmp_path, ("application",))) == 1


def test_docstrings_and_short_strings_are_allowed(tmp_path: Path) -> None:
    module = tmp_path / "application" / "fine.py"
    module.parent.mkdir()
    module.write_text(
        f'"""{PLANTED_PROMPT}"""\n\n\ndef f() -> str:\n    """{PLANTED_PROMPT}"""\n    return "Невірний email або пароль"\n',
        encoding="utf-8",
    )

    assert find_prompt_like_literals(tmp_path, ("application",)) == []
