# Джерела вакансій і тріаж

## Прогін джерел

Вакансії з ATS компаній (Greenhouse, Ashby, Lever, SmartRecruiters, Workable) і RSS-стрічок (DOU, Djinni) імпортуються кожному користувачеві за
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
- Секретів немає. Періодичний запуск (таймер, cron) налаштовує оператор; прод-команда — у [deploy.md](deploy.md).

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

## Тріаж за правилами

Тріаж вакансій без LLM і без ключів API: сервер сам оцінює вакансії користувачів без тріажу за ключовими словами,
профілем і підтвердженими фактами (скор за рубрикою аналізу, вердикт `skip` / `maybe` / `analyse` і причина).
Одноразовий запуск — `python -m bootstrap.auto_triage` (у проді — сервіс `triage`, профіль `triage`, див. [deploy.md](deploy.md)).

- Користувач — окрема транзакція: збій одного не відкочує вже збережене в інших; один прогін тріажить до 200 вакансій
  користувача, решта — у наступному. Паралельний запуск пропускається (pg advisory lock).
- Тріаж, який зробив агент (Claude через MCP: `prepare_triage` → `save_triage`), прогін за правилами ніколи не перезаписує.
- `--report` лише читає: порівняння з повними аналізами й розподіл вердиктів, нічого не пише; `--report --detail`
  додає рядок на вакансію, підсумок по складниках рубрики та чергу на тріаж.
- У логах лише лічильники й коди помилок, без вмісту вакансій.
