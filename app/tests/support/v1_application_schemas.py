"""Схеми тулів подач v1 (`origin/main` `99a2007`: `agent/applications.py`).

Розгорнуті JSON-схеми (без title / description / default), зняті зі справжнього сервера v1:
контракт-тест порівнює з ними схеми v2.
"""

from typing import Any

V1: dict[str, dict[str, Any]] = {
    "mark_applied": {
        "in": {
            "properties": {
                "job_id": {"type": "integer"},
                "application": {
                    "properties": {
                        "channel": {
                            "enum": ["email", "ats", "linkedin", "referral"],
                            "type": "string",
                        },
                        "applied_on": {"type": "string"},
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
                    },
                    "required": ["channel"],
                    "type": "object",
                },
            },
            "required": ["job_id", "application"],
            "type": "object",
        },
        "out": {
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
                "company_domains": {"items": {"type": "string"}, "type": "array"},
                "company_emails": {"items": {"type": "string"}, "type": "array"},
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
    },
    "set_application_status": {
        "in": {
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
            },
            "required": ["job_id", "status"],
            "type": "object",
        },
        "out": {
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
                "company_domains": {"items": {"type": "string"}, "type": "array"},
                "company_emails": {"items": {"type": "string"}, "type": "array"},
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
    },
}
