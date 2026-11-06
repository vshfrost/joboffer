#!/usr/bin/env bash
# CI-прогін. Той самий скрипт запускається локально і в GitHub Actions.
#   scripts/ci.sh            → усе по черзі (app, web, infra)
#   scripts/ci.sh app|web|infra → одна частина; у GitHub Actions кожна йде окремим паралельним job
# Секретів не потребує; потрібні uv (для app) і Docker (для web та infra).
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"

step() { printf '\n\033[1m▶ %s\033[0m\n' "$*"; }

app() {
cd "$repo/app"

step "app: залежності (строго за uv.lock)"
uv sync --locked

step "app: ruff lint + format"
uv run ruff check .
uv run ruff format --check .

step "app: mypy --strict"
uv run mypy

step "app: межі шарів (import-linter)"
uv run lint-imports

step "app: core-only тести (без інфраструктурних пакетів)"
"$repo/scripts/test-core.sh" -q

step "app: усі тести + покриття (рядки+гілки, поріг 80%)"
# Паралельно (xdist): кожен воркер піднімає власний Postgres (див. tests/integration/conftest.py).
# pytest-cov збирає покриття з воркерів; звіт і поріг — з [tool.coverage] у pyproject.toml.
uv run coverage erase
uv run pytest -q -n auto --maxprocesses 4 --dist loadscope --cov --cov-report=
uv run coverage report

}

web() {
cd "$repo"

step "web: залежності (строго за package-lock.json)"
scripts/web.sh ci --no-audit --no-fund

step "web: lint + межі шарів"
scripts/web.sh run lint

step "web: typecheck + build"
scripts/web.sh run build

step "web: воркер ALTCHA — окремий файл свого origin (CSP не дозволяє data:-воркери)"
compgen -G "web/dist/assets/worker-*.js" >/dev/null || { echo "у web/dist/assets нема worker-*.js" >&2; exit 1; }
if grep -lq "data:text/javascript" web/dist/assets/*.js; then
  echo "у бандлі є data:text/javascript — воркер вбудовано замість окремого файлу" >&2
  exit 1
fi

step "web: тести (Vitest) + покриття профілю, вакансій, подач, тріажу, аналізу, пошти, відповідей, джерел і реєстрації (поріг 100 %)"
# Без --maxWorkers Vitest бере ядра мінус одне: на 2-vCPU раннері це один воркер і вільне ядро.
scripts/web.sh run test -- --coverage --maxWorkers=100%

}

infra() {
cd "$repo"

step "infra: compose-конфіг валідний"
# Placeholder лише для інтерполяції: справжній пароль — в infra/.env, у CI він не потрібен.
JOBOFFER_POSTGRES_PASSWORD=ci-config-check docker compose -f infra/compose.yaml config -q

step "infra: без JOBOFFER_POSTGRES_PASSWORD compose-конфіг падає з підказкою"
# --env-file /dev/null: результат не залежить від локального infra/.env.
if out="$(env -u JOBOFFER_POSTGRES_PASSWORD docker compose --env-file /dev/null -f infra/compose.yaml config -q 2>&1)"; then
  echo "compose config пройшов без JOBOFFER_POSTGRES_PASSWORD" >&2
  exit 1
fi
grep -qF "задай JOBOFFER_POSTGRES_PASSWORD в infra/.env" <<<"$out" || {
  echo "у помилці compose нема підказки про JOBOFFER_POSTGRES_PASSWORD:" >&2
  echo "$out" >&2
  exit 1
}

step "infra: прод-compose валідний із шаблоном змінних і падає без кожної обовʼязкової змінної"
docker compose -f infra/compose.prod.yaml --env-file infra/.env.prod.example config -q
# Решта обовʼязкових змінних задана, тож у помилці лишається рівно одна підказка. --env-file /dev/null:
# результат не залежить від локальних файлів.
required=(JOBOFFER_POSTGRES_PASSWORD JOBOFFER_WEB_PUBLIC_URL JOBOFFER_AGENT_ALLOWED_HOSTS JOBOFFER_MAIL_ADDRESS)
for missing in "${required[@]}"; do
  if out="$(
    export JOBOFFER_POSTGRES_PASSWORD=ci-config-check JOBOFFER_WEB_PUBLIC_URL=https://jobs.example.com \
      JOBOFFER_AGENT_ALLOWED_HOSTS='["jobs.example.com"]' JOBOFFER_MAIL_ADDRESS=mailroom@example.com
    unset "$missing"
    docker compose --env-file /dev/null -f infra/compose.prod.yaml config -q 2>&1
  )"; then
    echo "прод-compose config пройшов без $missing" >&2
    exit 1
  fi
  grep -qF "задай $missing в /etc/joboffer/env" <<<"$out" || {
    echo "у помилці прод-compose нема підказки про $missing:" >&2
    echo "$out" >&2
    exit 1
  }
done

step "infra: прод-compose дотримується контракту (імʼя проєкту, порти лише на 127.0.0.1, том БД, cloudflared запінений)"
docker compose --profile sources -f infra/compose.prod.yaml --env-file infra/.env.prod.example config --format json | python3 -c '
import json, re, sys
cfg = json.load(sys.stdin)
svc = cfg["services"]
assert cfg["name"] == "joboffer", cfg["name"]
assert set(svc) == {"postgres", "app", "agent", "web", "cloudflared", "sources"}, set(svc)
published = {n: [(p["host_ip"], p["published"], p["target"]) for p in s.get("ports", [])] for n, s in svc.items()}
assert published == {
    "postgres": [], "app": [("127.0.0.1", "8797", 8797)], "agent": [("127.0.0.1", "8798", 8798)],
    "web": [("127.0.0.1", "8799", 8080)], "cloudflared": [], "sources": [],
}, published
assert svc["sources"]["profiles"] == ["sources"]
assert cfg["volumes"]["postgres-data"]["name"] == "joboffer-pgdata"
assert re.fullmatch(r"cloudflare/cloudflared:\d{4}\.\d+\.\d+", svc["cloudflared"]["image"]), svc["cloudflared"]["image"]
assert svc["cloudflared"]["command"] == ["tunnel", "--no-autoupdate", "run"]
for name in ("postgres", "app", "agent", "web", "cloudflared"):
    assert svc[name]["restart"] == "unless-stopped", name
env = svc["app"]["environment"]
assert (env["JOBOFFER_ENVIRONMENT"], env["JOBOFFER_COOKIE_SECURE"], env["JOBOFFER_SIGNUP_MODE"]) == ("prod", "true", "invite")
assert (env["JOBOFFER_CLIENT_IP_HEADER"], env["JOBOFFER_TRUSTED_PROXIES"]) == ("cf-connecting-ip", "1")
'

step "infra: mailsync — одноразовий сервіс синку пошти (профіль mail, лише gmail.env, без токена gmail.send)"
# gmail.env у CI нема; compose різних версій по-різному віддає env_file у config (v2.38 на раннері прибирає його
# навіть з --no-env-resolution), тому підставляємо існуючий тимчасовий файл із маркерною змінною і дивимось,
# що вона потрапила в environment лише mailsync. Типовий шлях і required: false — прямо в compose.prod.yaml.
docker compose version
gmail_env="$(mktemp)"
trap 'rm -f "$gmail_env"' EXIT
echo "JOBOFFER_GMAIL_CI_MARKER=1" >"$gmail_env"
grep -qzF 'path: ${JOBOFFER_GMAIL_ENV_FILE:-/etc/joboffer/gmail.env}
        required: false' infra/compose.prod.yaml || { echo "у compose.prod.yaml нема env_file /etc/joboffer/gmail.env з required: false" >&2; exit 1; }
default_set="$(docker compose -f infra/compose.prod.yaml --env-file infra/.env.prod.example config --services)"
grep -qx "mailsync" <<<"$default_set" && { echo "mailsync потрапляє в набір сервісів за замовчуванням (без --profile mail)" >&2; exit 1; }
JOBOFFER_GMAIL_ENV_FILE="$gmail_env" docker compose --profile mail -f infra/compose.prod.yaml --env-file infra/.env.prod.example config --format json | python3 -c '
import json, sys
svc = json.load(sys.stdin)["services"]
m = svc["mailsync"]
assert m["profiles"] == ["mail"], m.get("profiles")
assert not m.get("ports"), m.get("ports")
assert m["command"] == ["python", "-m", "bootstrap.sync_mail"], m["command"]
assert m["restart"] == "no", m["restart"]
assert m["image"] == "joboffer-app:prod", m["image"]
assert [n for n, s in svc.items() if "JOBOFFER_GMAIL_CI_MARKER" in s.get("environment", {})] == ["mailsync"], "gmail.env лише в mailsync"
env = m["environment"]
assert set(env) == {"JOBOFFER_ENVIRONMENT", "JOBOFFER_DATABASE_URL", "JOBOFFER_MAIL_ADDRESS", "JOBOFFER_GMAIL_CI_MARKER"}, sorted(env)
assert env["JOBOFFER_MAIL_ADDRESS"] == "mailroom@example.com", env["JOBOFFER_MAIL_ADDRESS"]
assert m["depends_on"]["app"]["condition"] == "service_healthy", m["depends_on"]
'

step "infra: triage — одноразовий сервіс тріажу за правилами (профіль triage, без секретів і портів)"
default_set="$(docker compose -f infra/compose.prod.yaml --env-file infra/.env.prod.example config --services)"
grep -qx "triage" <<<"$default_set" && { echo "triage потрапляє в набір сервісів за замовчуванням (без --profile triage)" >&2; exit 1; }
docker compose --profile triage -f infra/compose.prod.yaml --env-file infra/.env.prod.example config --format json | python3 -c '
import json, sys
t = json.load(sys.stdin)["services"]["triage"]
assert t["profiles"] == ["triage"], t.get("profiles")
assert not t.get("ports"), t.get("ports")
assert t["command"] == ["python", "-m", "bootstrap.auto_triage"], t["command"]
assert t["restart"] == "no", t["restart"]
assert t["image"] == "joboffer-app:prod", t["image"]
assert set(t["environment"]) == {"JOBOFFER_ENVIRONMENT", "JOBOFFER_DATABASE_URL"}, sorted(t["environment"])
assert t["depends_on"]["app"]["condition"] == "service_healthy", t["depends_on"]
'

step "infra: Caddyfile веба валідний"
docker run --rm -v "$repo/infra/web/Caddyfile:/etc/caddy/Caddyfile:ro" caddy:2.11.7-alpine \
  caddy validate --config /etc/caddy/Caddyfile

step "infra: образи app і web збираються"
docker build -q -f infra/docker/app.Dockerfile -t joboffer-app:ci .
docker build -q -f infra/docker/web.Dockerfile -t joboffer-web:ci .

step "infra: образ web містить статичні файли бренду (web/public → /srv/app/brand)"
# Без них Caddy віддає index.html замість логотипа й фавіконів (SPA-фолбек).
for f in logo.svg favicon.svg favicon.ico; do
  docker run --rm --entrypoint ls joboffer-web:ci "/srv/app/brand/$f" >/dev/null 2>&1 || {
    echo "в образі web нема /srv/app/brand/$f (web/public не потрапив у збірку)" >&2
    exit 1
  }
done

step "infra: образ web містить логотипи агентів (web/public/agents → /srv/app/agents)"
for f in claude.svg claudecode.svg openai.svg codex.svg README.md; do
  docker run --rm --entrypoint ls joboffer-web:ci "/srv/app/agents/$f" >/dev/null 2>&1 || {
    echo "в образі web нема /srv/app/agents/$f (web/public/agents не потрапив у збірку)" >&2
    exit 1
  }
done

step "infra: образ app рендерить PDF (pango, шрифти, шаблони)"
# Справжній рендер у фінальному образі: без системних бібліотек WeasyPrint падає на імпорті.
docker run --rm --entrypoint python joboffer-app:ci -c \
  "from pathlib import Path; from weasyprint import HTML; pdf = HTML(string='<p>ok</p>').write_pdf(); assert pdf.startswith(b'%PDF'); assert Path('/app/templates/pdf/cv.html').is_file(); assert Path('/data/documents').is_dir()"

step "infra: образ app містить промпти (composition root читає їх на старті)"
# Адреса БД — заглушка: engine лінивий, з'єднання не відкривається.
docker run --rm -e JOBOFFER_DATABASE_URL=postgresql+psycopg://ci:ci@localhost:5432/ci \
  --entrypoint python joboffer-app:ci -c \
  "from bootstrap.container import build_container; from bootstrap.settings import Settings; build_container(Settings())"
}

case "${1:-all}" in
  app) app ;;
  web) web ;;
  infra) infra ;;
  all) app; web; infra ;;
  *) echo "використання: scripts/ci.sh [app|web|infra]" >&2; exit 2 ;;
esac

printf '\n\033[1;32m✔ CI пройдено (%s)\033[0m\n' "${1:-all}"
