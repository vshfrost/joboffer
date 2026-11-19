# Архітектура

Гексагональна (ports & adapters), один модульний моноліт. Шари — пакети верхнього рівня в `app/`:

```
app/domain/          сутності, value objects, інваріанти, політики — лише stdlib, без IO
app/application/     use cases, DTO, порти, межа транзакції
app/infrastructure/  адаптери: HTTP, БД, зовнішні сервіси
app/bootstrap/       єдине місце, де все з'єднується (settings, wiring, точки входу)
```

- Залежності лише всередину: `bootstrap → infrastructure → application → domain`.
  Перевіряють import-linter (контракти в `app/pyproject.toml`: шари, заборона фреймворків у core) і `app/tests/architecture/`.
- Оточення читається лише в `bootstrap/settings.py` (префікс `JOBOFFER_`); модульних синглтонів нема.
- Час і ID приходять у domain явними значеннями (порти), не з `now()` чи `uuid4()`.

## Тести

```
app/tests/
  architecture/  межі шарів, композиція, розкладка пакетів
  unit/          core без IO (детермінований час і ID, заборона мережі й файлів)
  acceptance/    BDD: features/*.feature (# language: uk) + кроки поруч
  composition/   wiring у bootstrap
  contracts/     адаптери й текстові артефакти без БД: Gmail, PDF, джерела, схеми MCP-тулів, промпти, шаблони, compose і Caddyfile
  integration/   справжні зовнішні сервіси: Postgres через testcontainers (репозиторії, HTTP, MCP-тули, міграції)
  e2e/           застосунок наскрізь через транспорти, без БД
  support/       in-memory адаптери й фікстури для core-тестів
```

Кроки pytest-bdd синхронні; async use case викликається через фікстуру `portal`:
`portal.call(use_case, command)`.

`unit` і `acceptance` входять у core-набір (`scripts/test-core.sh`): він ганяється в окремому venv без FastAPI і решти
інфраструктури, тож імпорт фреймворку в core ламає його одразу. `contracts`, `integration` і `e2e` у core-набір не входять.

## Промпти й шаблони

Текст для моделі — файли `app/prompts/<область>/<імʼя>.md`, шаблони — `app/templates/<область>/<імʼя>.html`
(листи, область `mail`, — звичайний текст `.txt`). Шаблони — це HTML для PDF документів (`pdf/`) і сторінок логін-гейта
агента (`oauth/`); у тій самій теці лежать юридичні тексти `legal/*.md`, їх читає окремий адаптер.
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
