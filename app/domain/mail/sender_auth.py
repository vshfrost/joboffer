"""Автентичність відправника листа: вердикт DMARC із заголовків, що пройшли ланцюжок
відправник → Cloudflare Email Routing → основний Gmail → пересилання → скринька застосунку."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum


class SenderAuth(StrEnum):
    """Чи справжній відправник листа за DMARC: verified (pass), failed (fail) або unknown
    (нема вердикту, не довіряємо заголовкам, домен не збігся)."""

    VERIFIED = "verified"
    FAILED = "failed"
    UNKNOWN = "unknown"


# Заголовки автентифікації листа зверху вниз: (ім'я нижнім регістром, значення в один рядок).
AuthHeaders = tuple[tuple[str, str], ...]
AUTHENTICATION_RESULTS = "authentication-results"
ARC_AUTHENTICATION_RESULTS = "arc-authentication-results"
ARC_SEAL = "arc-seal"
# Authserv-id скриньки застосунку: лише верхній Authentication-Results від неї — наш.
APP_MAILBOX_AUTHSERV = "mx.google.com"
# Cloudflare Email Routing — перший вузол ланцюжка, що перевіряє DMARC відправника.
CLOUDFLARE_AUTHSERV = "mx.cloudflare.net"
CLOUDFLARE_ARC_DOMAIN = "cloudflare-email.net"


def sender_auth(auth_headers: AuthHeaders, from_address: str) -> SenderAuth:
    """Чи справжній відправник: вердикт DMARC для домену From.

    Читається лише верхній Authentication-Results від скриньки застосунку (нижчі міг
    вставити відправник). Якщо в ньому `arc=pass` — вердикт бере Cloudflare Email Routing із
    найнижчого набору ARC, який він запечатав; інакше (нема такого набору чи `arc` не pass) —
    вердикт самого верхнього заголовка. Домен вердикту мусить збігтися з доменом From.
    ARC-печатки криптографічно не перевіряються: довіряємо `arc=pass` скриньки застосунку."""
    domain = from_address.rpartition("@")[2].lower()
    top = next((v for n, v in auth_headers if n == AUTHENTICATION_RESULTS), None)
    if not domain or top is None:
        return SenderAuth.UNKNOWN
    authserv, results = _parse_results(top)
    if authserv != APP_MAILBOX_AUTHSERV:
        return SenderAuth.UNKNOWN
    arc = _result(results, "arc")
    verdict = None
    if arc is not None and arc.value == "pass":
        cloudflare = _cloudflare_verdict(auth_headers)
        verdict = _arc_summary(arc.comment) if cloudflare is None else cloudflare
    verdict = verdict or _direct_verdict(results)
    if verdict is None or verdict.domain != domain:
        return SenderAuth.UNKNOWN
    return _VERDICTS.get(verdict.result, SenderAuth.UNKNOWN)


@dataclass(frozen=True, slots=True)
class _Resinfo:
    """Один `метод=результат (коментар) властивості` з Authentication-Results."""

    method: str
    value: str
    comment: str
    properties: dict[str, str]


@dataclass(frozen=True, slots=True)
class _Verdict:
    result: str
    domain: str


_VERDICTS = {"pass": SenderAuth.VERIFIED, "fail": SenderAuth.FAILED}
_RESINFO = re.compile(
    r"\s*([a-z0-9-]+)\s*=\s*([a-z0-9-]+)(.*)", re.IGNORECASE | re.DOTALL
)
_PROPERTY = re.compile(r'([a-z0-9-]+\.[a-z0-9-]+)\s*=\s*("[^"]*"|\S+)', re.IGNORECASE)
_ARC_SUMMARY_DMARC = re.compile(r"(?<![\w.-])dmarc=([a-z0-9-]+)", re.IGNORECASE)
_ARC_SUMMARY_DOMAIN = re.compile(r"(?<![\w.-])fromdomain=([^\s;()]+)", re.IGNORECASE)
_ARC_INSTANCE = re.compile(r"i=(\d+)", re.IGNORECASE)
_ARC_SEAL_DOMAIN = re.compile(r"(?<![\w.-])d=([^\s;]+)", re.IGNORECASE)


def _split_header(value: str) -> list[tuple[str, str]]:
    """Значення заголовка → [(текст, коментарі)] за верхньорівневими «;». Крапка з комою в
    лапках чи дужках (її може вписати відправник, напр. в smtp.mailfrom) не ділить."""
    parts: list[tuple[str, str]] = []
    code: list[str] = []
    comment: list[str] = []
    depth = 0
    quoted = False
    for char in value:
        if char == '"':
            quoted = not quoted
        elif not quoted and char == "(":
            depth += 1
            if depth == 1:
                continue
        elif not quoted and char == ")" and depth:
            depth -= 1
            if depth == 0:
                comment.append(" ")
                continue
        elif not quoted and not depth and char == ";":
            parts.append(("".join(code), "".join(comment)))
            code, comment = [], []
            continue
        (comment if depth else code).append(char)
    parts.append(("".join(code), "".join(comment)))
    return parts


def _parse_results(value: str) -> tuple[str, list[_Resinfo]]:
    """(authserv-id нижнім регістром, результати) з Authentication-Results; для
    ARC-Authentication-Results спершу відкидається `i=N`."""
    parts = _split_header(value)
    if parts and _ARC_INSTANCE.fullmatch(parts[0][0].strip()):
        parts = parts[1:]
    if not parts:
        return "", []
    words = parts[0][0].split()
    authserv = words[0].lower() if words else ""
    results = []
    for code, comment in parts[1:]:
        found = _RESINFO.fullmatch(code)
        if found is None:
            continue
        properties = {
            name.lower(): found_value.strip('"').lower()
            for name, found_value in _PROPERTY.findall(found.group(3))
        }
        results.append(
            _Resinfo(
                found.group(1).lower(), found.group(2).lower(), comment, properties
            )
        )
    return authserv, results


def _result(results: Sequence[_Resinfo], method: str) -> _Resinfo | None:
    return next((item for item in results if item.method == method), None)


def _direct_verdict(results: Sequence[_Resinfo]) -> _Verdict | None:
    dmarc = _result(results, "dmarc")
    if dmarc is None:
        return None
    return _Verdict(dmarc.value, dmarc.properties.get("header.from", ""))


def _arc_summary(comment: str) -> _Verdict | None:
    """Вердикт попереднього вузла з підсумку `arc=pass (i=N … dmarc=X fromdomain=D)`."""
    result = _ARC_SUMMARY_DMARC.search(comment)
    domain = _ARC_SUMMARY_DOMAIN.search(comment)
    if result is None or domain is None:
        return None
    return _Verdict(result.group(1).lower(), domain.group(1).lower())


def _cloudflare_verdict(auth_headers: AuthHeaders) -> _Verdict | None:
    """DMARC з найнижчого набору ARC, запечатаного Cloudflare: ARC-Seal з d=cloudflare-email.net
    і ARC-Authentication-Results того ж i= від mx.cloudflare.net. Набір без печатки Cloudflare
    ігнорується: його міг вигадати відправник."""
    sealed = {
        int(instance.group(1))
        for name, value in auth_headers
        if name == ARC_SEAL
        and (instance := _ARC_INSTANCE.match(value.strip()))
        and (domain := _ARC_SEAL_DOMAIN.search(value))
        and domain.group(1).lower() == CLOUDFLARE_ARC_DOMAIN
    }
    sets: dict[int, _Verdict] = {}
    for name, value in auth_headers:
        instance = _ARC_INSTANCE.match(value.strip())
        if name != ARC_AUTHENTICATION_RESULTS or instance is None:
            continue
        number = int(instance.group(1))
        authserv, results = _parse_results(value)
        if number in sealed and authserv == CLOUDFLARE_AUTHSERV:
            sets.setdefault(number, _direct_verdict(results) or _Verdict("", ""))
    return sets[min(sets)] if sets else None
