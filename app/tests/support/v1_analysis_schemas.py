"""Схеми тулів аналізу v1 (`origin/main` `99a2007`: `agent/analysis.py`).

Розгорнуті JSON-схеми (без title / description / default), зняті зі справжнього сервера v1:
контракт-тест порівнює з ними схеми v2. Єдина різниця з v1 — `gaps` (задача 4ec6e2): на вході
об'єкт `{gap, question}` або рядок (старий формат), на виході об'єкт `{number, gap, question}`.
Друга різниця — `gap_answers` у брифі `prepare_analysis` (задача a0f389): відповіді користувача
на прогалини вакансії, `[{gap, has_experience, fact_ids, answered}]`.
Третя — `keyword_facts` на вході `save_analysis` (ATS-2): ключове слово → номери фактів під ним.
"""

from typing import Any

_NULLABLE_STRING = {"anyOf": [{"type": "string"}, {"type": "null"}]}
GAPS_IN: dict[str, Any] = {
    "items": {
        "anyOf": [
            {
                "properties": {"gap": {"type": "string"}, "question": _NULLABLE_STRING},
                "required": ["gap"],
                "type": "object",
            },
            {"type": "string"},
        ]
    },
    "type": "array",
}
KEYWORD_FACTS_IN: dict[str, Any] = {
    "anyOf": [
        {
            "additionalProperties": {"items": {"type": "integer"}, "type": "array"},
            "type": "object",
        },
        {"type": "null"},
    ]
}
GAP_ANSWERS_OUT: dict[str, Any] = {
    "items": {
        "properties": {
            "gap": {"type": "string"},
            "has_experience": {"type": "boolean"},
            "fact_ids": {"items": {"type": "integer"}, "type": "array"},
            "answered": {"type": "string"},
        },
        "required": ["gap", "has_experience", "fact_ids", "answered"],
        "type": "object",
    },
    "type": "array",
}
GAPS_OUT: dict[str, Any] = {
    "items": {
        "properties": {
            "number": {"type": "integer"},
            "gap": {"type": "string"},
            "question": _NULLABLE_STRING,
        },
        "required": ["number", "gap", "question"],
        "type": "object",
    },
    "type": "array",
}

V1: dict[str, dict[str, Any]] = {
    "prepare_analysis": {
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
                        "title": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                        "company": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                        "url": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                        "source": {"type": "string"},
                        "added": {"type": "string"},
                        "needs_text": {"type": "boolean"},
                        "untrusted_job_text": {
                            "anyOf": [{"type": "string"}, {"type": "null"}]
                        },
                        "dismissed": {"type": "boolean"},
                        "dismiss_reason": {
                            "anyOf": [{"type": "string"}, {"type": "null"}]
                        },
                    },
                    "required": [
                        "job_id",
                        "title",
                        "company",
                        "url",
                        "source",
                        "added",
                        "needs_text",
                        "untrusted_job_text",
                    ],
                    "type": "object",
                },
                "profile": {
                    "properties": {
                        "roles": {"items": {"type": "string"}, "type": "array"},
                        "work_modes": {
                            "items": {
                                "enum": ["remote", "hybrid", "onsite"],
                                "type": "string",
                            },
                            "type": "array",
                        },
                        "locations": {
                            "items": {
                                "properties": {
                                    "place": {"type": "string"},
                                    "aliases": {
                                        "items": {"type": "string"},
                                        "type": "array",
                                    },
                                    "work_modes": {
                                        "items": {
                                            "enum": ["remote", "hybrid", "onsite"],
                                            "type": "string",
                                        },
                                        "minItems": 1,
                                        "type": "array",
                                    },
                                },
                                "required": ["place", "work_modes"],
                                "type": "object",
                            },
                            "type": "array",
                        },
                        "include_unknown_mode": {"type": "boolean"},
                        "relocation": {"type": "boolean"},
                        "target_domains": {
                            "items": {"type": "string"},
                            "type": "array",
                        },
                        "seniority": {
                            "items": {
                                "enum": [
                                    "junior",
                                    "middle",
                                    "senior",
                                    "lead",
                                    "principal",
                                ],
                                "type": "string",
                            },
                            "type": "array",
                        },
                        "min_salary_eur": {
                            "anyOf": [{"type": "integer"}, {"type": "null"}]
                        },
                        "stop_words": {"items": {"type": "string"}, "type": "array"},
                        "title_keywords": {
                            "items": {"type": "string"},
                            "type": "array",
                        },
                        "title_exclude": {"items": {"type": "string"}, "type": "array"},
                        "full_name": {"type": "string"},
                        "email": {"type": "string"},
                        "phone": {"type": "string"},
                        "linkedin_url": {"type": "string"},
                        "city": {"type": "string"},
                        "github_url": {"type": "string"},
                        "work_authorization": {"type": "string"},
                    },
                    "type": "object",
                },
                "confirmed_facts": {
                    "items": {
                        "properties": {
                            "fact_id": {"type": "integer"},
                            "kind": {
                                "enum": [
                                    "experience",
                                    "achievement",
                                    "project",
                                    "skill",
                                    "education",
                                    "language",
                                ],
                                "type": "string",
                            },
                            "text": {"type": "string"},
                            "confirmed": {"type": "boolean"},
                        },
                        "required": ["fact_id", "kind", "text", "confirmed"],
                        "type": "object",
                    },
                    "type": "array",
                },
                "rubric": {"type": "string"},
                "previous": {
                    "anyOf": [
                        {
                            "properties": {
                                "score": {
                                    "maximum": 100,
                                    "minimum": 0,
                                    "type": "integer",
                                },
                                "summary": {"type": "string"},
                                "must_have": {
                                    "items": {"type": "string"},
                                    "type": "array",
                                },
                                "nice_to_have": {
                                    "items": {"type": "string"},
                                    "type": "array",
                                },
                                "keywords": {
                                    "items": {"type": "string"},
                                    "type": "array",
                                },
                                "seniority": {
                                    "anyOf": [
                                        {
                                            "enum": [
                                                "junior",
                                                "middle",
                                                "senior",
                                                "lead",
                                                "principal",
                                            ],
                                            "type": "string",
                                        },
                                        {"type": "null"},
                                    ]
                                },
                                "work_mode": {
                                    "anyOf": [
                                        {
                                            "enum": ["remote", "hybrid", "onsite"],
                                            "type": "string",
                                        },
                                        {"type": "null"},
                                    ]
                                },
                                "location": {
                                    "anyOf": [{"type": "string"}, {"type": "null"}]
                                },
                                "languages": {
                                    "items": {"type": "string"},
                                    "type": "array",
                                },
                                "salary_min_eur": {
                                    "anyOf": [{"type": "integer"}, {"type": "null"}]
                                },
                                "salary_max_eur": {
                                    "anyOf": [{"type": "integer"}, {"type": "null"}]
                                },
                                "relocation": {
                                    "anyOf": [{"type": "boolean"}, {"type": "null"}]
                                },
                                "reasons": {
                                    "items": {"type": "string"},
                                    "type": "array",
                                },
                                "gaps": GAPS_OUT,
                                "job_id": {"type": "integer"},
                                "filters_passed": {"type": "boolean"},
                                "flags": {"items": {"type": "string"}, "type": "array"},
                                "updated": {"type": "string"},
                            },
                            "required": [
                                "score",
                                "summary",
                                "job_id",
                                "filters_passed",
                                "flags",
                                "updated",
                            ],
                            "type": "object",
                        },
                        {"type": "null"},
                    ]
                },
                "gap_answers": GAP_ANSWERS_OUT,
            },
            "required": [
                "job",
                "profile",
                "confirmed_facts",
                "rubric",
                "previous",
                "gap_answers",
            ],
            "type": "object",
        },
    },
    "save_analysis": {
        "in": {
            "properties": {
                "job_id": {"type": "integer"},
                "analysis": {
                    "properties": {
                        "score": {"maximum": 100, "minimum": 0, "type": "integer"},
                        "summary": {"type": "string"},
                        "must_have": {"items": {"type": "string"}, "type": "array"},
                        "nice_to_have": {"items": {"type": "string"}, "type": "array"},
                        "keywords": {"items": {"type": "string"}, "type": "array"},
                        "seniority": {
                            "anyOf": [
                                {
                                    "enum": [
                                        "junior",
                                        "middle",
                                        "senior",
                                        "lead",
                                        "principal",
                                    ],
                                    "type": "string",
                                },
                                {"type": "null"},
                            ]
                        },
                        "work_mode": {
                            "anyOf": [
                                {
                                    "enum": ["remote", "hybrid", "onsite"],
                                    "type": "string",
                                },
                                {"type": "null"},
                            ]
                        },
                        "location": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                        "languages": {"items": {"type": "string"}, "type": "array"},
                        "salary_min_eur": {
                            "anyOf": [{"type": "integer"}, {"type": "null"}]
                        },
                        "salary_max_eur": {
                            "anyOf": [{"type": "integer"}, {"type": "null"}]
                        },
                        "relocation": {
                            "anyOf": [{"type": "boolean"}, {"type": "null"}]
                        },
                        "reasons": {"items": {"type": "string"}, "type": "array"},
                        "gaps": GAPS_IN,
                        "keyword_facts": KEYWORD_FACTS_IN,
                    },
                    "required": ["score", "summary"],
                    "type": "object",
                },
            },
            "required": ["job_id", "analysis"],
            "type": "object",
        },
        "out": {
            "properties": {
                "score": {"maximum": 100, "minimum": 0, "type": "integer"},
                "summary": {"type": "string"},
                "must_have": {"items": {"type": "string"}, "type": "array"},
                "nice_to_have": {"items": {"type": "string"}, "type": "array"},
                "keywords": {"items": {"type": "string"}, "type": "array"},
                "seniority": {
                    "anyOf": [
                        {
                            "enum": ["junior", "middle", "senior", "lead", "principal"],
                            "type": "string",
                        },
                        {"type": "null"},
                    ]
                },
                "work_mode": {
                    "anyOf": [
                        {"enum": ["remote", "hybrid", "onsite"], "type": "string"},
                        {"type": "null"},
                    ]
                },
                "location": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                "languages": {"items": {"type": "string"}, "type": "array"},
                "salary_min_eur": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
                "salary_max_eur": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
                "relocation": {"anyOf": [{"type": "boolean"}, {"type": "null"}]},
                "reasons": {"items": {"type": "string"}, "type": "array"},
                "gaps": GAPS_OUT,
                "job_id": {"type": "integer"},
                "filters_passed": {"type": "boolean"},
                "flags": {"items": {"type": "string"}, "type": "array"},
                "updated": {"type": "string"},
            },
            "required": [
                "score",
                "summary",
                "job_id",
                "filters_passed",
                "flags",
                "updated",
            ],
            "type": "object",
        },
    },
}
