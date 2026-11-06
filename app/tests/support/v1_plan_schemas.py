"""Схеми тулів плану теми v1 (`origin/main` `99a2007`: `agent/prep.py`).

Розгорнуті JSON-схеми (без title / description / default), зняті зі справжнього сервера v1:
контракт-тест порівнює з ними схеми v2.
"""

from typing import Any

V1_PLAN: dict[str, dict[str, Any]] = {
    "prepare_topic_plan": {
        "in": {
            "properties": {"topic_id": {"type": "integer"}},
            "required": ["topic_id"],
            "type": "object",
        },
        "out": {
            "properties": {
                "topic": {
                    "properties": {
                        "topic_id": {"type": "integer"},
                        "slug": {"type": "string"},
                        "title": {"type": "string"},
                        "kind": {
                            "enum": ["tech", "behavioral", "domain"],
                            "type": "string",
                        },
                        "summary": {"type": "string"},
                        "deadline": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                        "priority": {"type": "integer"},
                        "status": {
                            "enum": [
                                "new",
                                "planned",
                                "learning",
                                "practicing",
                                "ready",
                            ],
                            "type": "string",
                        },
                        "steps_done": {"type": "integer"},
                        "steps_total": {"type": "integer"},
                        "minutes_left": {"type": "integer"},
                        "jobs": {
                            "items": {
                                "properties": {
                                    "job_id": {"type": "integer"},
                                    "title": {
                                        "anyOf": [{"type": "string"}, {"type": "null"}]
                                    },
                                    "company": {
                                        "anyOf": [{"type": "string"}, {"type": "null"}]
                                    },
                                    "score": {"type": "integer"},
                                    "gap": {"type": "string"},
                                },
                                "required": [
                                    "job_id",
                                    "title",
                                    "company",
                                    "score",
                                    "gap",
                                ],
                                "type": "object",
                            },
                            "type": "array",
                        },
                        "next_step_id": {
                            "anyOf": [{"type": "integer"}, {"type": "null"}]
                        },
                        "steps": {
                            "items": {
                                "properties": {
                                    "step_id": {"type": "integer"},
                                    "position": {"type": "integer"},
                                    "kind": {
                                        "enum": ["learn", "practice", "check"],
                                        "type": "string",
                                    },
                                    "title": {"type": "string"},
                                    "minutes": {"type": "integer"},
                                    "details": {"type": "string"},
                                    "resources": {
                                        "items": {
                                            "properties": {
                                                "title": {"type": "string"},
                                                "url": {"type": "string"},
                                            },
                                            "required": ["title", "url"],
                                            "type": "object",
                                        },
                                        "type": "array",
                                    },
                                    "done": {
                                        "anyOf": [{"type": "string"}, {"type": "null"}]
                                    },
                                    "note": {"type": "string"},
                                },
                                "required": [
                                    "step_id",
                                    "position",
                                    "kind",
                                    "title",
                                    "minutes",
                                    "details",
                                    "resources",
                                    "done",
                                    "note",
                                ],
                                "type": "object",
                            },
                            "type": "array",
                        },
                    },
                    "required": [
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
                        "next_step_id",
                        "steps",
                    ],
                    "type": "object",
                },
                "rules": {"type": "string"},
            },
            "required": ["topic", "rules"],
            "type": "object",
        },
    },
    "save_topic_plan": {
        "in": {
            "properties": {
                "topic_id": {"type": "integer"},
                "steps": {
                    "items": {
                        "properties": {
                            "kind": {
                                "enum": ["learn", "practice", "check"],
                                "type": "string",
                            },
                            "title": {"type": "string"},
                            "minutes": {"type": "integer"},
                            "details": {"type": "string"},
                            "resources": {
                                "items": {
                                    "properties": {
                                        "title": {"type": "string"},
                                        "url": {"type": "string"},
                                    },
                                    "required": ["title", "url"],
                                    "type": "object",
                                },
                                "type": "array",
                            },
                        },
                        "required": ["kind", "title", "minutes"],
                        "type": "object",
                    },
                    "type": "array",
                },
            },
            "required": ["topic_id", "steps"],
            "type": "object",
        },
        "out": {
            "properties": {
                "topic_id": {"type": "integer"},
                "slug": {"type": "string"},
                "title": {"type": "string"},
                "kind": {"enum": ["tech", "behavioral", "domain"], "type": "string"},
                "summary": {"type": "string"},
                "deadline": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                "priority": {"type": "integer"},
                "status": {
                    "enum": ["new", "planned", "learning", "practicing", "ready"],
                    "type": "string",
                },
                "steps_done": {"type": "integer"},
                "steps_total": {"type": "integer"},
                "minutes_left": {"type": "integer"},
                "jobs": {
                    "items": {
                        "properties": {
                            "job_id": {"type": "integer"},
                            "title": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                            "company": {
                                "anyOf": [{"type": "string"}, {"type": "null"}]
                            },
                            "score": {"type": "integer"},
                            "gap": {"type": "string"},
                        },
                        "required": ["job_id", "title", "company", "score", "gap"],
                        "type": "object",
                    },
                    "type": "array",
                },
                "next_step_id": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
                "steps": {
                    "items": {
                        "properties": {
                            "step_id": {"type": "integer"},
                            "position": {"type": "integer"},
                            "kind": {
                                "enum": ["learn", "practice", "check"],
                                "type": "string",
                            },
                            "title": {"type": "string"},
                            "minutes": {"type": "integer"},
                            "details": {"type": "string"},
                            "resources": {
                                "items": {
                                    "properties": {
                                        "title": {"type": "string"},
                                        "url": {"type": "string"},
                                    },
                                    "required": ["title", "url"],
                                    "type": "object",
                                },
                                "type": "array",
                            },
                            "done": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                            "note": {"type": "string"},
                        },
                        "required": [
                            "step_id",
                            "position",
                            "kind",
                            "title",
                            "minutes",
                            "details",
                            "resources",
                            "done",
                            "note",
                        ],
                        "type": "object",
                    },
                    "type": "array",
                },
            },
            "required": [
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
                "next_step_id",
                "steps",
            ],
            "type": "object",
        },
    },
    "get_topic": {
        "in": {
            "properties": {"topic_id": {"type": "integer"}},
            "required": ["topic_id"],
            "type": "object",
        },
        "out": {
            "properties": {
                "topic_id": {"type": "integer"},
                "slug": {"type": "string"},
                "title": {"type": "string"},
                "kind": {"enum": ["tech", "behavioral", "domain"], "type": "string"},
                "summary": {"type": "string"},
                "deadline": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                "priority": {"type": "integer"},
                "status": {
                    "enum": ["new", "planned", "learning", "practicing", "ready"],
                    "type": "string",
                },
                "steps_done": {"type": "integer"},
                "steps_total": {"type": "integer"},
                "minutes_left": {"type": "integer"},
                "jobs": {
                    "items": {
                        "properties": {
                            "job_id": {"type": "integer"},
                            "title": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                            "company": {
                                "anyOf": [{"type": "string"}, {"type": "null"}]
                            },
                            "score": {"type": "integer"},
                            "gap": {"type": "string"},
                        },
                        "required": ["job_id", "title", "company", "score", "gap"],
                        "type": "object",
                    },
                    "type": "array",
                },
                "next_step_id": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
                "steps": {
                    "items": {
                        "properties": {
                            "step_id": {"type": "integer"},
                            "position": {"type": "integer"},
                            "kind": {
                                "enum": ["learn", "practice", "check"],
                                "type": "string",
                            },
                            "title": {"type": "string"},
                            "minutes": {"type": "integer"},
                            "details": {"type": "string"},
                            "resources": {
                                "items": {
                                    "properties": {
                                        "title": {"type": "string"},
                                        "url": {"type": "string"},
                                    },
                                    "required": ["title", "url"],
                                    "type": "object",
                                },
                                "type": "array",
                            },
                            "done": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                            "note": {"type": "string"},
                        },
                        "required": [
                            "step_id",
                            "position",
                            "kind",
                            "title",
                            "minutes",
                            "details",
                            "resources",
                            "done",
                            "note",
                        ],
                        "type": "object",
                    },
                    "type": "array",
                },
            },
            "required": [
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
                "next_step_id",
                "steps",
            ],
            "type": "object",
        },
    },
    "complete_step": {
        "in": {
            "properties": {"step_id": {"type": "integer"}, "note": {"type": "string"}},
            "required": ["step_id"],
            "type": "object",
        },
        "out": {
            "properties": {
                "topic_id": {"type": "integer"},
                "slug": {"type": "string"},
                "title": {"type": "string"},
                "kind": {"enum": ["tech", "behavioral", "domain"], "type": "string"},
                "summary": {"type": "string"},
                "deadline": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                "priority": {"type": "integer"},
                "status": {
                    "enum": ["new", "planned", "learning", "practicing", "ready"],
                    "type": "string",
                },
                "steps_done": {"type": "integer"},
                "steps_total": {"type": "integer"},
                "minutes_left": {"type": "integer"},
                "jobs": {
                    "items": {
                        "properties": {
                            "job_id": {"type": "integer"},
                            "title": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                            "company": {
                                "anyOf": [{"type": "string"}, {"type": "null"}]
                            },
                            "score": {"type": "integer"},
                            "gap": {"type": "string"},
                        },
                        "required": ["job_id", "title", "company", "score", "gap"],
                        "type": "object",
                    },
                    "type": "array",
                },
                "next_step_id": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
                "steps": {
                    "items": {
                        "properties": {
                            "step_id": {"type": "integer"},
                            "position": {"type": "integer"},
                            "kind": {
                                "enum": ["learn", "practice", "check"],
                                "type": "string",
                            },
                            "title": {"type": "string"},
                            "minutes": {"type": "integer"},
                            "details": {"type": "string"},
                            "resources": {
                                "items": {
                                    "properties": {
                                        "title": {"type": "string"},
                                        "url": {"type": "string"},
                                    },
                                    "required": ["title", "url"],
                                    "type": "object",
                                },
                                "type": "array",
                            },
                            "done": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                            "note": {"type": "string"},
                        },
                        "required": [
                            "step_id",
                            "position",
                            "kind",
                            "title",
                            "minutes",
                            "details",
                            "resources",
                            "done",
                            "note",
                        ],
                        "type": "object",
                    },
                    "type": "array",
                },
            },
            "required": [
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
                "next_step_id",
                "steps",
            ],
            "type": "object",
        },
    },
    "set_topic_ready": {
        "in": {
            "properties": {
                "topic_id": {"type": "integer"},
                "ready": {"type": "boolean"},
            },
            "required": ["topic_id"],
            "type": "object",
        },
        "out": {
            "properties": {
                "topic_id": {"type": "integer"},
                "slug": {"type": "string"},
                "title": {"type": "string"},
                "kind": {"enum": ["tech", "behavioral", "domain"], "type": "string"},
                "summary": {"type": "string"},
                "deadline": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                "priority": {"type": "integer"},
                "status": {
                    "enum": ["new", "planned", "learning", "practicing", "ready"],
                    "type": "string",
                },
                "steps_done": {"type": "integer"},
                "steps_total": {"type": "integer"},
                "minutes_left": {"type": "integer"},
                "jobs": {
                    "items": {
                        "properties": {
                            "job_id": {"type": "integer"},
                            "title": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                            "company": {
                                "anyOf": [{"type": "string"}, {"type": "null"}]
                            },
                            "score": {"type": "integer"},
                            "gap": {"type": "string"},
                        },
                        "required": ["job_id", "title", "company", "score", "gap"],
                        "type": "object",
                    },
                    "type": "array",
                },
                "next_step_id": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
                "steps": {
                    "items": {
                        "properties": {
                            "step_id": {"type": "integer"},
                            "position": {"type": "integer"},
                            "kind": {
                                "enum": ["learn", "practice", "check"],
                                "type": "string",
                            },
                            "title": {"type": "string"},
                            "minutes": {"type": "integer"},
                            "details": {"type": "string"},
                            "resources": {
                                "items": {
                                    "properties": {
                                        "title": {"type": "string"},
                                        "url": {"type": "string"},
                                    },
                                    "required": ["title", "url"],
                                    "type": "object",
                                },
                                "type": "array",
                            },
                            "done": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                            "note": {"type": "string"},
                        },
                        "required": [
                            "step_id",
                            "position",
                            "kind",
                            "title",
                            "minutes",
                            "details",
                            "resources",
                            "done",
                            "note",
                        ],
                        "type": "object",
                    },
                    "type": "array",
                },
            },
            "required": [
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
                "next_step_id",
                "steps",
            ],
            "type": "object",
        },
    },
}
