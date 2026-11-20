# Документація joboffer

Код у `app/` (бекенд), `web/` (клієнт), `infra/` (compose, образи, edge), `scripts/` (команди й CI).
Тут — опис того, що в коді, за темами. Швидкий старт — у [кореневому README](../README.md), політика безпеки — у
[SECURITY.md](../SECURITY.md).

| Файл | Про що |
|---|---|
| [architecture.md](architecture.md) | шари, правила залежностей, тести, промпти й шаблони, розкладка нового контексту |
| [development.md](development.md) | команди для локальної роботи, web-клієнт, база даних і міграції |
| [documents.md](documents.md) | генерація й перевірка PDF (CV, cover letter), фото для CV, чистка старих версій |
| [sources.md](sources.md) | прогін джерел вакансій, керування ними, «оновити зараз», тріаж за правилами |
| [mail.md](mail.md) | синк Gmail-скриньки, відповіді компаній, LinkedIn-алерти, відправка листів |
| [auth.md](auth.md) | користувачі, сесії, Altcha, запрошення, реєстрація з кодом, вхід через Google, агент (MCP + OAuth) |
| [deploy.md](deploy.md) | прод-стек: сервіси compose, профілі, edge Caddy, Cloudflare Tunnel, змінні оточення |

Каталог [design/](design/) — еталон логотипа (референс, не потрапляє в збірку).
