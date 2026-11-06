"""Схеми тулів тріажу v1 (`origin/main` `99a2007`: `agent/triage.py`).

Розгорнуті JSON-схеми (без title / description / default), зняті зі справжнього сервера v1:
контракт-тест порівнює з ними схеми v2.
"""

from typing import Any

V1: dict[str, dict[str, Any]] = {
    "prepare_triage": {
        "in": {
            "properties": {"limit": {"maximum": 20, "minimum": 1, "type": "integer"}},
            "type": "object",
        },
        "out": {
            "properties": {
                "jobs": {
                    "items": {
                        "properties": {
                            "job_id": {"type": "integer"},
                            "title": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                            "company": {
                                "anyOf": [{"type": "string"}, {"type": "null"}]
                            },
                            "source": {"type": "string"},
                            "job_location": {
                                "anyOf": [{"type": "string"}, {"type": "null"}]
                            },
                            "untrusted_job_text": {"type": "string"},
                        },
                        "required": [
                            "job_id",
                            "title",
                            "company",
                            "source",
                            "job_location",
                            "untrusted_job_text",
                        ],
                        "type": "object",
                    },
                    "type": "array",
                },
                "pending": {"type": "integer"},
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
                "rules": {"type": "string"},
            },
            "required": ["jobs", "pending", "profile", "rules"],
            "type": "object",
        },
    },
    "save_triage": {
        "in": {
            "properties": {
                "items": {
                    "items": {
                        "properties": {
                            "job_id": {"type": "integer"},
                            "score": {"type": "integer"},
                            "verdict": {
                                "enum": ["skip", "maybe", "analyse"],
                                "type": "string",
                            },
                            "reason": {"type": "string"},
                        },
                        "required": ["job_id", "score", "verdict", "reason"],
                        "type": "object",
                    },
                    "maxItems": 20,
                    "type": "array",
                }
            },
            "required": ["items"],
            "type": "object",
        },
        "out": {
            "properties": {
                "saved": {
                    "items": {
                        "properties": {
                            "job_id": {"type": "integer"},
                            "score": {"type": "integer"},
                            "verdict": {
                                "enum": ["skip", "maybe", "analyse"],
                                "type": "string",
                            },
                            "reason": {"type": "string"},
                        },
                        "required": ["job_id", "score", "verdict", "reason"],
                        "type": "object",
                    },
                    "type": "array",
                },
                "analyse": {"items": {"type": "integer"}, "type": "array"},
                "maybe": {"items": {"type": "integer"}, "type": "array"},
                "skip": {"items": {"type": "integer"}, "type": "array"},
            },
            "required": ["saved", "analyse", "maybe", "skip"],
            "type": "object",
        },
    },
}
