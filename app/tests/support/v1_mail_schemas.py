"""Схема тула пошти v1 (`origin/main` `99a2007`: `agent/mail.py`, `agent/replies.py`).

Розгорнута JSON-схема (без title / description / default), знята з моделей `MailInboxView`,
`MailView`, `MailDropsView`, `ForwardedView` v1: контракт-тест порівнює з нею схеми v2.
"""

from typing import Any

_CATEGORIES = [
    "company",
    "linkedin_alert",
    "linkedin_application",
    "linkedin_message",
    "forwarding_confirmation",
    "suspicious",
    "other",
]
_DROPS: dict[str, Any] = {
    "properties": {
        "count": {"type": "integer"},
        "last_received": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "required": ["count", "last_received"],
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
_MAIL: dict[str, Any] = {
    "properties": {
        "received": {"type": "string"},
        "from_address": {"type": "string"},
        "untrusted_from_name": {"type": "string"},
        "untrusted_subject": {"type": "string"},
        "category": {"enum": _CATEGORIES, "type": "string"},
        "sender_auth": {"enum": ["verified", "failed", "unknown"], "type": "string"},
        "manual_forward": {"anyOf": [_FORWARDED, {"type": "null"}]},
    },
    "required": [
        "received",
        "from_address",
        "untrusted_from_name",
        "untrusted_subject",
        "category",
        "sender_auth",
        "manual_forward",
    ],
    "type": "object",
}

V1: dict[str, dict[str, Any]] = {
    "get_mail_inbox": {
        "in": {"properties": {}, "type": "object"},
        "out": {
            "properties": {
                "forwarding_address": {"type": "string"},
                "forwarding_code": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                "forwarding_link_only": {"type": "boolean"},
                "forwarding_requested_by": {"type": "string"},
                "recent": {"items": _MAIL, "type": "array"},
                "last_synced": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                "sync_failed": {"type": "boolean"},
                "daily_limit_drops": _DROPS,
                "old_address_drops": _DROPS,
                "suspicious_mail": _DROPS,
                "settings_url": {"type": "string"},
            },
            "required": [
                "forwarding_address",
                "forwarding_code",
                "forwarding_link_only",
                "forwarding_requested_by",
                "recent",
                "last_synced",
                "sync_failed",
                "daily_limit_drops",
                "old_address_drops",
                "suspicious_mail",
                "settings_url",
            ],
            "type": "object",
        },
    },
}
