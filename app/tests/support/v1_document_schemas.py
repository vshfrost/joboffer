"""Схеми тулів документів v1 (`origin/main` `99a2007`: `agent/documents.py`).

Розгорнуті JSON-схеми (без title / description / default), зняті зі справжнього сервера v1 разом із полями фото
(`photo_id`, `photos`): контракт-тест порівнює з ними схеми v2 повністю. Після v1 в аналізі брифів додано `candidate_asks` (63d7b9) і `gap_analogues` (ecd42c).
"""

from typing import Any

from tests.support.v1_analysis_schemas import GAP_ANALOGUES_OUT, GAPS_OUT

V1: dict[str, dict[str, Any]] = {
    "prepare_cv": {
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
                "analysis": {
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
                                "candidate_asks": {
                                    "items": {"type": "string"},
                                    "type": "array",
                                },
                                "gaps": GAPS_OUT,
                                "gap_analogues": GAP_ANALOGUES_OUT,
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
                "rules": {"type": "string"},
                "previous": {
                    "anyOf": [
                        {
                            "properties": {
                                "document_id": {"type": "integer"},
                                "job_id": {"type": "integer"},
                                "kind": {"enum": ["cv", "cl"], "type": "string"},
                                "version": {"type": "integer"},
                                "created": {"type": "string"},
                                "pdf_url": {"type": "string"},
                                "cv": {
                                    "anyOf": [
                                        {
                                            "properties": {
                                                "headline": {
                                                    "properties": {
                                                        "text": {"type": "string"},
                                                        "fact_ids": {
                                                            "items": {
                                                                "type": "integer"
                                                            },
                                                            "type": "array",
                                                        },
                                                    },
                                                    "required": ["text", "fact_ids"],
                                                    "type": "object",
                                                },
                                                "summary": {
                                                    "properties": {
                                                        "text": {"type": "string"},
                                                        "fact_ids": {
                                                            "items": {
                                                                "type": "integer"
                                                            },
                                                            "type": "array",
                                                        },
                                                    },
                                                    "required": ["text", "fact_ids"],
                                                    "type": "object",
                                                },
                                                "sections": {
                                                    "items": {
                                                        "properties": {
                                                            "name": {
                                                                "enum": [
                                                                    "Experience",
                                                                    "Projects",
                                                                    "Achievements",
                                                                    "Skills",
                                                                    "Education",
                                                                    "Education "
                                                                    "and "
                                                                    "Languages",
                                                                    "Certifications",
                                                                    "Languages",
                                                                ],
                                                                "type": "string",
                                                            },
                                                            "entries": {
                                                                "items": {
                                                                    "properties": {
                                                                        "heading": {
                                                                            "properties": {
                                                                                "text": {
                                                                                    "type": "string"
                                                                                },
                                                                                "fact_ids": {
                                                                                    "items": {
                                                                                        "type": "integer"
                                                                                    },
                                                                                    "type": "array",
                                                                                },
                                                                            },
                                                                            "required": [
                                                                                "text",
                                                                                "fact_ids",
                                                                            ],
                                                                            "type": "object",
                                                                        },
                                                                        "meta": {
                                                                            "anyOf": [
                                                                                {
                                                                                    "properties": {
                                                                                        "text": {
                                                                                            "type": "string"
                                                                                        },
                                                                                        "fact_ids": {
                                                                                            "items": {
                                                                                                "type": "integer"
                                                                                            },
                                                                                            "type": "array",
                                                                                        },
                                                                                    },
                                                                                    "required": [
                                                                                        "text",
                                                                                        "fact_ids",
                                                                                    ],
                                                                                    "type": "object",
                                                                                },
                                                                                {
                                                                                    "type": "null"
                                                                                },
                                                                            ]
                                                                        },
                                                                        "subtitle": {
                                                                            "anyOf": [
                                                                                {
                                                                                    "properties": {
                                                                                        "text": {
                                                                                            "type": "string"
                                                                                        },
                                                                                        "fact_ids": {
                                                                                            "items": {
                                                                                                "type": "integer"
                                                                                            },
                                                                                            "type": "array",
                                                                                        },
                                                                                    },
                                                                                    "required": [
                                                                                        "text",
                                                                                        "fact_ids",
                                                                                    ],
                                                                                    "type": "object",
                                                                                },
                                                                                {
                                                                                    "type": "null"
                                                                                },
                                                                            ]
                                                                        },
                                                                        "bullets": {
                                                                            "items": {
                                                                                "properties": {
                                                                                    "text": {
                                                                                        "type": "string"
                                                                                    },
                                                                                    "fact_ids": {
                                                                                        "items": {
                                                                                            "type": "integer"
                                                                                        },
                                                                                        "type": "array",
                                                                                    },
                                                                                },
                                                                                "required": [
                                                                                    "text",
                                                                                    "fact_ids",
                                                                                ],
                                                                                "type": "object",
                                                                            },
                                                                            "type": "array",
                                                                        },
                                                                    },
                                                                    "required": [
                                                                        "heading"
                                                                    ],
                                                                    "type": "object",
                                                                },
                                                                "type": "array",
                                                            },
                                                        },
                                                        "required": ["name", "entries"],
                                                        "type": "object",
                                                    },
                                                    "type": "array",
                                                },
                                            },
                                            "required": [
                                                "headline",
                                                "summary",
                                                "sections",
                                            ],
                                            "type": "object",
                                        },
                                        {"type": "null"},
                                    ]
                                },
                                "cover_letter": {
                                    "anyOf": [
                                        {
                                            "properties": {
                                                "text": {"type": "string"},
                                                "fact_ids": {
                                                    "items": {"type": "integer"},
                                                    "type": "array",
                                                },
                                            },
                                            "required": ["text", "fact_ids"],
                                            "type": "object",
                                        },
                                        {"type": "null"},
                                    ]
                                },
                                "lint": {
                                    "anyOf": [
                                        {
                                            "properties": {
                                                "passed": {"type": "boolean"},
                                                "pages": {"type": "integer"},
                                                "issues": {
                                                    "items": {
                                                        "properties": {
                                                            "code": {"type": "string"},
                                                            "message": {
                                                                "type": "string"
                                                            },
                                                        },
                                                        "required": ["code", "message"],
                                                        "type": "object",
                                                    },
                                                    "type": "array",
                                                },
                                                "keywords_covered": {
                                                    "anyOf": [
                                                        {
                                                            "items": {"type": "string"},
                                                            "type": "array",
                                                        },
                                                        {"type": "null"},
                                                    ]
                                                },
                                                "keywords_missing": {
                                                    "anyOf": [
                                                        {
                                                            "items": {"type": "string"},
                                                            "type": "array",
                                                        },
                                                        {"type": "null"},
                                                    ]
                                                },
                                                "keyword_coverage_percent": {
                                                    "anyOf": [
                                                        {"type": "integer"},
                                                        {"type": "null"},
                                                    ]
                                                },
                                            },
                                            "required": [
                                                "passed",
                                                "pages",
                                                "issues",
                                                "keywords_covered",
                                                "keywords_missing",
                                                "keyword_coverage_percent",
                                            ],
                                            "type": "object",
                                        },
                                        {"type": "null"},
                                    ]
                                },
                                "photo_id": {
                                    "anyOf": [{"type": "integer"}, {"type": "null"}]
                                },
                            },
                            "required": [
                                "document_id",
                                "job_id",
                                "kind",
                                "version",
                                "created",
                                "pdf_url",
                                "cv",
                                "cover_letter",
                                "lint",
                                "photo_id",
                            ],
                            "type": "object",
                        },
                        {"type": "null"},
                    ]
                },
                "photos": {
                    "properties": {
                        "photos": {
                            "items": {
                                "properties": {
                                    "photo_id": {"type": "integer"},
                                    "label": {"type": "string"},
                                    "added": {"type": "string"},
                                    "last_used": {
                                        "anyOf": [{"type": "string"}, {"type": "null"}]
                                    },
                                    "preview_url": {"type": "string"},
                                },
                                "required": [
                                    "photo_id",
                                    "label",
                                    "added",
                                    "last_used",
                                    "preview_url",
                                ],
                                "type": "object",
                            },
                            "type": "array",
                        },
                        "suggested_photo_id": {
                            "anyOf": [{"type": "integer"}, {"type": "null"}]
                        },
                        "photo_upload_url": {"type": "string"},
                    },
                    "required": ["photos", "suggested_photo_id", "photo_upload_url"],
                    "type": "object",
                },
                "ceiling": {
                    "anyOf": [
                        {
                            "properties": {
                                "percent": {"type": "integer"},
                                "unbacked": {
                                    "items": {"type": "string"},
                                    "type": "array",
                                },
                                "reaches_target": {"type": "boolean"},
                            },
                            "required": ["percent", "unbacked", "reaches_target"],
                            "type": "object",
                        },
                        {"type": "null"},
                    ]
                },
            },
            "required": [
                "job",
                "analysis",
                "profile",
                "confirmed_facts",
                "rules",
                "previous",
                "photos",
            ],
            "type": "object",
        },
    },
    "save_cv": {
        "in": {
            "properties": {
                "job_id": {"type": "integer"},
                "cv": {
                    "properties": {
                        "headline": {
                            "properties": {
                                "text": {"type": "string"},
                                "fact_ids": {
                                    "items": {"type": "integer"},
                                    "type": "array",
                                },
                            },
                            "required": ["text", "fact_ids"],
                            "type": "object",
                        },
                        "summary": {
                            "properties": {
                                "text": {"type": "string"},
                                "fact_ids": {
                                    "items": {"type": "integer"},
                                    "type": "array",
                                },
                            },
                            "required": ["text", "fact_ids"],
                            "type": "object",
                        },
                        "sections": {
                            "items": {
                                "properties": {
                                    "name": {
                                        "enum": [
                                            "Experience",
                                            "Projects",
                                            "Achievements",
                                            "Skills",
                                            "Education",
                                            "Education and Languages",
                                            "Certifications",
                                            "Languages",
                                        ],
                                        "type": "string",
                                    },
                                    "entries": {
                                        "items": {
                                            "properties": {
                                                "heading": {
                                                    "properties": {
                                                        "text": {"type": "string"},
                                                        "fact_ids": {
                                                            "items": {
                                                                "type": "integer"
                                                            },
                                                            "type": "array",
                                                        },
                                                    },
                                                    "required": ["text", "fact_ids"],
                                                    "type": "object",
                                                },
                                                "meta": {
                                                    "anyOf": [
                                                        {
                                                            "properties": {
                                                                "text": {
                                                                    "type": "string"
                                                                },
                                                                "fact_ids": {
                                                                    "items": {
                                                                        "type": "integer"
                                                                    },
                                                                    "type": "array",
                                                                },
                                                            },
                                                            "required": [
                                                                "text",
                                                                "fact_ids",
                                                            ],
                                                            "type": "object",
                                                        },
                                                        {"type": "null"},
                                                    ]
                                                },
                                                "subtitle": {
                                                    "anyOf": [
                                                        {
                                                            "properties": {
                                                                "text": {
                                                                    "type": "string"
                                                                },
                                                                "fact_ids": {
                                                                    "items": {
                                                                        "type": "integer"
                                                                    },
                                                                    "type": "array",
                                                                },
                                                            },
                                                            "required": [
                                                                "text",
                                                                "fact_ids",
                                                            ],
                                                            "type": "object",
                                                        },
                                                        {"type": "null"},
                                                    ]
                                                },
                                                "bullets": {
                                                    "items": {
                                                        "properties": {
                                                            "text": {"type": "string"},
                                                            "fact_ids": {
                                                                "items": {
                                                                    "type": "integer"
                                                                },
                                                                "type": "array",
                                                            },
                                                        },
                                                        "required": [
                                                            "text",
                                                            "fact_ids",
                                                        ],
                                                        "type": "object",
                                                    },
                                                    "type": "array",
                                                },
                                            },
                                            "required": ["heading"],
                                            "type": "object",
                                        },
                                        "type": "array",
                                    },
                                },
                                "required": ["name", "entries"],
                                "type": "object",
                            },
                            "type": "array",
                        },
                    },
                    "required": ["headline", "summary", "sections"],
                    "type": "object",
                },
                "photo_id": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
            },
            "required": ["job_id", "cv"],
            "type": "object",
        },
        "out": {
            "properties": {
                "document_id": {"type": "integer"},
                "job_id": {"type": "integer"},
                "kind": {"enum": ["cv", "cl"], "type": "string"},
                "version": {"type": "integer"},
                "created": {"type": "string"},
                "pdf_url": {"type": "string"},
                "cv": {
                    "anyOf": [
                        {
                            "properties": {
                                "headline": {
                                    "properties": {
                                        "text": {"type": "string"},
                                        "fact_ids": {
                                            "items": {"type": "integer"},
                                            "type": "array",
                                        },
                                    },
                                    "required": ["text", "fact_ids"],
                                    "type": "object",
                                },
                                "summary": {
                                    "properties": {
                                        "text": {"type": "string"},
                                        "fact_ids": {
                                            "items": {"type": "integer"},
                                            "type": "array",
                                        },
                                    },
                                    "required": ["text", "fact_ids"],
                                    "type": "object",
                                },
                                "sections": {
                                    "items": {
                                        "properties": {
                                            "name": {
                                                "enum": [
                                                    "Experience",
                                                    "Projects",
                                                    "Achievements",
                                                    "Skills",
                                                    "Education",
                                                    "Education and Languages",
                                                    "Certifications",
                                                    "Languages",
                                                ],
                                                "type": "string",
                                            },
                                            "entries": {
                                                "items": {
                                                    "properties": {
                                                        "heading": {
                                                            "properties": {
                                                                "text": {
                                                                    "type": "string"
                                                                },
                                                                "fact_ids": {
                                                                    "items": {
                                                                        "type": "integer"
                                                                    },
                                                                    "type": "array",
                                                                },
                                                            },
                                                            "required": [
                                                                "text",
                                                                "fact_ids",
                                                            ],
                                                            "type": "object",
                                                        },
                                                        "meta": {
                                                            "anyOf": [
                                                                {
                                                                    "properties": {
                                                                        "text": {
                                                                            "type": "string"
                                                                        },
                                                                        "fact_ids": {
                                                                            "items": {
                                                                                "type": "integer"
                                                                            },
                                                                            "type": "array",
                                                                        },
                                                                    },
                                                                    "required": [
                                                                        "text",
                                                                        "fact_ids",
                                                                    ],
                                                                    "type": "object",
                                                                },
                                                                {"type": "null"},
                                                            ]
                                                        },
                                                        "subtitle": {
                                                            "anyOf": [
                                                                {
                                                                    "properties": {
                                                                        "text": {
                                                                            "type": "string"
                                                                        },
                                                                        "fact_ids": {
                                                                            "items": {
                                                                                "type": "integer"
                                                                            },
                                                                            "type": "array",
                                                                        },
                                                                    },
                                                                    "required": [
                                                                        "text",
                                                                        "fact_ids",
                                                                    ],
                                                                    "type": "object",
                                                                },
                                                                {"type": "null"},
                                                            ]
                                                        },
                                                        "bullets": {
                                                            "items": {
                                                                "properties": {
                                                                    "text": {
                                                                        "type": "string"
                                                                    },
                                                                    "fact_ids": {
                                                                        "items": {
                                                                            "type": "integer"
                                                                        },
                                                                        "type": "array",
                                                                    },
                                                                },
                                                                "required": [
                                                                    "text",
                                                                    "fact_ids",
                                                                ],
                                                                "type": "object",
                                                            },
                                                            "type": "array",
                                                        },
                                                    },
                                                    "required": ["heading"],
                                                    "type": "object",
                                                },
                                                "type": "array",
                                            },
                                        },
                                        "required": ["name", "entries"],
                                        "type": "object",
                                    },
                                    "type": "array",
                                },
                            },
                            "required": ["headline", "summary", "sections"],
                            "type": "object",
                        },
                        {"type": "null"},
                    ]
                },
                "cover_letter": {
                    "anyOf": [
                        {
                            "properties": {
                                "text": {"type": "string"},
                                "fact_ids": {
                                    "items": {"type": "integer"},
                                    "type": "array",
                                },
                            },
                            "required": ["text", "fact_ids"],
                            "type": "object",
                        },
                        {"type": "null"},
                    ]
                },
                "lint": {
                    "anyOf": [
                        {
                            "properties": {
                                "passed": {"type": "boolean"},
                                "pages": {"type": "integer"},
                                "issues": {
                                    "items": {
                                        "properties": {
                                            "code": {"type": "string"},
                                            "message": {"type": "string"},
                                        },
                                        "required": ["code", "message"],
                                        "type": "object",
                                    },
                                    "type": "array",
                                },
                                "keywords_covered": {
                                    "anyOf": [
                                        {"items": {"type": "string"}, "type": "array"},
                                        {"type": "null"},
                                    ]
                                },
                                "keywords_missing": {
                                    "anyOf": [
                                        {"items": {"type": "string"}, "type": "array"},
                                        {"type": "null"},
                                    ]
                                },
                                "keyword_coverage_percent": {
                                    "anyOf": [{"type": "integer"}, {"type": "null"}]
                                },
                            },
                            "required": [
                                "passed",
                                "pages",
                                "issues",
                                "keywords_covered",
                                "keywords_missing",
                                "keyword_coverage_percent",
                            ],
                            "type": "object",
                        },
                        {"type": "null"},
                    ]
                },
                "photo_id": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
            },
            "required": [
                "document_id",
                "job_id",
                "kind",
                "version",
                "created",
                "pdf_url",
                "cv",
                "cover_letter",
                "lint",
                "photo_id",
            ],
            "type": "object",
        },
    },
    "prepare_cover_letter": {
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
                "analysis": {
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
                                "candidate_asks": {
                                    "items": {"type": "string"},
                                    "type": "array",
                                },
                                "gaps": GAPS_OUT,
                                "gap_analogues": GAP_ANALOGUES_OUT,
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
                "rules": {"type": "string"},
                "cv": {
                    "anyOf": [
                        {
                            "properties": {
                                "document_id": {"type": "integer"},
                                "job_id": {"type": "integer"},
                                "kind": {"enum": ["cv", "cl"], "type": "string"},
                                "version": {"type": "integer"},
                                "created": {"type": "string"},
                                "pdf_url": {"type": "string"},
                                "cv": {
                                    "anyOf": [
                                        {
                                            "properties": {
                                                "headline": {
                                                    "properties": {
                                                        "text": {"type": "string"},
                                                        "fact_ids": {
                                                            "items": {
                                                                "type": "integer"
                                                            },
                                                            "type": "array",
                                                        },
                                                    },
                                                    "required": ["text", "fact_ids"],
                                                    "type": "object",
                                                },
                                                "summary": {
                                                    "properties": {
                                                        "text": {"type": "string"},
                                                        "fact_ids": {
                                                            "items": {
                                                                "type": "integer"
                                                            },
                                                            "type": "array",
                                                        },
                                                    },
                                                    "required": ["text", "fact_ids"],
                                                    "type": "object",
                                                },
                                                "sections": {
                                                    "items": {
                                                        "properties": {
                                                            "name": {
                                                                "enum": [
                                                                    "Experience",
                                                                    "Projects",
                                                                    "Achievements",
                                                                    "Skills",
                                                                    "Education",
                                                                    "Education "
                                                                    "and "
                                                                    "Languages",
                                                                    "Certifications",
                                                                    "Languages",
                                                                ],
                                                                "type": "string",
                                                            },
                                                            "entries": {
                                                                "items": {
                                                                    "properties": {
                                                                        "heading": {
                                                                            "properties": {
                                                                                "text": {
                                                                                    "type": "string"
                                                                                },
                                                                                "fact_ids": {
                                                                                    "items": {
                                                                                        "type": "integer"
                                                                                    },
                                                                                    "type": "array",
                                                                                },
                                                                            },
                                                                            "required": [
                                                                                "text",
                                                                                "fact_ids",
                                                                            ],
                                                                            "type": "object",
                                                                        },
                                                                        "meta": {
                                                                            "anyOf": [
                                                                                {
                                                                                    "properties": {
                                                                                        "text": {
                                                                                            "type": "string"
                                                                                        },
                                                                                        "fact_ids": {
                                                                                            "items": {
                                                                                                "type": "integer"
                                                                                            },
                                                                                            "type": "array",
                                                                                        },
                                                                                    },
                                                                                    "required": [
                                                                                        "text",
                                                                                        "fact_ids",
                                                                                    ],
                                                                                    "type": "object",
                                                                                },
                                                                                {
                                                                                    "type": "null"
                                                                                },
                                                                            ]
                                                                        },
                                                                        "subtitle": {
                                                                            "anyOf": [
                                                                                {
                                                                                    "properties": {
                                                                                        "text": {
                                                                                            "type": "string"
                                                                                        },
                                                                                        "fact_ids": {
                                                                                            "items": {
                                                                                                "type": "integer"
                                                                                            },
                                                                                            "type": "array",
                                                                                        },
                                                                                    },
                                                                                    "required": [
                                                                                        "text",
                                                                                        "fact_ids",
                                                                                    ],
                                                                                    "type": "object",
                                                                                },
                                                                                {
                                                                                    "type": "null"
                                                                                },
                                                                            ]
                                                                        },
                                                                        "bullets": {
                                                                            "items": {
                                                                                "properties": {
                                                                                    "text": {
                                                                                        "type": "string"
                                                                                    },
                                                                                    "fact_ids": {
                                                                                        "items": {
                                                                                            "type": "integer"
                                                                                        },
                                                                                        "type": "array",
                                                                                    },
                                                                                },
                                                                                "required": [
                                                                                    "text",
                                                                                    "fact_ids",
                                                                                ],
                                                                                "type": "object",
                                                                            },
                                                                            "type": "array",
                                                                        },
                                                                    },
                                                                    "required": [
                                                                        "heading"
                                                                    ],
                                                                    "type": "object",
                                                                },
                                                                "type": "array",
                                                            },
                                                        },
                                                        "required": ["name", "entries"],
                                                        "type": "object",
                                                    },
                                                    "type": "array",
                                                },
                                            },
                                            "required": [
                                                "headline",
                                                "summary",
                                                "sections",
                                            ],
                                            "type": "object",
                                        },
                                        {"type": "null"},
                                    ]
                                },
                                "cover_letter": {
                                    "anyOf": [
                                        {
                                            "properties": {
                                                "text": {"type": "string"},
                                                "fact_ids": {
                                                    "items": {"type": "integer"},
                                                    "type": "array",
                                                },
                                            },
                                            "required": ["text", "fact_ids"],
                                            "type": "object",
                                        },
                                        {"type": "null"},
                                    ]
                                },
                                "lint": {
                                    "anyOf": [
                                        {
                                            "properties": {
                                                "passed": {"type": "boolean"},
                                                "pages": {"type": "integer"},
                                                "issues": {
                                                    "items": {
                                                        "properties": {
                                                            "code": {"type": "string"},
                                                            "message": {
                                                                "type": "string"
                                                            },
                                                        },
                                                        "required": ["code", "message"],
                                                        "type": "object",
                                                    },
                                                    "type": "array",
                                                },
                                                "keywords_covered": {
                                                    "anyOf": [
                                                        {
                                                            "items": {"type": "string"},
                                                            "type": "array",
                                                        },
                                                        {"type": "null"},
                                                    ]
                                                },
                                                "keywords_missing": {
                                                    "anyOf": [
                                                        {
                                                            "items": {"type": "string"},
                                                            "type": "array",
                                                        },
                                                        {"type": "null"},
                                                    ]
                                                },
                                                "keyword_coverage_percent": {
                                                    "anyOf": [
                                                        {"type": "integer"},
                                                        {"type": "null"},
                                                    ]
                                                },
                                            },
                                            "required": [
                                                "passed",
                                                "pages",
                                                "issues",
                                                "keywords_covered",
                                                "keywords_missing",
                                                "keyword_coverage_percent",
                                            ],
                                            "type": "object",
                                        },
                                        {"type": "null"},
                                    ]
                                },
                                "photo_id": {
                                    "anyOf": [{"type": "integer"}, {"type": "null"}]
                                },
                            },
                            "required": [
                                "document_id",
                                "job_id",
                                "kind",
                                "version",
                                "created",
                                "pdf_url",
                                "cv",
                                "cover_letter",
                                "lint",
                                "photo_id",
                            ],
                            "type": "object",
                        },
                        {"type": "null"},
                    ]
                },
                "previous": {
                    "anyOf": [
                        {
                            "properties": {
                                "document_id": {"type": "integer"},
                                "job_id": {"type": "integer"},
                                "kind": {"enum": ["cv", "cl"], "type": "string"},
                                "version": {"type": "integer"},
                                "created": {"type": "string"},
                                "pdf_url": {"type": "string"},
                                "cv": {
                                    "anyOf": [
                                        {
                                            "properties": {
                                                "headline": {
                                                    "properties": {
                                                        "text": {"type": "string"},
                                                        "fact_ids": {
                                                            "items": {
                                                                "type": "integer"
                                                            },
                                                            "type": "array",
                                                        },
                                                    },
                                                    "required": ["text", "fact_ids"],
                                                    "type": "object",
                                                },
                                                "summary": {
                                                    "properties": {
                                                        "text": {"type": "string"},
                                                        "fact_ids": {
                                                            "items": {
                                                                "type": "integer"
                                                            },
                                                            "type": "array",
                                                        },
                                                    },
                                                    "required": ["text", "fact_ids"],
                                                    "type": "object",
                                                },
                                                "sections": {
                                                    "items": {
                                                        "properties": {
                                                            "name": {
                                                                "enum": [
                                                                    "Experience",
                                                                    "Projects",
                                                                    "Achievements",
                                                                    "Skills",
                                                                    "Education",
                                                                    "Education "
                                                                    "and "
                                                                    "Languages",
                                                                    "Certifications",
                                                                    "Languages",
                                                                ],
                                                                "type": "string",
                                                            },
                                                            "entries": {
                                                                "items": {
                                                                    "properties": {
                                                                        "heading": {
                                                                            "properties": {
                                                                                "text": {
                                                                                    "type": "string"
                                                                                },
                                                                                "fact_ids": {
                                                                                    "items": {
                                                                                        "type": "integer"
                                                                                    },
                                                                                    "type": "array",
                                                                                },
                                                                            },
                                                                            "required": [
                                                                                "text",
                                                                                "fact_ids",
                                                                            ],
                                                                            "type": "object",
                                                                        },
                                                                        "meta": {
                                                                            "anyOf": [
                                                                                {
                                                                                    "properties": {
                                                                                        "text": {
                                                                                            "type": "string"
                                                                                        },
                                                                                        "fact_ids": {
                                                                                            "items": {
                                                                                                "type": "integer"
                                                                                            },
                                                                                            "type": "array",
                                                                                        },
                                                                                    },
                                                                                    "required": [
                                                                                        "text",
                                                                                        "fact_ids",
                                                                                    ],
                                                                                    "type": "object",
                                                                                },
                                                                                {
                                                                                    "type": "null"
                                                                                },
                                                                            ]
                                                                        },
                                                                        "subtitle": {
                                                                            "anyOf": [
                                                                                {
                                                                                    "properties": {
                                                                                        "text": {
                                                                                            "type": "string"
                                                                                        },
                                                                                        "fact_ids": {
                                                                                            "items": {
                                                                                                "type": "integer"
                                                                                            },
                                                                                            "type": "array",
                                                                                        },
                                                                                    },
                                                                                    "required": [
                                                                                        "text",
                                                                                        "fact_ids",
                                                                                    ],
                                                                                    "type": "object",
                                                                                },
                                                                                {
                                                                                    "type": "null"
                                                                                },
                                                                            ]
                                                                        },
                                                                        "bullets": {
                                                                            "items": {
                                                                                "properties": {
                                                                                    "text": {
                                                                                        "type": "string"
                                                                                    },
                                                                                    "fact_ids": {
                                                                                        "items": {
                                                                                            "type": "integer"
                                                                                        },
                                                                                        "type": "array",
                                                                                    },
                                                                                },
                                                                                "required": [
                                                                                    "text",
                                                                                    "fact_ids",
                                                                                ],
                                                                                "type": "object",
                                                                            },
                                                                            "type": "array",
                                                                        },
                                                                    },
                                                                    "required": [
                                                                        "heading"
                                                                    ],
                                                                    "type": "object",
                                                                },
                                                                "type": "array",
                                                            },
                                                        },
                                                        "required": ["name", "entries"],
                                                        "type": "object",
                                                    },
                                                    "type": "array",
                                                },
                                            },
                                            "required": [
                                                "headline",
                                                "summary",
                                                "sections",
                                            ],
                                            "type": "object",
                                        },
                                        {"type": "null"},
                                    ]
                                },
                                "cover_letter": {
                                    "anyOf": [
                                        {
                                            "properties": {
                                                "text": {"type": "string"},
                                                "fact_ids": {
                                                    "items": {"type": "integer"},
                                                    "type": "array",
                                                },
                                            },
                                            "required": ["text", "fact_ids"],
                                            "type": "object",
                                        },
                                        {"type": "null"},
                                    ]
                                },
                                "lint": {
                                    "anyOf": [
                                        {
                                            "properties": {
                                                "passed": {"type": "boolean"},
                                                "pages": {"type": "integer"},
                                                "issues": {
                                                    "items": {
                                                        "properties": {
                                                            "code": {"type": "string"},
                                                            "message": {
                                                                "type": "string"
                                                            },
                                                        },
                                                        "required": ["code", "message"],
                                                        "type": "object",
                                                    },
                                                    "type": "array",
                                                },
                                                "keywords_covered": {
                                                    "anyOf": [
                                                        {
                                                            "items": {"type": "string"},
                                                            "type": "array",
                                                        },
                                                        {"type": "null"},
                                                    ]
                                                },
                                                "keywords_missing": {
                                                    "anyOf": [
                                                        {
                                                            "items": {"type": "string"},
                                                            "type": "array",
                                                        },
                                                        {"type": "null"},
                                                    ]
                                                },
                                                "keyword_coverage_percent": {
                                                    "anyOf": [
                                                        {"type": "integer"},
                                                        {"type": "null"},
                                                    ]
                                                },
                                            },
                                            "required": [
                                                "passed",
                                                "pages",
                                                "issues",
                                                "keywords_covered",
                                                "keywords_missing",
                                                "keyword_coverage_percent",
                                            ],
                                            "type": "object",
                                        },
                                        {"type": "null"},
                                    ]
                                },
                                "photo_id": {
                                    "anyOf": [{"type": "integer"}, {"type": "null"}]
                                },
                            },
                            "required": [
                                "document_id",
                                "job_id",
                                "kind",
                                "version",
                                "created",
                                "pdf_url",
                                "cv",
                                "cover_letter",
                                "lint",
                                "photo_id",
                            ],
                            "type": "object",
                        },
                        {"type": "null"},
                    ]
                },
            },
            "required": [
                "job",
                "analysis",
                "profile",
                "confirmed_facts",
                "rules",
                "cv",
                "previous",
            ],
            "type": "object",
        },
    },
    "save_cover_letter": {
        "in": {
            "properties": {
                "job_id": {"type": "integer"},
                "text": {"type": "string"},
                "fact_ids": {"items": {"type": "integer"}, "type": "array"},
            },
            "required": ["job_id", "text", "fact_ids"],
            "type": "object",
        },
        "out": {
            "properties": {
                "document_id": {"type": "integer"},
                "job_id": {"type": "integer"},
                "kind": {"enum": ["cv", "cl"], "type": "string"},
                "version": {"type": "integer"},
                "created": {"type": "string"},
                "pdf_url": {"type": "string"},
                "cv": {
                    "anyOf": [
                        {
                            "properties": {
                                "headline": {
                                    "properties": {
                                        "text": {"type": "string"},
                                        "fact_ids": {
                                            "items": {"type": "integer"},
                                            "type": "array",
                                        },
                                    },
                                    "required": ["text", "fact_ids"],
                                    "type": "object",
                                },
                                "summary": {
                                    "properties": {
                                        "text": {"type": "string"},
                                        "fact_ids": {
                                            "items": {"type": "integer"},
                                            "type": "array",
                                        },
                                    },
                                    "required": ["text", "fact_ids"],
                                    "type": "object",
                                },
                                "sections": {
                                    "items": {
                                        "properties": {
                                            "name": {
                                                "enum": [
                                                    "Experience",
                                                    "Projects",
                                                    "Achievements",
                                                    "Skills",
                                                    "Education",
                                                    "Education and Languages",
                                                    "Certifications",
                                                    "Languages",
                                                ],
                                                "type": "string",
                                            },
                                            "entries": {
                                                "items": {
                                                    "properties": {
                                                        "heading": {
                                                            "properties": {
                                                                "text": {
                                                                    "type": "string"
                                                                },
                                                                "fact_ids": {
                                                                    "items": {
                                                                        "type": "integer"
                                                                    },
                                                                    "type": "array",
                                                                },
                                                            },
                                                            "required": [
                                                                "text",
                                                                "fact_ids",
                                                            ],
                                                            "type": "object",
                                                        },
                                                        "meta": {
                                                            "anyOf": [
                                                                {
                                                                    "properties": {
                                                                        "text": {
                                                                            "type": "string"
                                                                        },
                                                                        "fact_ids": {
                                                                            "items": {
                                                                                "type": "integer"
                                                                            },
                                                                            "type": "array",
                                                                        },
                                                                    },
                                                                    "required": [
                                                                        "text",
                                                                        "fact_ids",
                                                                    ],
                                                                    "type": "object",
                                                                },
                                                                {"type": "null"},
                                                            ]
                                                        },
                                                        "subtitle": {
                                                            "anyOf": [
                                                                {
                                                                    "properties": {
                                                                        "text": {
                                                                            "type": "string"
                                                                        },
                                                                        "fact_ids": {
                                                                            "items": {
                                                                                "type": "integer"
                                                                            },
                                                                            "type": "array",
                                                                        },
                                                                    },
                                                                    "required": [
                                                                        "text",
                                                                        "fact_ids",
                                                                    ],
                                                                    "type": "object",
                                                                },
                                                                {"type": "null"},
                                                            ]
                                                        },
                                                        "bullets": {
                                                            "items": {
                                                                "properties": {
                                                                    "text": {
                                                                        "type": "string"
                                                                    },
                                                                    "fact_ids": {
                                                                        "items": {
                                                                            "type": "integer"
                                                                        },
                                                                        "type": "array",
                                                                    },
                                                                },
                                                                "required": [
                                                                    "text",
                                                                    "fact_ids",
                                                                ],
                                                                "type": "object",
                                                            },
                                                            "type": "array",
                                                        },
                                                    },
                                                    "required": ["heading"],
                                                    "type": "object",
                                                },
                                                "type": "array",
                                            },
                                        },
                                        "required": ["name", "entries"],
                                        "type": "object",
                                    },
                                    "type": "array",
                                },
                            },
                            "required": ["headline", "summary", "sections"],
                            "type": "object",
                        },
                        {"type": "null"},
                    ]
                },
                "cover_letter": {
                    "anyOf": [
                        {
                            "properties": {
                                "text": {"type": "string"},
                                "fact_ids": {
                                    "items": {"type": "integer"},
                                    "type": "array",
                                },
                            },
                            "required": ["text", "fact_ids"],
                            "type": "object",
                        },
                        {"type": "null"},
                    ]
                },
                "lint": {
                    "anyOf": [
                        {
                            "properties": {
                                "passed": {"type": "boolean"},
                                "pages": {"type": "integer"},
                                "issues": {
                                    "items": {
                                        "properties": {
                                            "code": {"type": "string"},
                                            "message": {"type": "string"},
                                        },
                                        "required": ["code", "message"],
                                        "type": "object",
                                    },
                                    "type": "array",
                                },
                                "keywords_covered": {
                                    "anyOf": [
                                        {"items": {"type": "string"}, "type": "array"},
                                        {"type": "null"},
                                    ]
                                },
                                "keywords_missing": {
                                    "anyOf": [
                                        {"items": {"type": "string"}, "type": "array"},
                                        {"type": "null"},
                                    ]
                                },
                                "keyword_coverage_percent": {
                                    "anyOf": [{"type": "integer"}, {"type": "null"}]
                                },
                            },
                            "required": [
                                "passed",
                                "pages",
                                "issues",
                                "keywords_covered",
                                "keywords_missing",
                                "keyword_coverage_percent",
                            ],
                            "type": "object",
                        },
                        {"type": "null"},
                    ]
                },
                "photo_id": {"anyOf": [{"type": "integer"}, {"type": "null"}]},
            },
            "required": [
                "document_id",
                "job_id",
                "kind",
                "version",
                "created",
                "pdf_url",
                "cv",
                "cover_letter",
                "lint",
                "photo_id",
            ],
            "type": "object",
        },
    },
    "list_documents": {
        "in": {
            "properties": {"job_id": {"type": "integer"}},
            "required": ["job_id"],
            "type": "object",
        },
        "out": {
            "properties": {
                "documents": {
                    "items": {
                        "properties": {
                            "document_id": {"type": "integer"},
                            "job_id": {"type": "integer"},
                            "kind": {"enum": ["cv", "cl"], "type": "string"},
                            "version": {"type": "integer"},
                            "created": {"type": "string"},
                            "pdf_url": {"type": "string"},
                            "cv": {
                                "anyOf": [
                                    {
                                        "properties": {
                                            "headline": {
                                                "properties": {
                                                    "text": {"type": "string"},
                                                    "fact_ids": {
                                                        "items": {"type": "integer"},
                                                        "type": "array",
                                                    },
                                                },
                                                "required": ["text", "fact_ids"],
                                                "type": "object",
                                            },
                                            "summary": {
                                                "properties": {
                                                    "text": {"type": "string"},
                                                    "fact_ids": {
                                                        "items": {"type": "integer"},
                                                        "type": "array",
                                                    },
                                                },
                                                "required": ["text", "fact_ids"],
                                                "type": "object",
                                            },
                                            "sections": {
                                                "items": {
                                                    "properties": {
                                                        "name": {
                                                            "enum": [
                                                                "Experience",
                                                                "Projects",
                                                                "Achievements",
                                                                "Skills",
                                                                "Education",
                                                                "Education "
                                                                "and "
                                                                "Languages",
                                                                "Certifications",
                                                                "Languages",
                                                            ],
                                                            "type": "string",
                                                        },
                                                        "entries": {
                                                            "items": {
                                                                "properties": {
                                                                    "heading": {
                                                                        "properties": {
                                                                            "text": {
                                                                                "type": "string"
                                                                            },
                                                                            "fact_ids": {
                                                                                "items": {
                                                                                    "type": "integer"
                                                                                },
                                                                                "type": "array",
                                                                            },
                                                                        },
                                                                        "required": [
                                                                            "text",
                                                                            "fact_ids",
                                                                        ],
                                                                        "type": "object",
                                                                    },
                                                                    "meta": {
                                                                        "anyOf": [
                                                                            {
                                                                                "properties": {
                                                                                    "text": {
                                                                                        "type": "string"
                                                                                    },
                                                                                    "fact_ids": {
                                                                                        "items": {
                                                                                            "type": "integer"
                                                                                        },
                                                                                        "type": "array",
                                                                                    },
                                                                                },
                                                                                "required": [
                                                                                    "text",
                                                                                    "fact_ids",
                                                                                ],
                                                                                "type": "object",
                                                                            },
                                                                            {
                                                                                "type": "null"
                                                                            },
                                                                        ]
                                                                    },
                                                                    "subtitle": {
                                                                        "anyOf": [
                                                                            {
                                                                                "properties": {
                                                                                    "text": {
                                                                                        "type": "string"
                                                                                    },
                                                                                    "fact_ids": {
                                                                                        "items": {
                                                                                            "type": "integer"
                                                                                        },
                                                                                        "type": "array",
                                                                                    },
                                                                                },
                                                                                "required": [
                                                                                    "text",
                                                                                    "fact_ids",
                                                                                ],
                                                                                "type": "object",
                                                                            },
                                                                            {
                                                                                "type": "null"
                                                                            },
                                                                        ]
                                                                    },
                                                                    "bullets": {
                                                                        "items": {
                                                                            "properties": {
                                                                                "text": {
                                                                                    "type": "string"
                                                                                },
                                                                                "fact_ids": {
                                                                                    "items": {
                                                                                        "type": "integer"
                                                                                    },
                                                                                    "type": "array",
                                                                                },
                                                                            },
                                                                            "required": [
                                                                                "text",
                                                                                "fact_ids",
                                                                            ],
                                                                            "type": "object",
                                                                        },
                                                                        "type": "array",
                                                                    },
                                                                },
                                                                "required": ["heading"],
                                                                "type": "object",
                                                            },
                                                            "type": "array",
                                                        },
                                                    },
                                                    "required": ["name", "entries"],
                                                    "type": "object",
                                                },
                                                "type": "array",
                                            },
                                        },
                                        "required": ["headline", "summary", "sections"],
                                        "type": "object",
                                    },
                                    {"type": "null"},
                                ]
                            },
                            "cover_letter": {
                                "anyOf": [
                                    {
                                        "properties": {
                                            "text": {"type": "string"},
                                            "fact_ids": {
                                                "items": {"type": "integer"},
                                                "type": "array",
                                            },
                                        },
                                        "required": ["text", "fact_ids"],
                                        "type": "object",
                                    },
                                    {"type": "null"},
                                ]
                            },
                            "lint": {
                                "anyOf": [
                                    {
                                        "properties": {
                                            "passed": {"type": "boolean"},
                                            "pages": {"type": "integer"},
                                            "issues": {
                                                "items": {
                                                    "properties": {
                                                        "code": {"type": "string"},
                                                        "message": {"type": "string"},
                                                    },
                                                    "required": ["code", "message"],
                                                    "type": "object",
                                                },
                                                "type": "array",
                                            },
                                            "keywords_covered": {
                                                "anyOf": [
                                                    {
                                                        "items": {"type": "string"},
                                                        "type": "array",
                                                    },
                                                    {"type": "null"},
                                                ]
                                            },
                                            "keywords_missing": {
                                                "anyOf": [
                                                    {
                                                        "items": {"type": "string"},
                                                        "type": "array",
                                                    },
                                                    {"type": "null"},
                                                ]
                                            },
                                            "keyword_coverage_percent": {
                                                "anyOf": [
                                                    {"type": "integer"},
                                                    {"type": "null"},
                                                ]
                                            },
                                        },
                                        "required": [
                                            "passed",
                                            "pages",
                                            "issues",
                                            "keywords_covered",
                                            "keywords_missing",
                                            "keyword_coverage_percent",
                                        ],
                                        "type": "object",
                                    },
                                    {"type": "null"},
                                ]
                            },
                            "photo_id": {
                                "anyOf": [{"type": "integer"}, {"type": "null"}]
                            },
                        },
                        "required": [
                            "document_id",
                            "job_id",
                            "kind",
                            "version",
                            "created",
                            "pdf_url",
                            "cv",
                            "cover_letter",
                            "lint",
                            "photo_id",
                        ],
                        "type": "object",
                    },
                    "type": "array",
                }
            },
            "required": ["documents"],
            "type": "object",
        },
    },
}
