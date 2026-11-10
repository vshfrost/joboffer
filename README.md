# joboffer

Сервіс генерації CV та Cover Letter для подачі на вакансію

## Архітектура

Гексагональна (ports & adapters), один модульний моноліт. Шари — пакети верхнього рівня в `app/`:

```
app/domain/          сутності, value objects, інваріанти, політики — лише stdlib, без IO
app/application/     use cases, DTO, порти, межа транзакції
app/infrastructure/  адаптери: HTTP, БД, зовнішні сервіси
app/bootstrap/       єдине місце, де все з'єднується (settings, wiring, точки входу)
```

- Залежності лише всередину: `bootstrap → infrastructure → application → domain`.
  Перевіряють import-linter і `app/tests/architecture/`.
- Оточення читається лише в `bootstrap/settings.py` (префікс `JOBOFFER_`); модульних синглтонів нема.
- Час і ID приходять у domain явними значеннями (порти), не з `now()` чи `uuid4()`.

## Тести

```
app/tests/
  architecture/  межі шарів, композиція, розкладка пакетів
  unit/          core без IO (детермінований час і ID, заборона мережі й файлів)
  acceptance/    BDD: features/*.feature (# language: uk) + кроки поруч
  composition/   wiring у bootstrap
  contracts/ integration/ e2e/   — з'являються разом з адаптерами
```

Кроки pytest-bdd синхронні; async use case викликається через фікстуру `portal`:
`portal.call(use_case, command)`.

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
scripts/test-core.sh   # core-only тести в окремому venv без FastAPI і решти інфраструктури
scripts/ci.sh          # увесь CI однією командою; `ci.sh app|web|infra` — одна частина (так її запускає GitHub Actions, три job паралельно)
docker compose -f infra/compose.yaml up -d --build
```

## PDF документів

CV і cover letter генерує Claude через MCP: `prepare_*` → `check_cv` / `check_cover_letter` (нічого не зберігають:
спершу текст без рендеру — факти, фото, невидимі символи, переноси, подвійні пробіли, маркери, шаблони `[…]`,
покриття ключових слів; PDF у пам'яті й ATS-lint — лише коли текст чистий) → `save_*` один раз. Збереження повторює
ті самі перевірки, відмовляє при будь-якому зауваженні, а успішне замінює попередній документ того ж виду для тієї ж
вакансії (рядок, файл PDF і одноразові посилання видаляються; номери документів і версії лише ростуть).
Сервер рендерить PDF (WeasyPrint, шаблони в
`app/templates/pdf/`), робить ATS-lint (pypdf) і кладе файл у `JOBOFFER_DOCUMENTS_DIR` (`<id документа>.pdf`; у образі й
compose — volume `/data/documents`). Відкривається `GET /api/documents/<номер>/pdf` з чинною сесією. Для рендера потрібні
системні pango, harfbuzz і шрифти DejaVu (в образі й CI є); на Mac без них PDF-тести падають — запускай їх у Linux-контейнері
або в CI. Шапка CV може нести фото користувача (`save_cv(photo_id)`): рамка 101 × 113 pt праворуч, текст відступає;
в листа фото нема.

Одноразова чистка старих версій (лишає найновіший документ кожного користувача, вакансії й виду; решту разом із PDF
видаляє): `python -m bootstrap.prune_documents` лише рахує, `--apply` видаляє. Запускати там, де том документів
доступний для запису, тобто в сервісі `agent`:
`docker compose -f infra/compose.prod.yaml --env-file /etc/joboffer/env exec agent python -m bootstrap.prune_documents --apply`.

## Фото для CV

Фото лежать у Postgres (`photos.data`, `bytea`). Завантажує користувач у вебі: `POST /api/photos` (multipart `file` +
`label`, CSRF), далі `GET /api/photos`, `GET /api/photos/<номер>.jpg` (лише власнику) і `DELETE /api/photos/<номер>`.
Сервер не обрізає: приймає кадр, який користувач обрав у браузері, перевіряє пропорції рамки шапки CV (858 × 960 ±1 %)
і ширину ≥ 300 px, повертає за EXIF, кладе прозорість на білий, зменшує сторону до 900 px і пише JPEG без метаданих.
Тіло завантаження читається потоком і обривається на 5 МБ ще під час читання; кадр понад 16 МП відхиляється за заголовком, до декодування. Агент бачить фото тулом `list_photos`;
байти через MCP не передаються. Фото — персональні дані: не логувати байти, у тестах лише згенеровані зображення.

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
Бренд — `web/public/brand/`, еталон лого — `docs/design/` (референс, не в збірці).

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

## Прогін джерел

Вакансії з ATS компаній (Greenhouse, Ashby, Lever) і RSS-стрічок (DOU, Djinni) імпортуються кожному користувачеві за
його профілем. Таблиці: `source_companies`, `source_feeds` (унікальні «користувач + платформа + слаг» і «користувач +
джерело + запит») та стан останнього прогону — `source_company_runs` / `source_feed_runs`, один рядок на джерело
користувача (час, лічильники, код помилки).

```bash
docker compose -f infra/compose.yaml run --rm sources    # або: cd app && uv run python -m bootstrap.refresh_sources
```

- Ту саму ціль кількох користувачів прогін читає один раз; кожне джерело користувача комітиться окремо. Збій
  джерела (`timeout`, `not_found`, `rate_limited`, `unavailable`, `rejected`, `invalid`, `unsupported`) записується
  в його стан, решта йде далі; так само будь-який інший збій читання (стан `invalid`, текст винятку нікуди не
  йде); джерело, видалене посеред прогону, пропускається. Код виходу — 0. Паралельний запуск пропускається (pg
  advisory lock).
- Аудит — рядки `SOURCES_AUDIT` (джерело, ціль, користувач, лічильники, код помилки) без вмісту вакансій.
- Секретів немає; таймер на сервері — B12.

Керування джерелами — `/api/sources` (сесія + CSRF, як решта вебу): `GET` — компанії й стрічки з `last_run`
(`null` — прогону ще не було); `POST /companies {platform, slug, name?}` (один пробний запит до ATS; 422 біля поля
`platform` / `slug`) і `POST /feeds {source, query}` (`name=value` через `&`, DOU — `category`, Djinni —
`primary_keyword`; 422 біля `source` / `query`) → 201; `PATCH /companies|feeds/{id} {enabled}` → 200;
`DELETE /companies|feeds/{id}` → 204 (стан прогону зникає, імпортовані вакансії лишаються); чуже чи неіснуюче → 404.

«Оновити зараз»: `GET /api/sources` також віддає `refresh {limit, remaining, next_at, last_run_at}` (`last_run_at` —
найпізніший прогін джерел користувача, `null` — прогонів ще не було) і `filtered_out_count`; `POST /refresh` ставить
запит у чергу (`source_refresh_requests`) → 202, не більше 2 за 30 хв на користувача, третій → 429 `refresh_limit` з
`Retry-After`. Прогін (`bootstrap.refresh_sources`) позначає всі запити, що чекали, виконаними. «Уже не проходять
фільтр»: `GET /filtered` → `[{number, title, company, reason}]` (свої вакансії `ats:` / `rss:`, не сховані, без аналізу
й подачі; reason — `title` / `excluded` / `format` / `location`); `POST /filtered/dismiss {numbers}` → 200
`{dismissed}` (сервер перераховує список; хоч одного номера нема — 409 `filtered_changed`, нічого не сховано; порожній
вибір — 422 біля `numbers`; вакансії ховаються з причиною «фільтр профілю»). MCP: `get_sources`, `refresh_sources`.

## Синк пошти

Користувачі пересилають листи (відповіді компаній, підтвердження Gmail) на особисту адресу `local+<tag>@domain` у
скриньці застосунку; joboffer лише читає цю скриньку (scope `gmail.readonly`) і розкладає листи по власниках за tag.

```bash
docker compose -f infra/compose.yaml run --rm mailsync    # або: cd app && uv run python -m bootstrap.sync_mail
```

- Оточення: `JOBOFFER_MAIL_ADDRESS`, `JOBOFFER_GMAIL_CLIENT_ID` / `_CLIENT_SECRET` / `_REFRESH_TOKEN` (`infra/.env`,
  шаблон `.env.example`). Креди є лише в процесі синку; без них він не стартує. Значення вписує оператор.
- Курсор змін (`historyId`) зберігається в БД; протухлий або відсутній — ресинк за 90 днів. Паралельний запуск
  пропускається (pg advisory lock). Скринька недоступна — помилка в стані синку й код виходу 1.
- Лист без `+tag` чи з чужим tag лише рахується в аудиті. Лист на адресу до ротації або понад 100 листів за 24 год
  записується власнику без тексту: причина, дата, адреса відправника й тема (до 200 символів).
- Листи компаній у тій самій транзакції зіставляються з поданими вакансіями власника (тред → адреса → домен → ATS
  з назвою компанії → назва) і отримують підказку типу; подача сама йде applied → replied лише за впевненого збігу
  від verified-відправника (не для автопідтвердження й не для ручного пересилання). Далі відповіді розбирає агент:
  MCP-тули `list_replies` / `review_reply`; у вебі — `/replies` (черги «До розбору» / «Без вакансії» / «Розібрані»
  з лічильниками, пошук, сторінки 20 / 50 / 100, деталі з подачами власника, превʼю `GET /replies/{id}/preview?type=&job_id=`
  і `POST /replies/{id}/review` за тими самими правилами).
- Відправка листів (код реєстрації): сервіс `app`, Gmail `messages.send`, окремий `JOBOFFER_GMAIL_SEND_REFRESH_TOKEN`
  зі scope `gmail.send` (client id і secret ті самі; токена синку в `app` нема, токена відправки нема в `mailsync`).
  Лист text/plain UTF-8 від «joboffer <JOBOFFER_MAIL_ADDRESS>», без посилань; шаблони — `app/templates/mail/*.txt`.
  Не більше `JOBOFFER_MAIL_SEND_DAILY_LIMIT` (типово 50) листів за 24 год (журнал `mail_sends`, лише моменти);
  понад ліміт запиту до Google нема. Без токена реєстрація закрита (`Container.registration_open`).
- Листи `linkedin_alert` (підроблені з DMARC fail мають вид suspicious і не розбираються) там само розбираються за структурою дайджесту у вакансії
  власника «потрібен текст» (посада, компанія, локація, канонічне посилання, `linkedin_id`, source `linkedin_alert`);
  кожен лист — рівно раз (`alerts_processed_at`), вакансія з таким `linkedin_id` не дублюється. Не розібране
  лишається в `parse_error` листа, синк не падає. Текст вакансії дописується через `add_job` з посиланням LinkedIn.
- Аудит — рядки `MAIL_AUDIT …` без вмісту листів і секретів (для алертів: alerts / created / known / failed).

## Користувачі

Реєстрації немає: користувача створює оператор. Пароль питається інтерактивно (двічі, ≥12 символів) і ніколи
не береться з аргументів чи оточення.

```bash
cd app && JOBOFFER_DATABASE_URL=… uv run python -m bootstrap.create_user --email you@example.com --name "Імʼя"
```

У dev-стеку: `docker compose -f infra/compose.yaml exec app python -m bootstrap.create_user --email … --name …`.
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
З `JOBOFFER_ENVIRONMENT=prod` застосунок не стартує, якщо `JOBOFFER_COOKIE_SECURE=false`, `web_public_url` чи адреси
Google не https, `agent_allowed_hosts` містить `*` або `agent_redirect_allowlist` має не-https запис; `/docs`, `/redoc` і
`/openapi.json` у проді не віддаються.
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
`python -m bootstrap.create_invite` (у dev-стеку: `sudo docker compose -p joboffer exec app python -m bootstrap.create_invite`)
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

## Прод

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

- Сервіси: `postgres` (том `joboffer-pgdata`), `app` (`127.0.0.1:8797`), `agent` (`127.0.0.1:8798`), `web` (Caddy,
  `127.0.0.1:8799` → контейнер `:8080`), `cloudflared` (образ запінено на точну версію, портів не публікує) і одноразові
  `sources` (профіль `sources`), `triage` (профіль `triage`: `python -m bootstrap.auto_triage` — тріаж вакансій за
  ключовими словами, профілем і підтвердженими фактами без LLM і без ключів; `--report` лише читає: порівняння з повними
  аналізами й розподіл вердиктів; рядки `agent` не перезаписує) та `mailsync` (профіль `mail`; Gmail-доступ на читання
  лише з `/etc/joboffer/gmail.env`, поза репо). Усі, крім `sources`, `triage` і `mailsync`, мають `restart: unless-stopped`.
- PDF документів: тека хоста `/srv/joboffer/documents` (uid 10001, права 0700; інший шлях — `JOBOFFER_DOCUMENTS_HOST_DIR`)
  монтується в `/data/documents`: агент пише, app читає.
- Фіксовано в compose: `JOBOFFER_ENVIRONMENT=prod`, `COOKIE_SECURE=true`, `SIGNUP_MODE=invite`,
  `CLIENT_IP_HEADER=cf-connecting-ip`, `TRUSTED_PROXIES=1`; публічну адресу, дозволені Host-и й
  скриньку застосунку задає оператор в env-файлі.
- Edge (`infra/web/Caddyfile`): `/api/*` → `app:8797` (префікс `/api` зрізається, як у Vite), `/mcp`, `/mcp/*` і
  `/.well-known/oauth-*` → `agent:8798` без зміни шляху, решта `/.well-known/*` → 404, усе інше — SPA. Upstream-и
  перевизначають `APP_UPSTREAM` і `AGENT_UPSTREAM`. HSTS, CSP, `nosniff` і Referrer-Policy стоять на всіх відповідях;
  CSP, `nosniff` і Referrer-Policy, які агент задав сам (HTML логіна MCP), Caddy не перекриває. `Host` і
  `CF-Connecting-IP` проходять до застосунку: IP клієнта для ліміту спроб береться з нього.
- Cloudflare: тунель remotely-managed (токен — `TUNNEL_TOKEN`), ingress у дашборді → `http://web:8080`. Обидві адреси повернення Google (веб і гейт MCP) мають бути вписані в клієнт Google Cloud Console.

## Промпти й шаблони

Текст для моделі — файли `app/prompts/<область>/<імʼя>.md`, шаблони (HTML, згодом PDF) — `app/templates/<область>/<імʼя>.html`.
У Python їх нема (довгі рядкові літерали забороняє `tests/architecture/test_no_prompt_literals.py`): доступ лише через
порти `Prompts` і `Templates` за типізованим ключем; усі файли читаються на старті, відсутній — помилка з назвою файлу.
У образі вони лежать у `/app/prompts` і `/app/templates` (`JOBOFFER_PROMPTS_DIR`, `JOBOFFER_TEMPLATES_DIR`).

## Контексти

Новий контекст — по одному файлу на шар:

```
app/domain/<контекст>/                 ID, value objects, агрегат (версія, події)
app/application/contracts/<контекст>.py   команди й результати — примітиви
app/application/ports/<контекст>.py       репозиторій і unit of work контексту
app/application/<контекст>/use_cases.py   єдине місце правил
app/infrastructure/db/<контекст>/         таблиця й репозиторій
app/infrastructure/http/<контекст>.py     запит → команда → use case → відповідь
app/tests/support/<контекст>.py           in-memory адаптери для core-тестів
app/tests/acceptance/features/            правила без бази (BDD, `# language: uk`)
```
