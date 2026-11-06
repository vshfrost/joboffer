"""Правила гранту: єдиний scope (його перевіряє SDK), привʼязка до resource, строки життя."""

from datetime import timedelta

from domain.oauth.errors import InvalidTarget

SCOPE = "joboffer"
CODE_TTL = timedelta(minutes=5)
ACCESS_TTL = timedelta(hours=1)
REFRESH_TTL = timedelta(days=30)
# Скільки живе запит між /authorize і входом користувача (rid).
PENDING_TTL = timedelta(minutes=10)


def ensure_resource(requested: str | None, expected: str) -> str:
    """`None` — клієнт не просив resource: грант привʼязується до нашого. Інший — `InvalidTarget`."""
    if requested is not None and requested != expected:
        raise InvalidTarget("Непідтримуваний resource")
    return expected
