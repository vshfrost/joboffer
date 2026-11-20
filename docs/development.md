# Розробка

## Команди

Потрібні [uv](https://docs.astral.sh/uv/) (Python 3.14 він поставить сам) і Docker.

```bash
cd app
uv sync --locked
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run lint-imports
uv run uvicorn --factory bootstrap.api:create_app --port 8797
```

З кореня репо:

```bash
scripts/check.sh       # швидка перевірка змін відносно origin/main (≤ ~2 хв): lint, типи, лише змінені тести
scripts/test-core.sh   # core-only тести в окремому venv без FastAPI і решти інфраструктури
scripts/ci.sh          # увесь CI однією командою; `ci.sh app|web|infra` — одна частина (так її запускає GitHub Actions, три job паралельно)
docker compose -f infra/compose.yaml up -d --build
```

Повний прогін (`scripts/ci.sh`) призначений для GitHub Actions; локально достатньо `scripts/check.sh` і тестів, яких
торкається зміна.

Dev-стек `infra/compose.yaml` (проєкт `joboffer-dev`, усі порти лише на `127.0.0.1`): `postgres`, `app` (`:8797`),
`agent` (`:8798`), `web` (Vite, `:5174`) і одноразові `sources` та `mailsync` (див. [sources.md](sources.md), [mail.md](mail.md)).
Пароль БД — у `infra/.env` (шаблон `infra/.env.example`), файл не комітиться.

## Web-клієнт

`web/` — React SPA зі своєю гексагональною розкладкою (`src/{domain,application,ports,infrastructure,ui,bootstrap}`);
межі стереже ESLint (`eslint-plugin-boundaries`): React і TanStack — лише в `ui`/`bootstrap`, `fetch` — лише в
`infrastructure`. npm запускається в Docker (`node:24.21.0-alpine`) через `scripts/web.sh`:

```bash
scripts/web.sh ci              # залежності строго за web/package-lock.json
scripts/web.sh run lint        # ESLint + межі шарів
scripts/web.sh run build       # tsc --noEmit + vite build (web/dist, base /)
scripts/web.sh run test        # Vitest
scripts/web.sh run dev         # http://localhost:5174/
```

Нова залежність: `scripts/web.sh install --save-exact <пакет>@<версія>` (версія ≥14 днів від релізу).

UI — Tailwind CSS 4 і компоненти в стилі shadcn/ui (Radix, class-variance-authority) з темою Pine:
токени лежать лише в `web/src/ui/theme.css`, їх звіряє `theme.test.ts` з дизайн-системою; Inter — локальні WOFF2
(`@fontsource-variable/inter`). Нові кольори, радіуси й відступи спершу додаються до дизайн-системи.
Бренд — `web/public/brand/`, еталон лого — [design/](design/) (референс, не в збірці).

## База даних

PostgreSQL через async SQLAlchemy + psycopg 3. Адреса — `JOBOFFER_DATABASE_URL`
(`postgresql+psycopg://user:password@host:5432/db`); у compose її збирає `infra/.env` (шаблон `.env.example`).

- ORM-таблиці — у `app/infrastructure/db/<контекст>/tables.py`, від `infrastructure.db.base.Base`.
- Транзакція use case — порт `application/ports/unit_of_work.py`, реалізація `SqlAlchemyUnitOfWork`.
- Міграції — `app/infrastructure/db/migrations/versions/`, нумерація послідовна (`0002_…`), тіло пишеться вручну;
  збіг зі схемою перевіряє `test_models_match_migrations`, одну голову — `test_single_head`.
- Застосувати: `cd app && JOBOFFER_DATABASE_URL=… uv run python -m bootstrap.migrate`
  (`alembic upgrade` навмисно не працює: оточення читає лише bootstrap). Контейнер робить це перед стартом.
- Integration-тести піднімають Postgres через testcontainers (потрібен Docker).
