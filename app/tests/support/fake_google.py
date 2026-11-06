"""Підроблений Google на межі HTTP: discovery, JWKS і token endpoint з тестовим RSA-ключем (не секрет).

Застосунок ходить сюди через `httpx.ASGITransport`, тож Authlib проходить увесь справжній шлях:
metadata → authorize-посилання → обмін коду → перевірка `id_token` за JWKS.
"""

import time
from base64 import b64decode
from typing import Any

from joserfc import jwt
from joserfc.jwk import KeySet, RSAKey
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

ISSUER = "https://accounts.example.test"
CLIENT_ID = "test-client-id.apps.googleusercontent.com"
CLIENT_SECRET = "test-google-secret"
METADATA_URL = f"{ISSUER}/.well-known/openid-configuration"
KEY_ID = "test-key-1"
_UNSET: Any = object()


def new_key(kid: str = KEY_ID) -> RSAKey:
    return RSAKey.generate_key(2048, parameters={"kid": kid, "use": "sig"})


class FakeGoogle:
    def __init__(self) -> None:
        self.key = new_key()
        self.pending: str | None = None
        self.token_status = 200
        self.token_requests: list[dict[str, str]] = []

    def prepare(
        self, nonce: str | None, *, key: RSAKey | None = None, **overrides: Any
    ) -> None:
        """Який `id_token` віддасть наступний обмін коду. `None` у override прибирає claim."""
        now = int(time.time())
        claims: dict[str, Any] = {
            "iss": ISSUER,
            "aud": CLIENT_ID,
            "sub": "google-sub-1",
            "email": "taras@example.com",
            "email_verified": True,
            "name": "Богдан Прикладенко",
            "iat": now,
            "exp": now + 3600,
            "nonce": nonce,
        }
        claims.update(overrides)
        claims = {name: value for name, value in claims.items() if value is not None}
        self.pending = jwt.encode(
            {"alg": "RS256", "kid": KEY_ID}, claims, key or self.key
        )

    def app(self) -> Starlette:
        async def metadata(_: Request) -> Response:
            return JSONResponse(
                {
                    "issuer": ISSUER,
                    "authorization_endpoint": f"{ISSUER}/authorize",
                    "token_endpoint": f"{ISSUER}/token",
                    "jwks_uri": f"{ISSUER}/jwks",
                    "response_types_supported": ["code"],
                    "subject_types_supported": ["public"],
                    "id_token_signing_alg_values_supported": ["RS256"],
                    "code_challenge_methods_supported": ["S256"],
                }
            )

        async def jwks(_: Request) -> Response:
            return JSONResponse(KeySet([self.key]).as_dict(private=False))

        async def token(request: Request) -> Response:
            form = {name: str(value) for name, value in (await request.form()).items()}
            basic = request.headers.get("authorization", "")
            if basic.startswith("Basic "):
                user, _, secret = b64decode(basic[6:]).decode().partition(":")
                form["basic_client_id"], form["basic_client_secret"] = user, secret
            self.token_requests.append(form)
            if self.token_status != 200:
                return JSONResponse(
                    {"error": "server_error"}, status_code=self.token_status
                )
            return JSONResponse(
                {
                    "access_token": "fake-access-token",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                    "id_token": self.pending,
                }
            )

        return Starlette(
            routes=[
                Route("/.well-known/openid-configuration", metadata),
                Route("/jwks", jwks),
                Route("/token", token, methods=["POST"]),
            ]
        )
