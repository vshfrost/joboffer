"""Юридичні тексти: умови й політика, без сесії."""

from fastapi import APIRouter
from pydantic import BaseModel

from application.contracts.legal import LegalDoc
from application.ports.legal import LegalDocuments
from domain.shared.errors import NotFound


class LegalDocumentBody(BaseModel):
    doc: LegalDoc
    version: str
    text: str


def legal_router(documents: LegalDocuments) -> APIRouter:
    router = APIRouter()

    @router.get("/legal/{doc}", tags=["legal"])
    async def get_document(doc: str) -> LegalDocumentBody:
        # Невідомий документ — 404, а не 422 валідації параметра.
        if doc not in LegalDoc:
            raise NotFound("Документ не знайдено")
        found = documents.get(LegalDoc(doc))
        return LegalDocumentBody(doc=found.doc, version=found.version, text=found.text)

    return router
