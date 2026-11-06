# syntax=docker/dockerfile:1
# Образ backend (app/). Контекст збірки — корінь репо.
FROM ghcr.io/astral-sh/uv:0.12.23 AS uv

FROM python:3.14.8-slim-trixie AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /src
# Спершу лише залежності — шар кешується, доки не змінився uv.lock.
COPY app/pyproject.toml app/uv.lock app/.python-version ./
RUN uv sync --locked --no-default-groups --no-install-project
COPY app/domain domain
COPY app/application application
COPY app/infrastructure infrastructure
COPY app/bootstrap bootstrap
RUN uv sync --locked --no-default-groups --no-editable

FROM python:3.14.8-slim-trixie
# WeasyPrint (рендер PDF): pango + harfbuzz і шрифти, які він вбудовує в PDF.
# poppler-utils: pdftotext, другий парсер PDF для ATS-lint.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core \
        poppler-utils \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --system --uid 10001 --no-create-home joboffer
# PDF версій документів: тека належить joboffer, тож іменований volume над нею теж.
RUN mkdir -p /data/documents && chown joboffer /data/documents
COPY --from=build /opt/venv /opt/venv
# Промпти — файли, не Python-пакет: лежать поруч із venv, шлях задає JOBOFFER_PROMPTS_DIR.
COPY app/prompts /app/prompts
# HTML-шаблони (логін-гейт агента, PDF документів) — так само файли поруч із venv.
COPY app/templates /app/templates
# XDG_CACHE_HOME: у системного користувача без домашньої теки fontconfig інакше не має де кешувати шрифти.
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    JOBOFFER_PROMPTS_DIR=/app/prompts \
    JOBOFFER_TEMPLATES_DIR=/app/templates \
    JOBOFFER_DOCUMENTS_DIR=/data/documents \
    XDG_CACHE_HOME=/tmp
USER joboffer
EXPOSE 8797 8798
# Міграції — перед стартом: схема завжди відповідає коду образу.
CMD ["sh", "-c", "python -m bootstrap.migrate && exec uvicorn --factory bootstrap.api:create_app --host 0.0.0.0 --port 8797"]
