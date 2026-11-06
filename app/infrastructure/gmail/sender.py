"""Відправка листів у Gmail: REST messages.send через httpx2. Окремий refresh token лише зі
scope gmail.send (процес синку має інший, лише на читання). Access token береться на кожну
відправку: листів мало, кешу не треба. Збій Google — `MailUnavailable` без тексту відповіді."""

import base64
from email.message import EmailMessage
from email.utils import formataddr

import httpx2

from domain.mail.outgoing import MailUnavailable, OutgoingMail
from infrastructure.gmail.client import (
    API_URL,
    OAUTH_URL,
    TIMEOUT_SECONDS,
    GmailCredentials,
)

GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
FROM_NAME = "joboffer"


class GmailSender:
    """`MailSender` поверх Gmail API; `address` — скринька застосунку (відправник)."""

    def __init__(
        self,
        creds: GmailCredentials,
        address: str,
        transport: httpx2.AsyncBaseTransport | None = None,
    ) -> None:
        self._creds = creds
        self._address = address
        self._transport = transport

    async def send(self, mail: OutgoingMail) -> None:
        raw = self._raw(mail)
        async with httpx2.AsyncClient(
            base_url=API_URL, timeout=TIMEOUT_SECONDS, transport=self._transport
        ) as http:
            token = await self._access_token(http)
            try:
                response = await http.post(
                    "messages/send",
                    json={"raw": raw},
                    headers={"Authorization": f"Bearer {token}"},
                )
            except httpx2.HTTPError as exc:
                raise MailUnavailable(
                    f"Gmail недоступний: {type(exc).__name__}."
                ) from exc
        if not response.is_success:
            raise MailUnavailable(
                f"Gmail відповів {response.status_code} на messages/send."
            )

    def _raw(self, mail: OutgoingMail) -> str:
        message = EmailMessage()
        try:
            message["From"] = formataddr((FROM_NAME, self._address))
            message["To"] = mail.to
            message["Subject"] = mail.subject
        except ValueError:
            # Переведення рядка в адресі чи темі — спроба підмінити заголовки.
            raise MailUnavailable(
                "Лист не сформовано: некоректний заголовок."
            ) from None
        message.set_content(mail.body, charset="utf-8", cte="base64")
        return base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")

    async def _access_token(self, http: httpx2.AsyncClient) -> str:
        try:
            response = await http.post(
                OAUTH_URL,
                data={
                    "grant_type": "refresh_token",
                    "client_id": self._creds.client_id,
                    "client_secret": self._creds.client_secret,
                    "refresh_token": self._creds.refresh_token,
                },
            )
        except httpx2.HTTPError as exc:
            raise MailUnavailable(
                f"Gmail: токен недоступний: {type(exc).__name__}."
            ) from exc
        if not response.is_success:
            raise MailUnavailable(
                f"Gmail: не вдалося оновити access token ({response.status_code})."
            )
        return str(response.json()["access_token"])
