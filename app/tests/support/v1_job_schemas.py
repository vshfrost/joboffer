"""Схеми тулів вакансій v1 (`origin/main` `99a2007`: `agent/server.py`, `agent/dismiss.py`).

Розгорнуті JSON-схеми (без title / description / default), зняті зі справжнього сервера v1:
контракт-тест порівнює з ними схеми v2.
"""

from typing import Any

V1: dict[str, dict[str, Any]] = {
    "add_job": {
        "in": {
            "properties": {
                "text": {"type": "string"},
                "url": {"type": "string"},
                "title": {"type": "string"},
                "company": {"type": "string"},
            },
            "required": ["text"],
            "type": "object",
        },
        "out": {
            "properties": {
                "job_id": {"type": "integer"},
                "duplicate": {"type": "boolean"},
            },
            "required": ["job_id", "duplicate"],
            "type": "object",
        },
    },
    "get_job": {
        "in": {
            "properties": {"job_id": {"type": "integer"}},
            "required": ["job_id"],
            "type": "object",
        },
        "out": {
            "properties": {
                "job_id": {"type": "integer"},
                "title": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                "company": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                "url": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                "source": {"type": "string"},
                "added": {"type": "string"},
                "needs_text": {"type": "boolean"},
                "untrusted_job_text": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                "dismissed": {"type": "boolean"},
                "dismiss_reason": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                "application": {
                    "anyOf": [
                        {
                            "properties": {
                                "job_id": {"type": "integer"},
                                "status": {
                                    "enum": [
                                        "applied",
                                        "replied",
                                        "interview",
                                        "offer",
                                        "rejected",
                                        "withdrawn",
                                    ],
                                    "type": "string",
                                },
                                "applied_on": {"type": "string"},
                                "channel": {
                                    "enum": ["email", "ats", "linkedin", "referral"],
                                    "type": "string",
                                },
                                "ats": {
                                    "anyOf": [
                                        {
                                            "enum": [
                                                "greenhouse",
                                                "lever",
                                                "ashby",
                                                "workable",
                                                "smartrecruiters",
                                                "other",
                                            ],
                                            "type": "string",
                                        },
                                        {"type": "null"},
                                    ]
                                },
                                "company_domains": {
                                    "items": {"type": "string"},
                                    "type": "array",
                                },
                                "company_emails": {
                                    "items": {"type": "string"},
                                    "type": "array",
                                },
                                "status_changed": {"type": "string"},
                            },
                            "required": [
                                "job_id",
                                "status",
                                "applied_on",
                                "channel",
                                "ats",
                                "company_domains",
                                "company_emails",
                                "status_changed",
                            ],
                            "type": "object",
                        },
                        {"type": "null"},
                    ]
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
                "application",
            ],
            "type": "object",
        },
    },
    "list_jobs": {
        "in": {
            "properties": {
                "filters": {
                    "anyOf": [
                        {
                            "properties": {
                                "query": {"type": "string"},
                                "days": {
                                    "anyOf": [{"type": "integer"}, {"type": "null"}]
                                },
                                "source": {"type": "string"},
                                "work_mode": {
                                    "anyOf": [
                                        {
                                            "enum": ["remote", "hybrid", "onsite"],
                                            "type": "string",
                                        },
                                        {"type": "null"},
                                    ]
                                },
                                "status": {
                                    "anyOf": [
                                        {
                                            "enum": [
                                                "applied",
                                                "replied",
                                                "interview",
                                                "offer",
                                                "rejected",
                                                "withdrawn",
                                            ],
                                            "type": "string",
                                        },
                                        {"type": "null"},
                                    ]
                                },
                                "needs_text": {"type": "boolean"},
                                "triage_verdict": {
                                    "anyOf": [
                                        {
                                            "enum": ["skip", "maybe", "analyse"],
                                            "type": "string",
                                        },
                                        {"type": "null"},
                                    ]
                                },
                                "dismissed": {"type": "boolean"},
                            },
                            "type": "object",
                        },
                        {"type": "null"},
                    ]
                },
                "limit": {"maximum": 200, "minimum": 1, "type": "integer"},
            },
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
                            "url": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                            "source": {"type": "string"},
                            "added": {"type": "string"},
                            "score": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
                            "filters_passed": {
                                "anyOf": [{"type": "boolean"}, {"type": "null"}]
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
                            "status": {
                                "anyOf": [
                                    {
                                        "enum": [
                                            "applied",
                                            "replied",
                                            "interview",
                                            "offer",
                                            "rejected",
                                            "withdrawn",
                                        ],
                                        "type": "string",
                                    },
                                    {"type": "null"},
                                ]
                            },
                            "needs_text": {"type": "boolean"},
                            "triage_score": {
                                "anyOf": [{"type": "integer"}, {"type": "null"}]
                            },
                            "triage_verdict": {
                                "anyOf": [
                                    {
                                        "enum": ["skip", "maybe", "analyse"],
                                        "type": "string",
                                    },
                                    {"type": "null"},
                                ]
                            },
                            "dismissed": {"type": "boolean"},
                        },
                        "required": [
                            "job_id",
                            "title",
                            "company",
                            "url",
                            "source",
                            "added",
                            "score",
                            "filters_passed",
                            "work_mode",
                            "status",
                            "needs_text",
                            "triage_score",
                            "triage_verdict",
                            "dismissed",
                        ],
                        "type": "object",
                    },
                    "type": "array",
                }
            },
            "required": ["jobs"],
            "type": "object",
        },
    },
    "dismiss_jobs": {
        "in": {
            "properties": {
                "job_ids": {
                    "items": {"type": "integer"},
                    "maxItems": 50,
                    "type": "array",
                },
                "reason": {"maxLength": 200, "type": "string"},
            },
            "required": ["job_ids", "reason"],
            "type": "object",
        },
        "out": {
            "properties": {
                "dismissed": {"items": {"type": "integer"}, "type": "array"}
            },
            "required": ["dismissed"],
            "type": "object",
        },
    },
    "restore_job": {
        "in": {
            "properties": {"job_id": {"type": "integer"}},
            "required": ["job_id"],
            "type": "object",
        },
        "out": {
            "properties": {"job_id": {"type": "integer"}},
            "required": ["job_id"],
            "type": "object",
        },
    },
}
