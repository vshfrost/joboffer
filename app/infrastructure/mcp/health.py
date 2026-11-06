"""`/healthz` агента: відповідає 200, лише коли база доступна."""

from collections.abc import Awaitable, Callable

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


def healthz(engine: AsyncEngine) -> Callable[[Request], Awaitable[Response]]:
    async def endpoint(_: Request) -> Response:
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except SQLAlchemyError, OSError:
            return JSONResponse({"status": "database unavailable"}, status_code=503)
        return JSONResponse({"status": "ok"})

    return endpoint
