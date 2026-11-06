"""Схема тула `list_photos` v1 (`origin/main` `99a2007`: `agent/photos.py`).

Розгорнута JSON-схема (без title / description / default), знята зі справжнього сервера v1:
контракт-тест порівнює з нею схему v2.
"""

from typing import Any

V1: dict[str, dict[str, Any]] = {
    "list_photos": {
        "in": {"properties": {}, "type": "object"},
        "out": {
            "properties": {
                "photo_upload_url": {"type": "string"},
                "photos": {
                    "items": {
                        "properties": {
                            "added": {"type": "string"},
                            "label": {"type": "string"},
                            "last_used": {
                                "anyOf": [{"type": "string"}, {"type": "null"}]
                            },
                            "photo_id": {"type": "integer"},
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
            },
            "required": ["photos", "suggested_photo_id", "photo_upload_url"],
            "type": "object",
        },
    }
}
