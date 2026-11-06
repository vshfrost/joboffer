"""Скринька застосунку в Gmail: REST API v1 через httpx2. Access token — з refresh token
(OAuth2 token endpoint Google); лише scope gmail.readonly. Refresh token має тільки процес синку."""

import base64
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx2

from domain.mail.mail import CursorExpired, IncomingMail, MailboxError, MailChanges
from infrastructure.gmail.parse import parse_message

GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
API_URL = "https://gmail.googleapis.com/gmail/v1/users/me/"
OAUTH_URL = "https://oauth2.googleapis.com/token"
PAGE_SIZE = 500
TIMEOUT_SECONDS = 30.0
# Access token оновлюється трохи раніше, ніж спливе його строк.
TOKEN_EXPIRY_MARGIN = 60.0
DEFAULT_TOKEN_LIFETIME = 3600.0


@dataclass(frozen=True, slots=True)
class GmailCredentials:
    """OAuth-креди скриньки: секрети не потрапляють у repr."""

    client_id: str
    client_secret: str = field(repr=False)
    refresh_token: str = field(repr=False)


@dataclass(frozen=True, slots=True)
class GmailProfile:
    address: str
    history_id: str


def connect(creds: GmailCredentials) -> GmailMailbox:
    """Скринька без мережі при створенні: з'єднання й access token — при першому запиті."""
    return GmailMailbox(
        creds, httpx2.AsyncClient(base_url=API_URL, timeout=TIMEOUT_SECONDS)
    )


class GmailMailbox:
    """`Mailbox` поверх Gmail API. Курсор — historyId."""

    def __init__(
        self,
        creds: GmailCredentials,
        http: httpx2.AsyncClient,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._creds = creds
        self._http = http
        self._monotonic = monotonic
        self._token = ""
        self._token_expires_at = 0.0

    async def aclose(self) -> None:
        await self._http.aclose()

    async def profile(self) -> GmailProfile:
        page = self._ok(await self._get("profile", {}), "profile")
        return GmailProfile(str(page["emailAddress"]).lower(), str(page["historyId"]))

    async def profile_cursor(self) -> str:
        return (await self.profile()).history_id

    async def changes(self, cursor: str) -> MailChanges:
        # Упорядкована множина: той самий лист буває в кількох записах історії.
        ids: dict[str, None] = {}
        history_id = cursor
        params = {"startHistoryId": cursor, "historyTypes": "messageAdded"}
        async for page in self._pages("history", params, expired_cursor=True):
            for record in page.get("history", []):
                for added in record.get("messagesAdded", []):
                    ids[str(added["message"]["id"])] = None
            history_id = str(page.get("historyId", history_id))
        return MailChanges(tuple(ids), history_id)

    async def since(self, moment: datetime) -> list[str]:
        """Від старіших до новіших (Gmail віддає новіші першими)."""
        params = {"q": f"after:{int(moment.timestamp())}", "includeSpamTrash": "true"}
        ids = [
            str(item["id"])
            async for page in self._pages("messages", params)
            for item in page.get("messages", [])
        ]
        return ids[::-1]

    async def message(self, message_id: str) -> IncomingMail | None:
        path = f"messages/{message_id}"
        response = await self._get(path, {"format": "raw"})
        if response.status_code == httpx2.codes.NOT_FOUND:
            return None
        page = self._ok(response, path)
        raw = str(page["raw"])
        return parse_message(
            base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)),
            message_id=str(page["id"]),
            received_at=datetime.fromtimestamp(int(page["internalDate"]) / 1000, UTC),
        )

    async def _pages(
        self, path: str, params: dict[str, str], *, expired_cursor: bool = False
    ) -> AsyncIterator[dict[str, Any]]:
        page_token = ""
        while True:
            query = {**params, "maxResults": str(PAGE_SIZE)}
            if page_token:
                query["pageToken"] = page_token
            response = await self._get(path, query)
            if expired_cursor and response.status_code == httpx2.codes.NOT_FOUND:
                raise CursorExpired("Gmail: курсор змін протух — потрібен ресинк.")
            page = self._ok(response, path)
            yield page
            page_token = str(page.get("nextPageToken", ""))
            if not page_token:
                return

    async def _get(self, path: str, params: dict[str, str]) -> httpx2.Response:
        """GET з access token; 401 — токен оновлюється й запит повторюється один раз."""
        if self._monotonic() >= self._token_expires_at:
            await self._refresh()
        response = await self._send(path, params)
        if response.status_code == httpx2.codes.UNAUTHORIZED:
            await self._refresh()
            response = await self._send(path, params)
        return response

    async def _send(self, path: str, params: dict[str, str]) -> httpx2.Response:
        try:
            return await self._http.get(
                path, params=params, headers={"Authorization": f"Bearer {self._token}"}
            )
        except httpx2.HTTPError as exc:
            raise MailboxError(f"Gmail недоступний: {type(exc).__name__}.") from exc

    async def _refresh(self) -> None:
        try:
            response = await self._http.post(
                OAUTH_URL,
                data={
                    "grant_type": "refresh_token",
                    "client_id": self._creds.client_id,
                    "client_secret": self._creds.client_secret,
                    "refresh_token": self._creds.refresh_token,
                },
            )
        except httpx2.HTTPError as exc:
            raise MailboxError(
                f"Gmail: токен недоступний: {type(exc).__name__}."
            ) from exc
        if not response.is_success:
            raise MailboxError(
                "Gmail: не вдалося оновити access token (refresh token відкликано чи "
                "прострочено?) — потрібен новий refresh token."
            )
        payload: dict[str, Any] = response.json()
        self._token = str(payload["access_token"])
        lifetime = float(payload.get("expires_in", DEFAULT_TOKEN_LIFETIME))
        self._token_expires_at = self._monotonic() + lifetime - TOKEN_EXPIRY_MARGIN

    @staticmethod
    def _ok(response: httpx2.Response, path: str) -> dict[str, Any]:
        if not response.is_success:
            raise MailboxError(f"Gmail відповів {response.status_code} на {path}.")
        page: dict[str, Any] = response.json()
        return page
