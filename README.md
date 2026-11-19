# joboffer

Сервіс генерації CV та Cover Letter для подачі на вакансію. Claude думає (читає CV і вакансії, оцінює, пише документи)
через MCP, joboffer зберігає дані й перевіряє їх: вакансії, факти з CV, аналіз, PDF документів, подачі, пошта.
Бекенд — Python (FastAPI, PostgreSQL), клієнт — React SPA.

## Швидкий старт

Потрібні [uv](https://docs.astral.sh/uv/) і Docker.

```bash
cd app && uv sync --locked && uv run pytest        # тести бекенда
scripts/web.sh ci && scripts/web.sh run test       # залежності й тести клієнта
docker compose -f infra/compose.yaml up -d --build # dev-стек; пароль БД — infra/.env (шаблон infra/.env.example)
```

Веб — `http://localhost:5174/`, API — `127.0.0.1:8797`, агент (MCP) — `http://localhost:5174/mcp`.
Створити користувача: `docker compose -f infra/compose.yaml exec app python -m bootstrap.create_user --email … --name …`.

## Документація

Повний опис — у [docs/](docs/README.md): [архітектура](docs/architecture.md), [розробка](docs/development.md),
[документи й фото](docs/documents.md), [джерела й тріаж](docs/sources.md), [пошта](docs/mail.md),
[вхід і агент](docs/auth.md), [прод](docs/deploy.md). Про вразливості — [SECURITY.md](SECURITY.md).
