"""Фейковий Gmail для інтеграційних тестів: токен-ендпоінт і messages.send в одному MockTransport.

Мережі нема; надіслані листи розбираються назад у повідомлення, з яких тест читає код.
"""

import base64
import email
import json
import re
from email import policy
from email.message import EmailMessage

import httpx2

from infrastructure.gmail.client import OAUTH_URL

CODE = re.compile(r"\b\d{6}\b")


class FakeMailbox:
    def __init__(self, *, send_status: int = 200) -> None:
        self.send_status = send_status
        self.messages: list[EmailMessage] = []

    def transport(self) -> httpx2.MockTransport:
        return httpx2.MockTransport(self._handle)

    def _handle(self, request: httpx2.Request) -> httpx2.Response:
        if str(request.url) == OAUTH_URL:
            return httpx2.Response(
                200, json={"access_token": "access-1", "expires_in": 3599}
            )
        if self.send_status != 200:
            return httpx2.Response(self.send_status, json={"error": "fail"})
        raw = json.loads(request.content)["raw"]
        self.messages.append(
            email.message_from_bytes(
                base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)),
                policy=policy.default,
                _class=EmailMessage,
            )
        )
        return httpx2.Response(200, json={"id": "sent-1"})

    def codes(self) -> list[str]:
        """Коди з усіх листів, що їх містять, від старіших до новіших."""
        return [
            found.group()
            for message in self.messages
            if (found := CODE.search(message.get_content()))
        ]

    def to(self) -> list[str]:
        return [str(message["To"]) for message in self.messages]
