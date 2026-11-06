"""HTTP-вхід: cookie-сесія, CSRF, Actor із сесії.

- Токен сесії лежить лише в HttpOnly-cookie; у відповідях його нема.
- CSRF-токен виводиться з токена сесії (HMAC), тож окремо не зберігається, а SPA бере його з
  відповідей `login` / `me` і шле в заголовку `X-CSRF-Token` для небезпечних методів.
- Заданий `client_ip_header` (Cloudflare) береться лише від локального проксі: loopback або приватна адреса.
- Клієнт для ліміту спроб — IP зі сокета; `X-Forwarded-For` береться лише за `trusted_proxies > 0`
  і лише запис, який додав наш проксі (справа), бо лівіші записи підробляє клієнт.
"""

import hashlib
import hmac
from dataclasses import dataclass
from ipaddress import ip_address

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, SecretStr

from application.contracts.actor import Actor, Channel, Scope
from application.contracts.identity import UserView
from application.contracts.sessions import Login, SessionView
from application.identity.altcha import AltchaUseCases
from application.identity.sessions import SessionUseCases
from domain.identity.errors import NOT_AUTHENTICATED_MESSAGE, NotAuthenticated
from domain.identity.ids import UserId
from domain.shared.errors import Forbidden
from infrastructure.http.correlation import correlation_id

CSRF_HEADER = "X-CSRF-Token"
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_CSRF_LABEL = b"joboffer-csrf-v1"
_WEB_CLIENT_ID = "web"


def _is_local(host: str) -> bool:
    try:
        address = ip_address(host)
    except ValueError:
        return False
    return address.is_loopback or address.is_private


class CsrfFailed(Forbidden):
    code = "csrf_failed"


@dataclass(frozen=True, slots=True)
class CookieConfig:
    name: str
    secure: bool
    max_age: int


def csrf_token_for(session_token: str) -> str:
    return hmac.new(session_token.encode(), _CSRF_LABEL, hashlib.sha256).hexdigest()


class HttpAuth:
    def __init__(
        self,
        sessions: SessionUseCases,
        cookie: CookieConfig,
        trusted_proxies: int,
        client_ip_header: str | None = None,
    ) -> None:
        self._sessions = sessions
        self._cookie = cookie
        self._trusted_proxies = trusted_proxies
        self._client_ip_header = client_ip_header

    def client_key(self, request: Request) -> str:
        peer = request.client.host if request.client else "unknown"
        if self._client_ip_header is not None and _is_local(peer):
            try:
                return str(
                    ip_address(request.headers.get(self._client_ip_header, "").strip())
                )
            except ValueError:
                pass  # заголовка нема або він не адреса: далі як без нього
        if self._trusted_proxies == 0:
            return peer
        forwarded = [
            part.strip()
            for part in request.headers.get("x-forwarded-for", "").split(",")
            if part.strip()
        ]
        if len(forwarded) < self._trusted_proxies:
            return peer
        return forwarded[-self._trusted_proxies]

    def token_of(self, request: Request) -> str | None:
        return request.cookies.get(self._cookie.name)

    async def session(self, request: Request) -> SessionView:
        token = self.token_of(request)
        if token is None:
            raise NotAuthenticated(NOT_AUTHENTICATED_MESSAGE)
        return await self._sessions.identify(token)

    def require_csrf(self, request: Request, session_token: str) -> None:
        supplied = request.headers.get(CSRF_HEADER, "")
        # compare_digest падає на рядках не-ASCII, а заголовок приходить від клієнта: порівнюємо байти.
        expected = csrf_token_for(session_token)
        if not hmac.compare_digest(supplied.encode(), expected.encode()):
            raise CsrfFailed("Невірний або відсутній CSRF-токен")

    async def actor(self, request: Request) -> Actor:
        """Залежність для захищених маршрутів: сесія → Actor; небезпечні методи ще й із CSRF."""
        view = await self.session(request)
        if request.method not in _SAFE_METHODS:
            self.require_csrf(request, str(self.token_of(request)))
        return Actor(
            user_id=UserId.parse(view.user.id),
            channel=Channel.WEB,
            client_id=_WEB_CLIENT_ID,
            grant_id=None,
            scopes=frozenset(Scope),
            correlation_id=correlation_id(request),
        )

    def set_cookie(self, response: Response, token: str) -> None:
        response.set_cookie(
            self._cookie.name,
            token,
            max_age=self._cookie.max_age,
            path="/",
            secure=self._cookie.secure,
            httponly=True,
            samesite="lax",
        )

    def clear_cookie(self, response: Response) -> None:
        response.delete_cookie(
            self._cookie.name,
            path="/",
            secure=self._cookie.secure,
            httponly=True,
            samesite="lax",
        )

    async def log_in(
        self, request: Request, email: str, password: str
    ) -> tuple[str, UserView]:
        issued = await self._sessions.login(
            Login(email=email, password=password, client=self.client_key(request))
        )
        return issued.token, issued.user

    async def log_out(self, request: Request) -> None:
        token = self.token_of(request)
        if token is None:
            return
        try:
            await self._sessions.identify(token)
        except NotAuthenticated:
            return  # сесії вже нема: захищати нічого, достатньо прибрати cookie
        self.require_csrf(request, token)
        await self._sessions.logout(token)


class LoginRequest(BaseModel):
    email: str
    password: SecretStr


class UserResponse(BaseModel):
    id: str
    email: str
    display_name: str


class ChallengeResponse(BaseModel):
    algorithm: str
    challenge: str
    maxnumber: int
    salt: str
    signature: str


class SessionResponse(BaseModel):
    user: UserResponse
    csrf_token: str


def _user(view: UserView) -> UserResponse:
    return UserResponse(id=view.id, email=view.email, display_name=view.display_name)


def session_response(user: UserView, token: str) -> SessionResponse:
    """Тіло відповіді після відкриття сесії: користувач і CSRF-токен, виведений із токена сесії."""
    return SessionResponse(user=_user(user), csrf_token=csrf_token_for(token))


def auth_router(
    auth: HttpAuth, altcha: AltchaUseCases, *, google_enabled: bool = False
) -> APIRouter:
    router = APIRouter(prefix="/auth", tags=["auth"])

    @router.get("/providers")
    async def providers() -> dict[str, bool]:
        """Які способи входу ввімкнено (для екрана входу); сесії не потребує."""
        return {"google": google_enabled}

    @router.get("/challenge")
    async def challenge(response: Response) -> ChallengeResponse:
        """Задача proof-of-work для віджета altcha; без ключа — 503."""
        issued = await altcha.issue()
        response.headers["Cache-Control"] = "no-store"
        return ChallengeResponse(
            algorithm=issued.algorithm,
            challenge=issued.challenge,
            maxnumber=issued.maxnumber,
            salt=issued.salt,
            signature=issued.signature,
        )

    @router.post("/login")
    async def login(
        body: LoginRequest, request: Request, response: Response
    ) -> SessionResponse:
        token, user = await auth.log_in(
            request, body.email, body.password.get_secret_value()
        )
        auth.set_cookie(response, token)
        response.headers["Cache-Control"] = "no-store"
        return session_response(user, token)

    @router.get("/me")
    async def me(request: Request, response: Response) -> SessionResponse:
        view = await auth.session(request)
        response.headers["Cache-Control"] = "no-store"
        return SessionResponse(
            user=_user(view.user),
            csrf_token=csrf_token_for(str(auth.token_of(request))),
        )

    @router.post("/logout", status_code=204)
    async def logout(request: Request) -> Response:
        await auth.log_out(request)
        response = Response(status_code=204, headers={"Cache-Control": "no-store"})
        auth.clear_cookie(response)
        return response

    return router
