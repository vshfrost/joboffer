"""Вид і назва агента за DCR-клієнтом: чиста функція без IO.

Правила за порядком (перше, що збіглось):
1. хост redirect_uri — claude.ai чи claude.com, а назва без «code» → Claude;
2. назва містить «Claude Code» → Claude Code;
3. хост — chatgpt.com чи openai.com → ChatGPT;
4. назва містить «codex» → Codex;
5. інакше — «other» під назвою клієнта (до 80 символів) або його id, якщо назви нема.
"""

import re

from domain.agents.agent import AgentIdentity, AgentKind

NAME_LIMIT = 80
_CLAUDE_HOSTS = ("claude.ai", "claude.com")
_CHATGPT_HOSTS = ("chatgpt.com", "openai.com")
# Authority закінчується на `/ ? # \`: зворотний слеш браузер читає як `/`, тож `evil.com\@claude.ai` — хост evil.com.
_AUTHORITY = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://([^/?#\\]*)")


def classify_agent(
    client_id: str, name: str | None, redirect_uris: tuple[str, ...]
) -> AgentIdentity:
    lowered = (name or "").casefold()
    hosts = [_host(uri) for uri in redirect_uris]
    if "code" not in lowered and _on(hosts, _CLAUDE_HOSTS):
        return AgentIdentity(AgentKind.CLAUDE, "Claude")
    if "claude code" in lowered:
        return AgentIdentity(AgentKind.CLAUDE_CODE, "Claude Code")
    if _on(hosts, _CHATGPT_HOSTS):
        return AgentIdentity(AgentKind.CHATGPT, "ChatGPT")
    if "codex" in lowered:
        return AgentIdentity(AgentKind.CODEX, "Codex")
    shown = (name or "").strip()[:NAME_LIMIT].strip()
    return AgentIdentity(AgentKind.OTHER, shown or client_id)


def _host(uri: str) -> str:
    """Хост з адреси `схема://[користувач@]хост[:порт]/…`; не адреса — порожній рядок."""
    found = _AUTHORITY.match(uri)
    if found is None:
        return ""
    host_port = found.group(1).rpartition("@")[2]
    return (
        host_port.rpartition(":")[0].lower() if ":" in host_port else host_port.lower()
    )


def _on(hosts: list[str], domains: tuple[str, ...]) -> bool:
    """Хост — сам домен або його піддомен (`www.claude.ai`), але не `evilclaude.ai`."""
    return any(host == d or host.endswith(f".{d}") for host in hosts for d in domains)
