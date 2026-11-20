# Користувачі, вхід і агент

## Користувачі

Користувача створює оператор або він з'являється через запрошення (див. нижче). Оператор створює користувача командою;
пароль питається інтерактивно (двічі, ≥12 символів) і ніколи не береться з аргументів чи оточення.

```bash
cd app && JOBOFFER_DATABASE_URL=… uv run python -m bootstrap.create_user --email you@example.com --name "Імʼя"
```

У dev-стеку: `docker compose -f infra/compose.yaml exec app python -m bootstrap.create_user --email … --name …`;
у проді — те саме через `docker compose -f infra/compose.prod.yaml --env-file /etc/joboffer/env exec app …`.
Паролі зберігаються лише як Argon2id-хеш; email нормалізується (нижній регістр, без пробілів).

## Вхід і сесії

Cookie-сесія: `POST /auth/login` (email + пароль) видає HttpOnly-cookie і `csrf_token`; `GET /auth/me` повертає
користувача й той самий `csrf_token`; `POST /auth/logout` закриває сесію. Небезпечні методи (все, крім
GET/HEAD/OPTIONS) вимагають заголовок `X-CSRF-Token`. Назовні шляхи йдуть під `/api` (проксі знімає префікс).

Захищений маршрут бере `Actor` із сесії залежністю `Depends(container.auth.actor)`: вона дає 401 без сесії
і 403 без CSRF-токена на небезпечних методах. У БД лежить лише sha256-дайджест токена.

| Змінна | За замовчуванням | Що робить |
|---|---|---|
| `JOBOFFER_SESSION_IDLE_HOURS` | `12` | скільки сесія живе без активності (активність посуває вікно) |
| `JOBOFFER_SESSION_ABSOLUTE_DAYS` | `30` | абсолютний строк сесії, навіть активної |
| `JOBOFFER_SESSION_COOKIE_NAME` | `__Host-joboffer_session` (з `COOKIE_SECURE=false` — `joboffer_session`) | ім'я cookie; `__Host-` вимагає Secure, Path=/ і без Domain, тож браузер відкидає його по http |
| `JOBOFFER_COOKIE_SECURE` | `true` | прапор `Secure`; `false` лише для dev по http |
| `JOBOFFER_TRUSTED_PROXIES` | `0` | скільки reverse proxy перед застосунком; `0` — `X-Forwarded-For` ігнорується |
| `JOBOFFER_CLIENT_IP_HEADER` | не задано | заголовок з адресою клієнта від Cloudflare (`cf-connecting-ip`); береться лише коли сокет-peer локальний (loopback/приватна адреса), від решти ігнорується; має перевагу над `X-Forwarded-For` |

Ліміт спроб входу: 5 невдач за 15 хвилин для пари «клієнт + email» і 20 невдач за 15 хвилин для email з усіх клієнтів
разом (розподілений підбір), далі 429 з `Retry-After`. Спроби під час блоку не записуються, тож блок знімається за
15 хвилин після останньої невдачі, що його викликала, і не буває вічним.
З `JOBOFFER_ENVIRONMENT=prod` застосунок не стартує, якщо `JOBOFFER_COOKIE_SECURE=false`, `web_public_url` (крім
loopback-адрес) чи адреси Google не https, `agent_allowed_hosts` містить `*` або `agent_redirect_allowlist` має не-https запис
(крім `loopback`); `/docs`, `/redoc` і `/openapi.json` у проді не віддаються.
За reverse proxy (Caddy) став `JOBOFFER_TRUSTED_PROXIES=1`, інакше всі клієнти матимуть одну адресу.

### Altcha (захист реєстрації)

`GET /api/auth/challenge` видає задачу proof-of-work у форматі віджета altcha v1 (SHA-256, HMAC-SHA256 на stdlib):
`{algorithm, challenge, maxnumber, salt, signature}`, строк 5 хвилин у `salt`. Розв'язок (base64-JSON віджета)
перевіряє `AltchaUseCases.verify`: підпис, строк, число, формат; використаний розв'язок удруге не приймається
(таблиця `altcha_solutions`). Невірний розв'язок → `422 challenge_failed`. Без ключа задачі не видаються
(503 `registration_closed`) і розв'язки не приймаються.

| Змінна | За замовчуванням | Що робить |
|---|---|---|
| `JOBOFFER_ALTCHA_HMAC_KEY` | не задано | секрет підпису задач, ≥ 32 символи; задає лише власник на деплої |
| `JOBOFFER_ALTCHA_MAXNUMBER` | `100000` | верхня межа числа (складність для клієнта), 1..10000000 |

### Запрошення на реєстрацію

Режим задає `JOBOFFER_SIGNUP_MODE`: `closed` (за замовчуванням) або `invite`. Оператор створює одноразове запрошення:
`python -m bootstrap.create_invite` (у dev-стеку: `docker compose -f infra/compose.yaml exec app python -m bootstrap.create_invite`;
у проді — `docker compose -f infra/compose.prod.yaml --env-file /etc/joboffer/env exec app python -m bootstrap.create_invite`)
друкує `<JOBOFFER_WEB_PUBLIC_URL>/signup?invite=<токен>`; токен видно лише тут, у БД лежить його sha256. Запрошення живе
7 днів і погашається один раз.

`GET /auth/signup/invite?invite=<токен>` без сесії: дійсне → `200 {valid, expires_at}`; невідоме, прострочене чи використане →
однаково `404 invite_invalid`; режим `closed` → `404 signup_closed`; понад 20 перевірок за 15 хвилин з одного клієнта →
`429` з `Retry-After`.

### Реєстрація з кодом з листа

Користувач з'являється в `users` лише після правильного коду; до того дані чекають у `signup_requests` (хеш пароля й
sha256-дайджест коду, один запит на email). Потрібні `JOBOFFER_SIGNUP_MODE=invite`, ключ ALTCHA і токен `gmail.send`
(без них `503 registration_closed`). Усі три маршрути — без сесії.

- `POST /auth/signup` `{email, password, display_name?, invite, terms_version, altcha, website}` → `202 {signup_id}` і
  лист із 6-цифровим кодом. Порядок перевірок: режим (`404 signup_closed`) → приманка `website` (заповнена → `202`, нічого
  не робимо) → ALTCHA (`422 challenge_failed`) → запрошення (`404 invite_invalid`, не гаситься) → `terms_version` ==
  поточна версія `GET /legal/terms` (`422`) → пароль від 8 символів із цифрою, малою й великою літерою та спецсимволом (`422 password_weak` з переліком того, чого бракує; закороткий чи задовгий — `422 invalid_value`) →
  ліміт 5 реєстрацій за годину з клієнта (`429`). Наявний email → така сама `202` з випадковим `signup_id` і лист
  «акаунт уже є» без коду. `display_name` не обовʼязкове: без нього — частина email до `@`. Збій пошти чи вичерпаний
  добовий ліміт листів → `503 mail_unavailable`, запрошення ціле.
- `POST /auth/signup/verify` `{signup_id, code}`: невірний код → `422 code_incorrect` з `attempts_left`; п'ята невдача,
  15 хвилин чи невідомий `signup_id` → `422 signup_expired`; правильний код в одній транзакції гасить запрошення (не вдалось →
  `409 invite_used`), створює користувача з версією умов і видаляє запит, далі `201` + cookie-сесія + `csrf_token`.
- `POST /auth/signup/resend` `{signup_id}` → `202 {signup_id}` і новий код (старий перестає діяти, спроби скидаються,
  15 хвилин рахуються заново); раніше ніж через 60 секунд або понад 5 листів на email за годину → `429` з `Retry-After`.

Ліміти реєстрації (5 / год з клієнта, 5 листів / год на email) ведуться в `signup_limits`, а не в `login_failures`: вхід і
перевірка запрошення чистять її від записів старших за 15 хвилин. Прострочені запити прибираються під час `signup`.

У вебі це `/signup?invite=<токен>` (форма: email, імʼя, пароль, згода з `/terms` і `/privacy`, віджет ALTCHA) і
`/signup/verify` (код із листа). Форма є лише для дійсного запрошення: без нього чи з недійсним, а також на
`/signup/verify` без розпочатої реєстрації — екран помилки без форми. Посилання на реєстрацію з `/login` нема, кнопки
Google на цих сторінках теж. Віджет `altcha` зібрано в бандл (воркер — окремий файл свого origin, без CDN; CSP з
`worker-src 'self' blob:`). Після правильного коду відкривається `/profile`.

### Вхід через Google

`GET /auth/google/start?next=` → Google (OIDC, Authlib: state, nonce, PKCE S256, `id_token` перевіряє Authlib за JWKS) →
`GET /auth/google/callback` → та сама cookie-сесія, що й пароль, → редирект у SPA на `next` (лише внутрішній шлях).
Google лише пускає, але не реєструє: потрібен підтверджений `email`, і користувач мусить уже бути в `users`. Без email,
з непідтвердженим або з невідомим email (зокрема лише в незавершеній реєстрації `signup_requests`) — помилка
`email_required`, ні користувача, ні сесії. Користувач шукається за Google `sub` → за email (identity привʼязується до
наявного, пароль далі працює). Підроблений `state` — `invalid_state`.
Стан флоу — підписана cookie `joboffer_oauth_state` (10 хв). `GET /auth/providers` каже SPA, чи показувати кнопку.

| Змінна | Що робить |
|---|---|
| `JOBOFFER_GOOGLE_CLIENT_ID`, `JOBOFFER_GOOGLE_CLIENT_SECRET` | OAuth-клієнт «Web application» із Google Cloud Console |
| `JOBOFFER_GOOGLE_REDIRECT_URI` | рівно та адреса, що вписана в клієнт Google: `https://<хост>/api/auth/google/callback` |
| `JOBOFFER_AUTH_STATE_SECRET` | підпис cookie стану флоу, ≥ 32 символи |

Усі чотири або жодної: без них Google вимкнено, пароль працює.

**Логін-гейт MCP** (`JOBOFFER_GOOGLE_GATE_REDIRECT_URI` — адреса повернення гейта, у процесі `agent`): кнопка «Увійти через Google»
на сторінці згоди → `GET /auth/google/start?rid=` → Google → `GET /auth/google/callback` → той самий `sign_in_with_google` →
`complete_authorization` → редирект у клієнт MCP із кодом. `rid` перевіряється до Google і після повернення; на помилці код
не видається, а `rid` лишається живим. Стан гейта — власна cookie `joboffer_gate_state` і власний підпис (стан веб-флоу тут не діє).
У Google Cloud Console для одного клієнта — дві адреси повернення (веб і гейт). Адреса гейта мусить дорівнювати `<origin вебу>/mcp/auth/google/callback` (інакше застосунок не стартує).

## Агент (MCP + OAuth)

Окремий процес `bootstrap.agent:create_agent_app` (compose-сервіс `agent`, `127.0.0.1:8798`): MCP-ендпоінт
(streamable HTTP) на `<origin вебу>/mcp` і OAuth 2.1-сервер на MCP SDK (DCR лише публічних клієнтів, PKCE S256, resource
RFC 8707, scope рівно `joboffer`). Токени й коди — лише sha256-дайджести в БД; код і refresh одноразові,
повторне пред'явлення відкликає грант. Тул отримує `Actor(channel=mcp, grant_id, scopes={read, write})` із токена
через `infrastructure.mcp.actor.current_actor()`. Публічний `/register` (DCR) без автентифікації: 10 запитів за годину з
клієнта (429), тіло до 16 КіБ (413), клієнти без гранту старші за 30 днів видаляються (`oauth_clients.registered_at`).

Логін-гейт `/login`: екран згоди (хто просить доступ і куди піде код) + **email і пароль** користувача з `users`
(`python -m bootstrap.create_user`); ліміт спроб той самий «клієнт + email», що й у вебі. HTML — файли
`app/templates/oauth/`, без JS. Маршрути OAuth лежать у корені процесу й під `/mcp/…` (так їх оголошують метадані). Edge (Caddy, Tunnel, у dev — Vite)
веде на агента `/mcp*`, `/.well-known/oauth-protected-resource/mcp` і `/.well-known/oauth-authorization-server*` без зміни шляху.

| Змінна | За замовчуванням | Що робить |
|---|---|---|
| `JOBOFFER_WEB_PUBLIC_URL` | `http://localhost:5174` | origin вебу; адреса агента = цей origin + `/mcp` (resource OAuth, окремого налаштування нема) |
| `JOBOFFER_AGENT_ALLOWED_HOSTS` | `["127.0.0.1:*","localhost:*"]` | дозволені `Host` (JSON-список); браузерний `Origin` не дозволено |
| `JOBOFFER_AGENT_REDIRECT_ALLOWLIST` | `["https://claude.ai/api/mcp/auth_callback","loopback"]` | куди дозволено віддавати код: точна адреса, `…/*` (один сегмент-ID) або `loopback` |

Перевірка з Claude Code (тестового користувача створи сам через `create_user`):

```bash
claude mcp add --transport http joboffer http://localhost:5174/mcp
```
