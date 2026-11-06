"""Налаштування лише в bootstrap і жодних модульних синглтонів."""

import ast
from collections.abc import Iterator
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LAYERS = ("domain", "application", "infrastructure", "bootstrap")

# Звідки дозволено читати оточення / .env.
ENV_ALLOWED_LAYER = "bootstrap"
ENV_MODULES = {"pydantic_settings", "dotenv"}
ENV_ATTRIBUTES = {"environ", "getenv", "environb"}

# Виклики, результат яких не можна зберігати в змінній модуля: це stateful-обʼєкти
# на процес (застосунок, налаштування, пули й сесії БД, клієнти Redis).
SINGLETON_FACTORIES = {
    "create_app", "FastAPI", "Settings", "build_container", "Container",
    "create_engine", "create_async_engine", "sessionmaker", "async_sessionmaker",
    "Session", "AsyncSession", "Redis", "from_url",
}  # fmt: skip
# Прихований глобальний користувач заборонений: Actor передається явно.
FORBIDDEN_GLOBAL_NAMES = {"current_user", "current_actor", "actor", "user"}


def _modules(layer: str) -> Iterator[tuple[Path, ast.Module]]:
    for path in sorted((ROOT / layer).rglob("*.py")):
        yield path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _call_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            return func.attr
    return None


def test_environment_is_read_only_in_bootstrap() -> None:
    violations = []
    for layer in LAYERS:
        if layer == ENV_ALLOWED_LAYER:
            continue
        for path, tree in _modules(layer):
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    bad = [
                        a.name
                        for a in node.names
                        if a.name.split(".")[0] in ENV_MODULES
                    ]
                elif isinstance(node, ast.ImportFrom):
                    top = (node.module or "").split(".")[0]
                    names = {a.name for a in node.names}
                    bad = (
                        [top] if top in ENV_MODULES else sorted(names & ENV_ATTRIBUTES)
                    )
                elif isinstance(node, ast.Attribute) and node.attr in ENV_ATTRIBUTES:
                    bad = [node.attr]
                else:
                    continue
                if bad:
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno}: {bad}")
    assert violations == [], "Оточення читається поза bootstrap:\n" + "\n".join(
        violations
    )


def test_no_module_level_singletons() -> None:
    violations = []
    for layer in LAYERS:
        for path, tree in _modules(layer):
            for node in tree.body:  # лише верхній рівень модуля
                if isinstance(node, ast.Assign):
                    targets, value = node.targets, node.value
                elif isinstance(node, ast.AnnAssign) and node.value is not None:
                    targets, value = [node.target], node.value
                else:
                    continue
                names = {t.id for t in targets if isinstance(t, ast.Name)}
                where = f"{path.relative_to(ROOT)}:{node.lineno}"
                if _call_name(value) in SINGLETON_FACTORIES:
                    violations.append(
                        f"{where}: {sorted(names)} = {_call_name(value)}(...)"
                    )
                if names & FORBIDDEN_GLOBAL_NAMES:
                    violations.append(
                        f"{where}: глобальний {sorted(names & FORBIDDEN_GLOBAL_NAMES)}"
                    )
    assert violations == [], "Модульні синглтони:\n" + "\n".join(violations)
