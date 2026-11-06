"""Схеми тулів відповідей v1 (`origin/main` `99a2007`: `agent/replies.py`).

Розгорнуті JSON-схеми (без title / description / default), зняті зі справжнього сервера v1:
контракт-тест порівнює з ними схеми v2.
"""

from typing import Any

from tests.support.v1_application_schemas import V1 as V1_APPLICATIONS

_TYPES = ["auto_confirmation", "rejection", "invitation", "assignment", "other"]
_STATUSES = ["applied", "replied", "interview", "offer", "rejected", "withdrawn"]
_NULLABLE_STRING: dict[str, Any] = {"anyOf": [{"type": "string"}, {"type": "null"}]}
_JOB: dict[str, Any] = {
    "properties": {
        "job_id": {"type": "integer"},
        "title": _NULLABLE_STRING,
        "company": _NULLABLE_STRING,
        "status": {"anyOf": [{"enum": _STATUSES, "type": "string"}, {"type": "null"}]},
    },
    "required": ["job_id", "title", "company", "status"],
    "type": "object",
}
_FORWARDED: dict[str, Any] = {
    "properties": {
        "untrusted_from_address": {"type": "string"},
        "untrusted_from_name": {"type": "string"},
        "untrusted_subject": {"type": "string"},
    },
    "required": ["untrusted_from_address", "untrusted_from_name", "untrusted_subject"],
    "type": "object",
}
_REPLY: dict[str, Any] = {
    "properties": {
        "reply_id": {"type": "integer"},
        "received": {"type": "string"},
        "from_address": {"type": "string"},
        "sender_auth": {"enum": ["verified", "failed", "unknown"], "type": "string"},
        "untrusted_from_name": {"type": "string"},
        "untrusted_subject": {"type": "string"},
        "untrusted_text": {"type": "string"},
        "text_clipped": {"type": "boolean"},
        "job": {"anyOf": [_JOB, {"type": "null"}]},
        "confidence": {
            "anyOf": [
                {"enum": ["high", "medium", "low"], "type": "string"},
                {"type": "null"},
            ]
        },
        "matched_by": {
            "anyOf": [
                {
                    "enum": ["thread", "email", "domain", "ats", "name"],
                    "type": "string",
                },
                {"type": "null"},
            ]
        },
        "suggested_type": {"enum": _TYPES, "type": "string"},
        "type": {"anyOf": [{"enum": _TYPES, "type": "string"}, {"type": "null"}]},
        "manual_forward": {"anyOf": [_FORWARDED, {"type": "null"}]},
    },
    "required": [
        "reply_id",
        "received",
        "from_address",
        "sender_auth",
        "untrusted_from_name",
        "untrusted_subject",
        "untrusted_text",
        "text_clipped",
        "job",
        "confidence",
        "matched_by",
        "suggested_type",
        "type",
        "manual_forward",
    ],
    "type": "object",
}

V1: dict[str, dict[str, Any]] = {
    "list_replies": {
        "in": {
            "properties": {
                "reviewed": {"type": "boolean"},
                "limit": {"maximum": 50, "minimum": 1, "type": "integer"},
            },
            "type": "object",
        },
        "out": {
            "properties": {
                "replies": {"items": _REPLY, "type": "array"},
                "rules": {"type": "string"},
            },
            "required": ["replies", "rules"],
            "type": "object",
        },
    },
    "review_reply": {
        "in": {
            "properties": {
                "reply_id": {"type": "integer"},
                "type": {"enum": _TYPES, "type": "string"},
                "job_id": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
            },
            "required": ["reply_id", "type"],
            "type": "object",
        },
        "out": {
            "properties": {
                "reply": _REPLY,
                "application": {
                    "anyOf": [
                        V1_APPLICATIONS["set_application_status"]["out"],
                        {"type": "null"},
                    ]
                },
            },
            "required": ["reply", "application"],
            "type": "object",
        },
    },
}

# Описи тулів v1: у v1 вони про іменованого власника; у v2 — про користувача (текст у каталозі промптів).
V1_DESCRIPTIONS = {
    "list_replies": (
        "Company emails from Taras's forwarded mail, matched (or not) to the jobs he applied to, "
        "newest first: not yet reviewed by default. Review them with Taras by the returned rules, "
        "then call review_reply."
    ),
    "review_reply": (
        "Confirm a reply's type and job (job_id null: not about any of Taras's applications). The "
        "application moves forward by the type: rejection → rejected, invitation and assignment → "
        "interview, other → replied, auto_confirmation → no change; never backwards."
    ),
}
