"""Адаптер OAuth-сервера MCP SDK поверх use cases: лише переклад типів SDK ↔ application, без правил.

SDK робить метадані, DCR (`/register`), `/authorize`, `/token` (PKCE S256) і `/revoke`.
Усі DCR-клієнти публічні (PKCE без client secret): секрет клієнта в базі не зберігається.
"""

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    IdentityAssertionParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    RegistrationError,
    TokenError,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyUrl

from application.contracts.oauth import AuthorizationRequest, RegisterClient, TokenPair
from application.oauth.use_cases import OAuthUseCases
from domain.oauth.errors import (
    InvalidGrant,
    InvalidRedirectUri,
    InvalidTarget,
)
from domain.oauth.rules import SCOPE


def _oauth_token(pair: TokenPair) -> OAuthToken:
    return OAuthToken(
        access_token=pair.access_token,
        token_type="Bearer",  # noqa: S106 — тип токена, не секрет
        expires_in=pair.expires_in,
        scope=pair.scope,
        refresh_token=pair.refresh_token,
    )


class JobofferOAuthProvider(
    OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]
):
    def __init__(self, oauth: OAuthUseCases, *, resource_url: str) -> None:
        self._oauth = oauth
        self._resource = resource_url

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        view = await self._oauth.find_client(client_id)
        return (
            None
            if view is None
            else OAuthClientInformationFull.model_validate(view.metadata)
        )

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        # Публічний клієнт: SDK уже вигадав секрет — не зберігаємо його й не віддаємо клієнту.
        client_info.token_endpoint_auth_method = "none"  # noqa: S105 — метод автентифікації, не секрет
        client_info.client_secret = None
        client_info.client_secret_expires_at = None
        command = RegisterClient(
            client_id=client_info.client_id or "",
            name=client_info.client_name,
            redirect_uris=tuple(str(uri) for uri in client_info.redirect_uris or ()),
            metadata=client_info.model_dump(mode="json"),
        )
        try:
            await self._oauth.register_client(command)
        except InvalidRedirectUri as error:
            raise RegistrationError("invalid_redirect_uri", error.message) from error

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        request = AuthorizationRequest(
            client_id=client.client_id or "",
            redirect_uri=str(params.redirect_uri),
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            state=params.state,
            code_challenge=params.code_challenge,
            resource=params.resource,
        )
        try:
            rid = await self._oauth.begin_authorization(request)
        except InvalidTarget as error:
            raise AuthorizeError("invalid_target", error.message) from error
        return f"{self._resource}/login?rid={rid}"

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        view = await self._oauth.load_code(client.client_id or "", authorization_code)
        if view is None:
            return None
        return AuthorizationCode(
            code=authorization_code,
            scopes=[SCOPE],
            expires_at=view.expires_at.timestamp(),
            client_id=view.client_id,
            code_challenge=view.code_challenge,
            redirect_uri=AnyUrl(view.redirect_uri),
            redirect_uri_provided_explicitly=view.redirect_uri_provided_explicitly,
            resource=view.resource,
            subject=str(view.user_id),
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        try:
            pair = await self._oauth.exchange_code(
                client.client_id or "", authorization_code.code
            )
        except InvalidGrant as error:
            raise TokenError("invalid_grant", error.message) from error
        return _oauth_token(pair)

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        view = await self._oauth.load_refresh(client.client_id or "", refresh_token)
        if view is None:
            return None
        return RefreshToken(
            token=refresh_token,
            client_id=view.client_id,
            scopes=[SCOPE],
            expires_at=int(view.expires_at.timestamp()),
            resource=view.resource,
            subject=str(view.user_id),
        )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        try:
            pair = await self._oauth.exchange_refresh(
                client.client_id or "", refresh_token.token
            )
        except InvalidGrant as error:
            raise TokenError("invalid_grant", error.message) from error
        return _oauth_token(pair)

    async def load_access_token(self, token: str) -> AccessToken | None:
        view = await self._oauth.verify_access(token)
        if view is None:
            return None
        return AccessToken(
            token=token,
            client_id=view.client_id,
            scopes=[SCOPE],
            expires_at=int(view.expires_at.timestamp()),
            resource=view.resource,
            subject=str(view.user_id),
            # Для Actor тулів (K7): за яким грантом діє клієнт.
            claims={"grant_id": str(view.grant_id)},
        )

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        await self._oauth.revoke(token.token)

    async def exchange_identity_assertion(
        self, client: OAuthClientInformationFull, params: IdentityAssertionParams
    ) -> OAuthToken:
        raise TokenError(
            "unsupported_grant_type", "Identity assertion is not supported"
        )
