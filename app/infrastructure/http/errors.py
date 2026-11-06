"""Мапінг помилок у HTTP. Domain і application не знають статусів — їх знає лише цей модуль.

Тіло завжди одне: `{code, message, field_errors, correlation_id}`. Без stacktrace, SQL і
внутрішніх повідомлень: `NotFound` має однаковий текст, тож відповідь не розкриває, чи сутність
існує, чи вона чужа.
"""

import logging
import math
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from domain.identity.errors import (
    AltchaFailed,
    CodeIncorrect,
    InvalidCredentials,
    NotAuthenticated,
    RegistrationClosed,
    SignupMailUnavailable,
    TooManyAttempts,
)
from domain.mail.inbox import MailNotConfigured, ManualSyncLimit
from domain.shared.errors import (
    Conflict,
    DomainError,
    Forbidden,
    InvalidFields,
    InvalidValue,
    NotFound,
)
from domain.sources.refresh_requests import RefreshLimit
from infrastructure.http.correlation import correlation_id

logger = logging.getLogger(__name__)

NOT_FOUND_MESSAGE = "Не знайдено"
INVALID_REQUEST_MESSAGE = "Запит не пройшов перевірку"
INTERNAL_MESSAGE = "Внутрішня помилка. Повідом correlation_id, якщо повторюється."

# Категорія → статус. Підкласи (StaleVersion, свої Conflict контекстів) успадковують статус категорії.
_STATUS_BY_CATEGORY: tuple[tuple[type[DomainError], int], ...] = (
    (InvalidValue, 422),
    (AltchaFailed, 422),
    (NotFound, 404),
    (Forbidden, 403),
    (Conflict, 409),
    (InvalidCredentials, 401),
    (NotAuthenticated, 401),
    (TooManyAttempts, 429),
    (ManualSyncLimit, 429),
    (RefreshLimit, 429),
    (MailNotConfigured, 503),
    (RegistrationClosed, 503),
    (SignupMailUnavailable, 503),
)
_DEFAULT_DOMAIN_STATUS = 400


class FieldError(BaseModel):
    field: str
    message: str


class ErrorBody(BaseModel):
    code: str
    message: str
    field_errors: list[FieldError]
    correlation_id: str


def status_for(error: DomainError) -> int:
    for category, status in _STATUS_BY_CATEGORY:
        if isinstance(error, category):
            return status
    return _DEFAULT_DOMAIN_STATUS


def _body(
    request: Request,
    code: str,
    message: str,
    field_errors: list[FieldError] | None = None,
) -> dict[str, object]:
    return ErrorBody(
        code=code,
        message=message,
        field_errors=field_errors or [],
        correlation_id=correlation_id(request),
    ).model_dump()


def _respond(
    request: Request,
    status: int,
    code: str,
    message: str,
    field_errors: list[FieldError] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status, content=_body(request, code, message, field_errors)
    )


async def _domain_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, DomainError):
        raise TypeError("обробник DomainError отримав інший виняток")
    if isinstance(exc, NotFound):
        return _respond(request, 404, exc.code, NOT_FOUND_MESSAGE)
    field_errors: list[FieldError] = []
    if isinstance(exc, InvalidFields):
        field_errors = [
            FieldError(field=problem.field, message=problem.message)
            for problem in exc.problems
        ]
    elif isinstance(exc, InvalidValue):
        field_errors = [FieldError(field=exc.field, message=exc.message)]
    if isinstance(exc, CodeIncorrect):
        # Невірний код несе, скільки спроб лишилось: форма показує це поруч із полем коду.
        content = _body(request, exc.code, exc.message, field_errors)
        return JSONResponse(
            status_code=status_for(exc),
            content={**content, "attempts_left": exc.attempts_left},
        )
    response = _respond(request, status_for(exc), exc.code, exc.message, field_errors)
    if isinstance(exc, TooManyAttempts):
        response.headers["Retry-After"] = str(exc.retry_after)
    if isinstance(exc, ManualSyncLimit | RefreshLimit):
        wait = (exc.next_at - datetime.now(UTC)).total_seconds()
        response.headers["Retry-After"] = str(max(1, math.ceil(wait)))
    return response


async def _invalid_request(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise TypeError("обробник валідації отримав інший виняток")
    field_errors = [
        # loc: ("body" | "query" | "path", поле, …) — назовні лише шлях до поля.
        FieldError(
            field=".".join(str(part) for part in error["loc"][1:]) or "request",
            message=str(error["msg"]),
        )
        for error in exc.errors()
    ]
    return _respond(
        request, 422, "invalid_request", INVALID_REQUEST_MESSAGE, field_errors
    )


async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "unhandled error correlation_id=%s",
        correlation_id(request),
        exc_info=exc,
    )
    return _respond(request, 500, "internal_error", INTERNAL_MESSAGE)


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _domain_error)
    app.add_exception_handler(RequestValidationError, _invalid_request)
    app.add_exception_handler(Exception, _unexpected)
