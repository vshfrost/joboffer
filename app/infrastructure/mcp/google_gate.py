"""Вхід через Google в логін-гейті MCP: `GET /auth/google/start?rid=` → Google → `GET /auth/google/callback`.

Після повернення користувач — той самий, що й при вході паролем: далі `complete_authorization(rid, user)` і редирект
у клієнт MCP із кодом. Запит на вхід (rid) перевіряється до походу в Google і після повернення; на помилці код не
видається, а rid не спожито — користувач може спробувати ще раз чи ввести пароль.
"""

from mcp.server.auth.provider import construct_redirect_uri
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from application.identity.use_cases import IdentityUseCases
from application.oauth.use_cases import OAuthUseCases
from domain.identity.errors import EmailRequired
from domain.identity.ids import UserId
from domain.oauth.errors import AuthorizationExpired
from infrastructure.http.google import GOOGLE_FAILURES, GoogleLogin
from infrastructure.mcp.login_gate import HEADERS, LoginGate

_RID_KEY = "rid"
EMAIL_REQUIRED = "Google не передав підтверджений email — вхід неможливий"
CANCELLED = "Вхід скасовано"
FAILED = "Не вдалося увійти через Google. Спробуй ще раз."


class GoogleGate:
    def __init__(
        self,
        google: GoogleLogin,
        gate: LoginGate,
        oauth: OAuthUseCases,
        identity: IdentityUseCases,
    ) -> None:
        self._google = google
        self._gate = gate
        self._oauth = oauth
        self._identity = identity

    async def start(self, request: Request) -> Response:
        rid = request.query_params.get("rid", "")
        if await self._oauth.describe_pending(rid) is None:
            return self._gate.expired_page(400)
        request.session[_RID_KEY] = rid
        return await self._google.redirect_to_google(request)

    async def callback(self, request: Request) -> Response:
        rid = request.session.pop(_RID_KEY, "")
        if await self._oauth.describe_pending(rid) is None:
            return self._gate.expired_page(400)
        error = request.query_params.get("error")
        if error is not None:
            return await self._refused(
                rid, CANCELLED if error == "access_denied" else FAILED
            )
        try:
            claims = await self._google.claims(request)
            user = await self._identity.sign_in_with_google(claims)
        except EmailRequired:
            return await self._refused(rid, EMAIL_REQUIRED)
        except GOOGLE_FAILURES:
            return await self._refused(rid, FAILED)
        try:
            granted = await self._oauth.complete_authorization(
                rid, UserId.parse(user.id)
            )
        except AuthorizationExpired:
            return self._gate.expired_page(400)
        target = construct_redirect_uri(
            granted.redirect_uri, code=granted.code, state=granted.state
        )
        return RedirectResponse(target, status_code=302, headers=HEADERS)

    async def _refused(self, rid: str, message: str) -> Response:
        """Та сама сторінка гейта з помилкою; rid не спожито, код не видано."""
        return await self._gate.form_page(rid, error=message, status=400)
