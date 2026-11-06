"""Межі імпортів між шарами.

Дві незалежні перевірки:
- import-linter (контракти в pyproject.toml): напрямок шарів і заборонені фреймворки,
  включно з транзитивними ланцюжками та імпортами під TYPE_CHECKING;
- allowlist по AST: core може імпортувати лише stdlib (без IO-модулів) і дозволені шари.
  Allowlist ловить і ті бібліотеки, яких немає в денайлисті import-linter.
"""

import ast
import sys
from pathlib import Path

import pytest
from importlinter.cli import EXIT_STATUS_SUCCESS, lint_imports

ROOT = Path(__file__).resolve().parents[2]

# Шари, які core-шар може імпортувати (разом із самим собою).
CORE_ALLOWED_LAYERS = {
    "domain": {"domain"},
    "application": {"domain", "application"},
}

# Stdlib-модулі з IO, оточенням, годинником чи випадковістю — у core заборонені.
# Час і ID приходять через порти (Clock, IdGenerator), логування — справа infrastructure.
FORBIDDEN_STDLIB = {
    "os", "sys", "io", "pathlib", "shutil", "tempfile", "glob", "fileinput",
    "socket", "ssl", "http", "urllib", "smtplib", "email",
    "subprocess", "threading", "multiprocessing", "concurrent", "asyncio",
    "sqlite3", "dbm", "shelve", "pickle",
    "random", "secrets", "time", "logging", "importlib", "builtins",
}  # fmt: skip


def _imported_top_levels(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):  # walk заходить і в `if TYPE_CHECKING:` блоки
        if isinstance(node, ast.Import):
            found += [(node.lineno, alias.name.split(".")[0]) for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.append((node.lineno, node.module.split(".")[0]))
    return found


def test_import_linter_contracts_kept() -> None:
    config = str(ROOT / "pyproject.toml")
    assert lint_imports(config_filename=config, no_cache=True) == EXIT_STATUS_SUCCESS


@pytest.mark.parametrize("layer", sorted(CORE_ALLOWED_LAYERS))
def test_core_imports_only_allowlisted_modules(layer: str) -> None:
    allowed_stdlib = (sys.stdlib_module_names - FORBIDDEN_STDLIB) | {"__future__"}
    allowed = allowed_stdlib | CORE_ALLOWED_LAYERS[layer]
    violations = [
        f"{path.relative_to(ROOT)}:{line}: {module}"
        for path in sorted((ROOT / layer).rglob("*.py"))
        for line, module in _imported_top_levels(path)
        if module not in allowed
    ]
    assert violations == [], "Заборонені імпорти в core:\n" + "\n".join(violations)


def test_no_relative_imports_in_core() -> None:
    # Відносні імпорти обходили б allowlist вище (`from .. import x`), тож у core їх нема.
    violations = [
        f"{path.relative_to(ROOT)}:{node.lineno}"
        for layer in CORE_ALLOWED_LAYERS
        for path in sorted((ROOT / layer).rglob("*.py"))
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.ImportFrom) and node.level > 0
    ]
    assert violations == []
