"""Схеми фактових тулів v1 (`origin/main` `99a2007`: `agent/facts.py`).

Розгорнуті JSON-схеми (без title / description / default), зняті зі справжнього сервера v1:
контракт-тест порівнює з ними схеми v2.
"""

from typing import Any

V1: dict[str, dict[str, Any]] = {
    "confirm_facts": {
        "in": {
            "properties": {"fact_ids": {"items": {"type": "integer"}, "type": "array"}},
            "required": ["fact_ids"],
            "type": "object",
        },
        "out": {
            "properties": {
                "facts": {
                    "items": {
                        "properties": {
                            "confirmed": {"type": "boolean"},
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
                        },
                        "required": ["fact_id", "kind", "text", "confirmed"],
                        "type": "object",
                    },
                    "type": "array",
                }
            },
            "required": ["facts"],
            "type": "object",
        },
    },
    "delete_fact": {
        "in": {
            "properties": {"fact_id": {"type": "integer"}},
            "required": ["fact_id"],
            "type": "object",
        },
        "out": {
            "properties": {"deleted": {"type": "integer"}},
            "required": ["deleted"],
            "type": "object",
        },
    },
    "get_original_cv": {
        "in": {"properties": {}, "type": "object"},
        "out": {
            "properties": {
                "file_name": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                "saved": {"type": "string"},
                "text": {"type": "string"},
            },
            "required": ["file_name", "saved", "text"],
            "type": "object",
        },
    },
    "list_facts": {
        "in": {
            "properties": {
                "confirmed": {"anyOf": [{"type": "boolean"}, {"type": "null"}]}
            },
            "type": "object",
        },
        "out": {
            "properties": {
                "facts": {
                    "items": {
                        "properties": {
                            "confirmed": {"type": "boolean"},
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
                        },
                        "required": ["fact_id", "kind", "text", "confirmed"],
                        "type": "object",
                    },
                    "type": "array",
                }
            },
            "required": ["facts"],
            "type": "object",
        },
    },
    "save_facts": {
        "in": {
            "properties": {
                "facts": {
                    "items": {
                        "properties": {
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
                        },
                        "required": ["kind", "text"],
                        "type": "object",
                    },
                    "type": "array",
                }
            },
            "required": ["facts"],
            "type": "object",
        },
        "out": {
            "properties": {
                "added": {
                    "items": {
                        "properties": {
                            "confirmed": {"type": "boolean"},
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
                        },
                        "required": ["fact_id", "kind", "text", "confirmed"],
                        "type": "object",
                    },
                    "type": "array",
                },
                "skipped_duplicates": {"items": {"type": "string"}, "type": "array"},
            },
            "required": ["added", "skipped_duplicates"],
            "type": "object",
        },
    },
    "save_original_cv": {
        "in": {
            "properties": {"file_name": {"type": "string"}, "text": {"type": "string"}},
            "required": ["text"],
            "type": "object",
        },
        "out": {"properties": {"saved": {"type": "boolean"}}, "type": "object"},
    },
    "update_fact": {
        "in": {
            "properties": {
                "fact": {
                    "properties": {
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
                    },
                    "required": ["kind", "text"],
                    "type": "object",
                },
                "fact_id": {"type": "integer"},
            },
            "required": ["fact_id", "fact"],
            "type": "object",
        },
        "out": {
            "properties": {
                "confirmed": {"type": "boolean"},
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
            },
            "required": ["fact_id", "kind", "text", "confirmed"],
            "type": "object",
        },
    },
}
