"""Вхід через Google (OIDC) на Authlib: `GET /auth/google/start` → Google → `GET /auth/google/callback`.

State, nonce і PKCE-verifier живуть у підписаній cookie `SessionMiddleware` на час входу. `id_token` перевіряє
Authlib: підпис за JWKS, `iss`, `aud`, `exp`, nonce. Сам застосунок бере з нього лише `GoogleClaims`.
"""

from dataclasses import dataclass
from typing import Any

import httpx2
from authlib.integrations.base_client.errors import MismatchingStateError
from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, Response
from joserfc.errors import JoseError

from application.contracts.identity import GoogleClaims
from application.identity.sessions import SessionUseCases
from domain.identity.errors import EmailRequired
from domain.identity.redirects import safe_next_path
from infrastructure.http.auth import HttpAuth

_NEXT_KEY = "next"
# Усе, чим може закінчитись перевірка відповіді Google: state, nonce, підпис, aud/iss/exp, мережа, нема `sub`.
GOOGLE_FAILURES = (OAuthError, JoseError, httpx2.HTTPError, KeyError)


@dataclass(frozen=True, slots=True)
class GoogleConfig:
    client_id: str
    client_secret: str
    redirect_uri: str
    metadata_url: str
    # Підпис cookie зі станом флоу (SessionMiddleware того процесу, що показує кнопку).
    state_secret: str


def _claims(userinfo: dict[str, Any]) -> GoogleClaims:
    verified = userinfo.get("email_verified")
    return GoogleClaims(
        subject=str(userinfo["sub"]),
        email=userinfo.get("email"),
        # Google історично віддавав і рядок "true".
        email_verified=verified is True or verified == "true",
        name=userinfo.get("name"),
    )


class GoogleLogin:
    def __init__(
        self,
        config: GoogleConfig,
        *,
        transport: httpx2.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config
        client_kwargs: dict[str, Any] = {
            "scope": "openid email profile",
            "code_challenge_method": "S256",
        }
        if transport is not None:
            client_kwargs["transport"] = transport  # тести: Google — фейк на межі HTTP
        registry = OAuth()
        self._client = registry.register(
            name="google",
            client_id=config.client_id,
            client_secret=config.client_secret,
            server_metadata_url=config.metadata_url,
            client_kwargs=client_kwargs,
        )

    async def redirect_to_google(self, request: Request) -> Response:
        response: Response = await self._client.authorize_redirect(
            request, self.config.redirect_uri
        )
        return response

    async def claims(self, request: Request) -> GoogleClaims:
        """Обмінює код на токени й перевіряє `id_token`; будь-яка невідповідність — виняток."""
        token = await self._client.authorize_access_token(request)
        return _claims(token["userinfo"])


def google_router(
    login: GoogleLogin, sessions: SessionUseCases, auth: HttpAuth
) -> APIRouter:
    router = APIRouter(prefix="/auth/google", tags=["auth"])

    def back(path: str) -> RedirectResponse:
        # Куди повертаємо в SPA: вона живе в корені того ж origin, що й API.
        return RedirectResponse(path, status_code=302)

    def refused(error: str) -> RedirectResponse:
        return back(f"/login?error={error}")

    @router.get("/start")
    async def start(request: Request, next: str | None = None) -> Response:
        request.session[_NEXT_KEY] = safe_next_path(next)
        return await login.redirect_to_google(request)

    @router.get("/callback")
    async def callback(request: Request) -> Response:
        target = safe_next_path(request.session.pop(_NEXT_KEY, None))
        error = request.query_params.get("error")
        if error is not None:
            return refused("cancelled" if error == "access_denied" else "failed")
        try:
            claims = await login.claims(request)
            issued = await sessions.sign_in_with_google(claims)
        except EmailRequired:
            return refused("email_required")
        except MismatchingStateError:
            return refused("invalid_state")
        except GOOGLE_FAILURES:
            return refused("failed")
        response = back(target)
        auth.set_cookie(response, issued.token)
        response.headers["Cache-Control"] = "no-store"
        return response

    return router
