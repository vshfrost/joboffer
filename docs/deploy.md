# Прод

Стек `infra/compose.prod.yaml` (проєкт `joboffer`) назовні відкритий лише через Cloudflare Tunnel (сервіс `cloudflared`).
Змінні — файл `/etc/joboffer/env` (шаблон з усіма змінними й коментарями: `infra/.env.prod.example`; значення вписує
оператор, у git їх нема). `JOBOFFER_WEB_PUBLIC_URL`, `JOBOFFER_AGENT_ALLOWED_HOSTS` і `JOBOFFER_MAIL_ADDRESS` обовʼязкові:
без них compose не стартує, типових значень нема.

```bash
docker compose -f infra/compose.prod.yaml --env-file /etc/joboffer/env up -d --build
docker compose -f infra/compose.prod.yaml --env-file /etc/joboffer/env run --rm sources   # прогін джерел вакансій
docker compose -f infra/compose.prod.yaml --env-file /etc/joboffer/env --profile mail run --rm mailsync   # синк пошти
docker compose -f infra/compose.prod.yaml --env-file /etc/joboffer/env --profile triage run --rm triage   # тріаж за правилами без LLM
```

## Сервіси

- `postgres` (том `joboffer-pgdata`), `app` (`127.0.0.1:8797`), `agent` (`127.0.0.1:8798`), `web` (Caddy,
  `127.0.0.1:8799` → контейнер `:8080`), `cloudflared` (образ запінено на точну версію, портів не публікує).
- Одноразові сервіси, з `up` не стартують: `sources` (профіль `sources`, див. [sources.md](sources.md)), `triage` (профіль
  `triage`: `python -m bootstrap.auto_triage` — тріаж вакансій за ключовими словами, профілем і підтвердженими фактами
  без LLM і без ключів; `--report` лише читає: порівняння з повними аналізами й розподіл вердиктів; рядки `agent` не
  перезаписує) та `mailsync` (профіль `mail`; Gmail-доступ на читання лише з `/etc/joboffer/gmail.env`, поза репо,
  див. [mail.md](mail.md)). Усі, крім `sources`, `triage` і `mailsync`, мають `restart: unless-stopped`.
- PDF документів: тека хоста `/srv/joboffer/documents` (uid 10001, права 0700; інший шлях — `JOBOFFER_DOCUMENTS_HOST_DIR`)
  монтується в `/data/documents`: агент пише, app читає.
- Фіксовано в compose: `JOBOFFER_ENVIRONMENT=prod`, `COOKIE_SECURE=true`, `TRUSTED_PROXIES=1`,
  `CLIENT_IP_HEADER=cf-connecting-ip` (для `app` і `agent`), `SIGNUP_MODE=invite` (для `app`); публічну адресу,
  дозволені Host-и й скриньку застосунку задає оператор в env-файлі.

## Змінні оточення

Лише імена; значення вписує оператор у `/etc/joboffer/env` (або `/etc/joboffer/gmail.env` для `mailsync`).

| Змінна | Де | Примітка |
|---|---|---|
| `JOBOFFER_POSTGRES_PASSWORD` | postgres, усі сервіси | обовʼязкова |
| `JOBOFFER_WEB_PUBLIC_URL` | app, agent | обовʼязкова; origin вебу, https |
| `JOBOFFER_AGENT_ALLOWED_HOSTS` | app, agent | обовʼязкова; JSON-список дозволених `Host` |
| `JOBOFFER_MAIL_ADDRESS` | app, agent, mailsync | обовʼязкова; скринька застосунку |
| `TUNNEL_TOKEN` | cloudflared | обовʼязкова; токен remotely-managed тунелю |
| `JOBOFFER_GOOGLE_CLIENT_ID`, `JOBOFFER_GOOGLE_CLIENT_SECRET`, `JOBOFFER_GOOGLE_REDIRECT_URI`, `JOBOFFER_AUTH_STATE_SECRET` | app, agent | вхід через Google; усі чотири або жодної, див. [auth.md](auth.md) |
| `JOBOFFER_GOOGLE_GATE_REDIRECT_URI` | agent | адреса повернення логін-гейта MCP |
| `JOBOFFER_ALTCHA_HMAC_KEY`, `JOBOFFER_ALTCHA_MAXNUMBER` | app | Altcha; без ключа реєстрація закрита |
| `JOBOFFER_GMAIL_CLIENT_ID`, `JOBOFFER_GMAIL_CLIENT_SECRET`, `JOBOFFER_GMAIL_SEND_REFRESH_TOKEN` | app | відправка листів (scope `gmail.send`); без токена реєстрація закрита |
| `JOBOFFER_MAIL_SEND_DAILY_LIMIT` | app | типово 50 листів за 24 год |
| `JOBOFFER_GMAIL_CLIENT_ID`, `JOBOFFER_GMAIL_CLIENT_SECRET`, `JOBOFFER_GMAIL_REFRESH_TOKEN` | mailsync | лише з `gmail.env` (scope `gmail.readonly`) |
| `JOBOFFER_DOCUMENTS_HOST_DIR` | app, agent | тека PDF на хості (типово `/srv/joboffer/documents`) |
| `JOBOFFER_GMAIL_ENV_FILE` | mailsync | шлях до файлу з кредами читання (типово `/etc/joboffer/gmail.env`) |

`JOBOFFER_AGENT_REDIRECT_ALLOWLIST` і `JOBOFFER_SESSION_*` у прод-compose не прокидаються: діють типові значення з
[auth.md](auth.md).

## Edge (Caddy)

`infra/web/Caddyfile`: `/api/*` → `app:8797` (префікс `/api` зрізається, як у Vite), `/mcp*` і
`/.well-known/oauth-*` → `agent:8798` без зміни шляху, решта `/.well-known/*` → 404, усе інше — SPA. Upstream-и
перевизначають `APP_UPSTREAM` і `AGENT_UPSTREAM`. HSTS, CSP, `nosniff` і Referrer-Policy стоять на всіх відповідях;
CSP, `nosniff` і Referrer-Policy, які агент задав сам (HTML логіна MCP), Caddy не перекриває. `Host` і
`CF-Connecting-IP` проходять до застосунку: IP клієнта для ліміту спроб береться з нього.

## Cloudflare Tunnel

Тунель remotely-managed (токен — `TUNNEL_TOKEN`), ingress у дашборді Cloudflare → `http://web:8080`. Обидві адреси
повернення Google (веб і гейт MCP) мають бути вписані в клієнт Google Cloud Console:
`https://<хост>/api/auth/google/callback` і `https://<хост>/mcp/auth/google/callback`.
