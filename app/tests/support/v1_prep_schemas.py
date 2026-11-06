"""Схеми тулів тем підготовки v1 (`origin/main` `99a2007`: `agent/prep.py`).

Розгорнуті JSON-схеми (без title / description / default), зняті зі справжнього сервера v1:
контракт-тест порівнює з ними схеми v2. Поля `status`, `steps_done`, `steps_total`,
`minutes_left` у темі лишаються за контрактом v1; значення з кроків плану наповнить K50.
"""

from typing import Any

_NULLABLE_STRING = {"anyOf": [{"type": "string"}, {"type": "null"}]}
_STRINGS = {"items": {"type": "string"}, "type": "array"}

_TOPIC_JOB = {
    "properties": {
        "job_id": {"type": "integer"},
        "title": _NULLABLE_STRING,
        "company": _NULLABLE_STRING,
        "score": {"type": "integer"},
        "gap": {"type": "string"},
    },
    "required": ["job_id", "title", "company", "score", "gap"],
    "type": "object",
}

_TOPIC_FIELDS = [
    "topic_id",
    "slug",
    "title",
    "kind",
    "summary",
    "deadline",
    "priority",
    "status",
    "steps_done",
    "steps_total",
    "minutes_left",
    "jobs",
]

_TOPIC = {
    "properties": {
        "topic_id": {"type": "integer"},
        "slug": {"type": "string"},
        "title": {"type": "string"},
        "kind": {"enum": ["tech", "behavioral", "domain"], "type": "string"},
        "summary": {"type": "string"},
        "deadline": _NULLABLE_STRING,
        "priority": {"type": "integer"},
        "status": {
            "enum": ["new", "planned", "learning", "practicing", "ready"],
            "type": "string",
        },
        "steps_done": {"type": "integer"},
        "steps_total": {"type": "integer"},
        "minutes_left": {"type": "integer"},
        "jobs": {"items": _TOPIC_JOB, "type": "array"},
    },
    "required": _TOPIC_FIELDS,
    "type": "object",
}

_TOPIC_LIST = {
    "properties": {"topics": {"items": _TOPIC, "type": "array"}},
    "required": ["topics"],
    "type": "object",
}

V1: dict[str, dict[str, Any]] = {
    "prepare_prep_topics": {
        "in": {
            "properties": {"job_id": {"type": "integer"}},
            "required": ["job_id"],
            "type": "object",
        },
        "out": {
            "properties": {
                "job": {
                    "properties": {
                        "job_id": {"type": "integer"},
                        "title": _NULLABLE_STRING,
                        "company": _NULLABLE_STRING,
                        "score": {"type": "integer"},
                        "summary": {"type": "string"},
                        "must_have": _STRINGS,
                        "nice_to_have": _STRINGS,
                        "gaps": _STRINGS,
                    },
                    "required": [
                        "job_id",
                        "title",
                        "company",
                        "score",
                        "summary",
                        "must_have",
                        "nice_to_have",
                        "gaps",
                    ],
                    "type": "object",
                },
                "topics": {"items": _TOPIC, "type": "array"},
                "rules": {"type": "string"},
            },
            "required": ["job", "topics", "rules"],
            "type": "object",
        },
    },
    "save_prep_topics": {
        "in": {
            "properties": {
                "job_id": {"type": "integer"},
                "topics": {
                    "items": {
                        "properties": {
                            "slug": {"type": "string"},
                            "title": {"type": "string"},
                            "kind": {
                                "enum": ["tech", "behavioral", "domain"],
                                "type": "string",
                            },
                            "gap": {"type": "string"},
                            "summary": {"type": "string"},
                            "deadline": {"type": "string"},
                        },
                        "required": ["slug", "title", "kind", "gap"],
                        "type": "object",
                    },
                    "type": "array",
                },
            },
            "required": ["job_id", "topics"],
            "type": "object",
        },
        "out": _TOPIC_LIST,
    },
    "list_prep_topics": {
        "in": {"properties": {}, "type": "object"},
        "out": _TOPIC_LIST,
    },
}
