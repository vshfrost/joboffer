"""Схеми тулів пакета до інтерв'ю v1 (`origin/main` `99a2007`: `agent/interview.py`).

Розгорнуті JSON-схеми (без title / description / default), зняті зі справжнього сервера v1:
контракт-тест порівнює з ними схеми v2. Вакансія, аналіз, факти й теми в брифі — ті самі, що в
брифі CV (`V1_DOCUMENTS`) і в списку тем (`V1_TOPICS`). Різниць зі схемами v1 нема.
"""

from typing import Any

from tests.support.v1_document_schemas import V1 as V1_DOCUMENTS
from tests.support.v1_prep_schemas import V1 as V1_TOPICS

_BRIEF = V1_DOCUMENTS["prepare_cv"]["out"]["properties"]
_KIT: dict[str, Any] = {
    "properties": {
        "kit_id": {"type": "integer"},
        "job_id": {"type": "integer"},
        "version": {"type": "integer"},
        "created": {"type": "string"},
        "questions": {
            "items": {
                "properties": {
                    "kind": {"enum": ["technical", "behavioral"], "type": "string"},
                    "question": {"type": "string"},
                    "topic_id": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
                },
                "required": ["kind", "question"],
                "type": "object",
            },
            "type": "array",
        },
        "stories": {
            "items": {
                "properties": {
                    "title": {"type": "string"},
                    "situation": {"type": "string"},
                    "task": {"type": "string"},
                    "action": {"type": "string"},
                    "result": {"type": "string"},
                    "fact_ids": {"items": {"type": "integer"}, "type": "array"},
                },
                "required": [
                    "title",
                    "situation",
                    "task",
                    "action",
                    "result",
                    "fact_ids",
                ],
                "type": "object",
            },
            "type": "array",
        },
        "company_questions": {"items": {"type": "string"}, "type": "array"},
    },
    "required": [
        "kit_id",
        "job_id",
        "version",
        "created",
        "questions",
        "stories",
        "company_questions",
    ],
    "type": "object",
}

V1_KIT: dict[str, dict[str, Any]] = {
    "prepare_interview_kit": {
        "in": {
            "properties": {"job_id": {"type": "integer"}},
            "required": ["job_id"],
            "type": "object",
        },
        "out": {
            "properties": {
                "job": _BRIEF["job"],
                "analysis": _BRIEF["analysis"],
                "topics": V1_TOPICS["list_prep_topics"]["out"]["properties"]["topics"],
                "confirmed_facts": _BRIEF["confirmed_facts"],
                "rules": {"type": "string"},
                "previous": {"anyOf": [_KIT, {"type": "null"}]},
            },
            "required": [
                "job",
                "analysis",
                "topics",
                "confirmed_facts",
                "rules",
                "previous",
            ],
            "type": "object",
        },
    },
    "save_interview_kit": {
        "in": {
            "properties": {
                "job_id": {"type": "integer"},
                "questions": {
                    "items": {
                        "properties": {
                            "kind": {
                                "enum": ["technical", "behavioral"],
                                "type": "string",
                            },
                            "question": {"type": "string"},
                            "topic_id": {
                                "anyOf": [{"type": "integer"}, {"type": "null"}]
                            },
                        },
                        "required": ["kind", "question"],
                        "type": "object",
                    },
                    "type": "array",
                },
                "stories": {
                    "items": {
                        "properties": {
                            "title": {"type": "string"},
                            "situation": {"type": "string"},
                            "task": {"type": "string"},
                            "action": {"type": "string"},
                            "result": {"type": "string"},
                            "fact_ids": {"items": {"type": "integer"}, "type": "array"},
                        },
                        "required": [
                            "title",
                            "situation",
                            "task",
                            "action",
                            "result",
                            "fact_ids",
                        ],
                        "type": "object",
                    },
                    "type": "array",
                },
                "company_questions": {"items": {"type": "string"}, "type": "array"},
            },
            "required": ["job_id", "questions", "stories", "company_questions"],
            "type": "object",
        },
        "out": _KIT,
    },
}
