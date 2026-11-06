"""Схеми тулів джерел v1 (`origin/main` `99a2007`: `agent/sources.py`).

Розгорнута JSON-схема (без title / description / default), знята з моделей `SourcesView`, `CompanyView`,
`FeedView`, `RunView`, `FilteredOutView`, `FilteredJobView` і `RefreshRequested` v1: контракт-тест
порівнює з нею схеми v2. Тули v1 без параметрів.
"""

from typing import Any

_STRING_OR_NULL: dict[str, Any] = {"anyOf": [{"type": "string"}, {"type": "null"}]}
_RUN: dict[str, Any] = {
    "properties": {
        "ran_at": {"type": "string"},
        "found": {"type": "integer"},
        "imported": {"type": "integer"},
        "filtered": {"type": "integer"},
        "duplicate": {"type": "integer"},
        "completed": {"type": "integer"},
        "error": _STRING_OR_NULL,
    },
    "required": [
        "ran_at",
        "found",
        "imported",
        "filtered",
        "duplicate",
        "completed",
        "error",
    ],
    "type": "object",
}
_LAST_RUN: dict[str, Any] = {"anyOf": [_RUN, {"type": "null"}]}
_COMPANY: dict[str, Any] = {
    "properties": {
        "name": {"type": "string"},
        "platform": {"type": "string"},
        "slug": {"type": "string"},
        "enabled": {"type": "boolean"},
        "last_run": _LAST_RUN,
    },
    "required": ["name", "platform", "slug", "enabled", "last_run"],
    "type": "object",
}
_FEED: dict[str, Any] = {
    "properties": {
        "source": {"type": "string"},
        "query": {"type": "string"},
        "enabled": {"type": "boolean"},
        "last_run": _LAST_RUN,
    },
    "required": ["source", "query", "enabled", "last_run"],
    "type": "object",
}
_FILTERED_JOB: dict[str, Any] = {
    "properties": {
        "job_id": {"type": "integer"},
        "title": _STRING_OR_NULL,
        "company": _STRING_OR_NULL,
        "reason": {"type": "string"},
    },
    "required": ["job_id", "title", "company", "reason"],
    "type": "object",
}

V1: dict[str, dict[str, Any]] = {
    "get_sources": {
        "in": {"properties": {}, "type": "object"},
        "out": {
            "properties": {
                "companies": {"items": _COMPANY, "type": "array"},
                "feeds": {"items": _FEED, "type": "array"},
                "refresh_requests_left": {"type": "integer"},
                "next_refresh_at": _STRING_OR_NULL,
                "filtered_out": {
                    "properties": {
                        "count": {"type": "integer"},
                        "jobs": {"items": _FILTERED_JOB, "type": "array"},
                    },
                    "required": ["count", "jobs"],
                    "type": "object",
                },
                "settings_url": {"type": "string"},
            },
            "required": [
                "companies",
                "feeds",
                "refresh_requests_left",
                "next_refresh_at",
                "filtered_out",
                "settings_url",
            ],
            "type": "object",
        },
    },
    "refresh_sources": {
        "in": {"properties": {}, "type": "object"},
        "out": {
            "properties": {
                "requested": {"type": "boolean"},
                "refresh_requests_left": {"type": "integer"},
                "message": {"type": "string"},
            },
            "required": ["refresh_requests_left", "message"],
            "type": "object",
        },
    },
}
