"""Порт юридичних документів. Єдине джерело версії: нею і показують текст, і перевіряють згоду."""

from typing import Protocol

from application.contracts.legal import LegalDoc, LegalDocument


class LegalDocumentsUnavailableError(Exception):
    """Документ не вдалося прочитати: файлу нема, він не UTF-8 або без версії. Повідомлення називає файл."""


class LegalDocuments(Protocol):
    def get(self, doc: LegalDoc) -> LegalDocument: ...
