"""Схеми тулів квізу v1 (`origin/main` `99a2007`: `agent/quiz.py`).

Розгорнуті JSON-схеми (без title / description / default), зняті зі справжнього сервера v1:
контракт-тест порівнює з ними схеми v2. Тема в `prepare_questions` — та сама, що в плані теми
(`V1_PLAN`). Єдина різниця v2: ключ оцінки `answer_points` лишається лише у відповіді
`due_questions`; у v1 він був у кожному виводі питання.
"""

from typing import Any

from tests.support.v1_plan_schemas import V1_PLAN

_TOPIC = V1_PLAN["prepare_topic_plan"]["out"]["properties"]["topic"]

V1_QUIZ: dict[str, dict[str, Any]] = {
    "prepare_questions": {
        "in": {
            "properties": {"topic_id": {"type": "integer"}},
            "required": ["topic_id"],
            "type": "object",
        },
        "out": {
            "properties": {
                "topic": _TOPIC,
                "questions": {
                    "items": {
                        "properties": {
                            "question_id": {"type": "integer"},
                            "topic_id": {"type": "integer"},
                            "topic_title": {"type": "string"},
                            "question": {"type": "string"},
                            "answer_points": {
                                "items": {"type": "string"},
                                "type": "array",
                            },
                            "box": {"type": "integer"},
                            "due": {"type": "string"},
                        },
                        "required": [
                            "question_id",
                            "topic_id",
                            "topic_title",
                            "question",
                            "answer_points",
                            "box",
                            "due",
                        ],
                        "type": "object",
                    },
                    "type": "array",
                },
                "rules": {"type": "string"},
            },
            "required": ["topic", "questions", "rules"],
            "type": "object",
        },
    },
    "save_questions": {
        "in": {
            "properties": {
                "topic_id": {"type": "integer"},
                "questions": {
                    "items": {
                        "properties": {
                            "question": {"type": "string"},
                            "answer_points": {
                                "items": {"type": "string"},
                                "type": "array",
                            },
                        },
                        "required": ["question", "answer_points"],
                        "type": "object",
                    },
                    "type": "array",
                },
            },
            "required": ["topic_id", "questions"],
            "type": "object",
        },
        "out": {
            "properties": {
                "added": {
                    "items": {
                        "properties": {
                            "question_id": {"type": "integer"},
                            "topic_id": {"type": "integer"},
                            "topic_title": {"type": "string"},
                            "question": {"type": "string"},
                            "answer_points": {
                                "items": {"type": "string"},
                                "type": "array",
                            },
                            "box": {"type": "integer"},
                            "due": {"type": "string"},
                        },
                        "required": [
                            "question_id",
                            "topic_id",
                            "topic_title",
                            "question",
                            "answer_points",
                            "box",
                            "due",
                        ],
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
    "due_questions": {
        "in": {
            "properties": {
                "limit": {"maximum": 50, "minimum": 1, "type": "integer"},
                "topic_id": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
            },
            "type": "object",
        },
        "out": {
            "properties": {
                "questions": {
                    "items": {
                        "properties": {
                            "question_id": {"type": "integer"},
                            "topic_id": {"type": "integer"},
                            "topic_title": {"type": "string"},
                            "question": {"type": "string"},
                            "answer_points": {
                                "items": {"type": "string"},
                                "type": "array",
                            },
                            "box": {"type": "integer"},
                            "due": {"type": "string"},
                        },
                        "required": [
                            "question_id",
                            "topic_id",
                            "topic_title",
                            "question",
                            "answer_points",
                            "box",
                            "due",
                        ],
                        "type": "object",
                    },
                    "type": "array",
                },
                "total_due": {"type": "integer"},
                "rules": {"type": "string"},
            },
            "required": ["questions", "total_due", "rules"],
            "type": "object",
        },
    },
    "record_answer": {
        "in": {
            "properties": {
                "question_id": {"type": "integer"},
                "grade": {"maximum": 5, "minimum": 0, "type": "integer"},
                "answer": {"type": "string"},
                "feedback": {"type": "string"},
            },
            "required": ["question_id", "grade", "answer", "feedback"],
            "type": "object",
        },
        "out": {
            "properties": {
                "question_id": {"type": "integer"},
                "topic_id": {"type": "integer"},
                "topic_title": {"type": "string"},
                "question": {"type": "string"},
                "answer_points": {"items": {"type": "string"}, "type": "array"},
                "box": {"type": "integer"},
                "due": {"type": "string"},
            },
            "required": [
                "question_id",
                "topic_id",
                "topic_title",
                "question",
                "answer_points",
                "box",
                "due",
            ],
            "type": "object",
        },
    },
}
