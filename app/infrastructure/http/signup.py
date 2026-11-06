"""Реєстрація за запрошенням: перевірка посилання, signup → verify → resend. Сесії не потребує.

Клієнт для лімітів — той самий, що й для входу (`HttpAuth.client_key`). Після правильного коду
відповідь як у входу: cookie-сесія й `csrf_token`, але статус 201.
"""

from datetime import datetime

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field, SecretStr

from application.contracts.invites import CheckInvite
from application.contracts.signup import Signup, VerifySignup
from application.identity.invites import SignupInviteUseCases
from application.identity.signup import SignupUseCases
from infrastructure.http.auth import HttpAuth, SessionResponse, session_response


class InviteResponse(BaseModel):
    valid: bool
    expires_at: datetime


class SignupRequestBody(BaseModel):
    email: str
    password: SecretStr
    display_name: str = ""
    invite: str = ""
    # Версія умов, з якою погодився користувач; нема чи не поточна — 422.
    terms_version: str = ""
    # Розв'язок ALTCHA (base64-JSON віджета).
    altcha: str = ""
    # Приманка для ботів: людина її не бачить; заповнена — нічого не робимо.
    website: str = ""


class SignupAcceptedResponse(BaseModel):
    signup_id: str


class VerifyRequestBody(BaseModel):
    signup_id: str = Field(max_length=64)
    code: SecretStr = Field(max_length=16)


class ResendRequestBody(BaseModel):
    signup_id: str = Field(max_length=64)


def signup_router(
    invites: SignupInviteUseCases, signup: SignupUseCases, auth: HttpAuth
) -> APIRouter:
    router = APIRouter(prefix="/auth/signup", tags=["auth"])

    @router.get("/invite")
    async def check_invite(
        request: Request, response: Response, invite: str = ""
    ) -> InviteResponse:
        """Чи дійсне посилання `…/signup?invite=<токен>`; невдача — 404 `invite_invalid`."""
        status = await invites.check(
            CheckInvite(token=invite, client=auth.client_key(request))
        )
        response.headers["Cache-Control"] = "no-store"
        return InviteResponse(valid=status.valid, expires_at=status.expires_at)

    @router.post("", status_code=202)
    async def register(
        body: SignupRequestBody, request: Request, response: Response
    ) -> SignupAcceptedResponse:
        """Приймає дані й надсилає код на пошту. Користувача ще нема; відповідь однакова для
        нового й наявного email."""
        accepted = await signup.signup(
            Signup(
                email=body.email,
                password=body.password.get_secret_value(),
                display_name=body.display_name,
                invite=body.invite,
                terms_version=body.terms_version,
                altcha=body.altcha,
                website=body.website,
                client=auth.client_key(request),
            )
        )
        response.headers["Cache-Control"] = "no-store"
        return SignupAcceptedResponse(signup_id=accepted.signup_id)

    @router.post("/verify", status_code=201)
    async def verify(body: VerifyRequestBody, response: Response) -> SessionResponse:
        """Правильний код → користувач і сесія (cookie + csrf_token)."""
        issued = await signup.verify(
            VerifySignup(signup_id=body.signup_id, code=body.code.get_secret_value())
        )
        auth.set_cookie(response, issued.token)
        response.headers["Cache-Control"] = "no-store"
        return session_response(issued.user, issued.token)

    @router.post("/resend", status_code=202)
    async def resend(
        body: ResendRequestBody, response: Response
    ) -> SignupAcceptedResponse:
        """Новий код на ту саму адресу; раніше ніж через 60 секунд — 429 з `Retry-After`."""
        accepted = await signup.resend(body.signup_id)
        response.headers["Cache-Control"] = "no-store"
        return SignupAcceptedResponse(signup_id=accepted.signup_id)

    return router
