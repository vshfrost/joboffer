"""Відбиток тексту для дедупу: однаковий для вакансій і фактів."""

import hashlib


def text_fingerprint(text: str) -> str:
    """Пробіли й регістр не враховуються."""
    normalized = " ".join(text.split()).casefold()
    return hashlib.sha256(normalized.encode()).hexdigest()
