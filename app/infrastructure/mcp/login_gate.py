"""Логін-гейт OAuth: екран згоди + email і пароль. Код видається лише після вірного входу.

HTML — шаблони `app/templates/oauth/` (inline CSS, без JS); сюди підставляються лише екранізовані значення.
Ліміт спроб — той самий «клієнт + email», що й у вебі: пароль перевіряє `SessionUseCases.verify_login`.
"""

import html
import math
from collections.abc import Callable
from string import Template

from mcp.server.auth.provider import construct_redirect_uri
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from application.contracts.sessions import Login
from application.identity.sessions import SessionUseCases
from application.oauth.use_cases import OAuthUseCases
from application.ports.templates import TemplateKey, Templates
from domain.identity.errors import InvalidCredentials, TooManyAttempts
from domain.identity.ids import UserId
from domain.oauth.errors import AuthorizationExpired

# Жодних скриптів, фреймів чи витоку rid через Referer. form-action не ставимо: Chrome
# застосовує його й до 302 після POST, а успішний вхід редиректить на redirect_uri клієнта.
HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}
INVALID_CREDENTIALS = "Невірний email або пароль"
SECONDS_PER_MINUTE = 60


def _escape(value: str) -> str:
    return html.escape(value, quote=True)


class LoginGate:
    def __init__(
        self,
        oauth: OAuthUseCases,
        sessions: SessionUseCases,
        templates: Templates,
        client_key: Callable[[Request], str],
        *,
        google_enabled: bool = False,
    ) -> None:
        self._oauth = oauth
        self._sessions = sessions
        self._templates = templates
        self._client_key = client_key
        self._google_enabled = google_enabled

    async def handle(self, request: Request) -> Response:
        if request.method == "GET":
            return await self.form_page(request.query_params.get("rid", ""))
        form = await request.form()
        rid, email, password = (
            str(form.get(name, "")) for name in ("rid", "email", "password")
        )
        if await self._oauth.describe_pending(rid) is None:
            return self.expired_page(400)
        login = Login(email=email, password=password, client=self._client_key(request))
        try:
            user = await self._sessions.verify_login(login)
        except InvalidCredentials:
            return await self.form_page(
                rid, error=INVALID_CREDENTIALS, email=email, status=401
            )
        except TooManyAttempts as blocked:
            minutes = math.ceil(blocked.retry_after / SECONDS_PER_MINUTE)
            response = await self.form_page(
                rid,
                error=f"Забагато спроб. Спробуй за ~{minutes} хв.",
                email=email,
                status=429,
            )
            response.headers["Retry-After"] = str(blocked.retry_after)
            return response
        try:
            granted = await self._oauth.complete_authorization(
                rid, UserId.parse(user.id)
            )
        except AuthorizationExpired:
            return self.expired_page(400)
        target = construct_redirect_uri(
            granted.redirect_uri, code=granted.code, state=granted.state
        )
        return RedirectResponse(target, status_code=302, headers=HEADERS)

    async def form_page(
        self, rid: str, *, error: str = "", email: str = "", status: int = 200
    ) -> HTMLResponse:
        """Форма — лише для живого запиту (rid, виданий цим сервером) і разом зі згодою."""
        pending = await self._oauth.describe_pending(rid) if rid else None
        if pending is None:
            return self.expired_page(200)
        content = Template(
            self._templates.get(TemplateKey.OAUTH_LOGIN_FORM)
        ).safe_substitute(
            client_name=_escape(pending.client_name),
            redirect_host=_escape(pending.redirect_host),
            rid=_escape(rid),
            email=_escape(email),
            error=f'<p class="error" role="alert">{_escape(error)}</p>'
            if error
            else "",
            google=self._google_button(rid),
        )
        return self._page(content, status)

    def _google_button(self, rid: str) -> str:
        if not self._google_enabled:
            return ""
        return Template(
            self._templates.get(TemplateKey.OAUTH_LOGIN_GOOGLE)
        ).safe_substitute(rid=_escape(rid))

    def expired_page(self, status: int) -> HTMLResponse:
        return self._page(self._templates.get(TemplateKey.OAUTH_LOGIN_EXPIRED), status)

    def _page(self, content: str, status: int) -> HTMLResponse:
        page = Template(self._templates.get(TemplateKey.OAUTH_LOGIN)).safe_substitute(
            content=content
        )
        return HTMLResponse(page, status_code=status, headers=HEADERS)
