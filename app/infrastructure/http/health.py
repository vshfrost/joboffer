"""Liveness: процес живий і відповідає. Залежностей (БД тощо) не перевіряє."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel


class Health(BaseModel):
    status: Literal["ok"]


def health_router() -> APIRouter:
    router = APIRouter()

    @router.get("/healthz", tags=["health"])
    async def healthz() -> Health:
        return Health(status="ok")

    return router
