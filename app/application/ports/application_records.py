"""Unit of work подач: вакансії, подачі й документи (з них подача бере версію CV)."""

from typing import Protocol

from application.ports.documents import DocumentRepository
from application.ports.jobs import JobUnitOfWork


class ApplicationUnitOfWork(JobUnitOfWork, Protocol):
    @property
    def documents(self) -> DocumentRepository: ...
