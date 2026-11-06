"""Адреси повернення (redirect_uri) для DCR-клієнтів: що дозволено. Як порівнювати — адаптер `RedirectPolicy`."""

CLAUDE_CALLBACK = "https://claude.ai/api/mcp/auth_callback"
# Запис «loopback»: http://127.0.0.1 | localhost | [::1] на будь-якому порту (CLI-логін).
LOOPBACK = "loopback"
DEFAULT_ENTRIES = (CLAUDE_CALLBACK, LOOPBACK)
