#!/usr/bin/env bash
# Core-only тести в окремому venv без інфраструктурних пакетів.
# Встановлюється лише група `core-test`; залежності проєкту (FastAPI, SQLAlchemy, MCP, Redis…)
# і група `dev` — ні. Аргументи передаються в pytest.
set -euo pipefail
cd "$(dirname "$0")/../app"

export UV_PROJECT_ENVIRONMENT=.venv-core
uv sync --locked --only-group core-test --quiet

# Середовище справді чисте: жоден інфраструктурний пакет не імпортується.
uv run --no-sync python - <<'PY'
import importlib.util
infra = ["fastapi", "starlette", "pydantic", "pydantic_settings", "uvicorn", "sqlalchemy",
         "alembic", "psycopg", "asyncmy", "redis", "mcp", "authlib", "joserfc", "itsdangerous", "httpx2", "argon2", "aiokafka", "confluent_kafka",
         "weasyprint", "pypdf", "PIL", "grimp", "importlinter"]
present = [name for name in infra if importlib.util.find_spec(name) is not None]
if present:
    raise SystemExit(f"core-only venv містить інфраструктурні пакети: {present}")
print("core-only venv: інфраструктурних пакетів нема")
PY

uv run --no-sync pytest tests/unit tests/acceptance "$@"
