"""Мережа-пустушка для адаптерів джерел: httpx2 MockTransport, запити запам'ятовуються."""

import json
from pathlib import Path

import httpx2

from application.ports.job_sources import JobSource
from domain.sources.kinds import SourceKind
from infrastructure.sources import build_sources
from infrastructure.sources.http import Fetcher

PAUSE = 7.0


class Scripted:
    """Віддає відповіді за чергою (виняток — кидається; остання повторюється), рахує запити
    й паузи між повторами."""

    def __init__(self, *outcomes: httpx2.Response | Exception) -> None:
        self.outcomes = list(outcomes)
        self.requests: list[httpx2.Request] = []
        self.pauses: list[float] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        outcome = self.outcomes.pop(0) if len(self.outcomes) > 1 else self.outcomes[0]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    async def _pause(self, seconds: float) -> None:
        self.pauses.append(seconds)

    def fetcher(self) -> Fetcher:
        client = httpx2.AsyncClient(transport=httpx2.MockTransport(self))
        return Fetcher(client, sleep=self._pause, pause=PAUSE)

    def source(self, kind: SourceKind) -> JobSource:
        return build_sources(self.fetcher())[kind]


def ok(body: bytes = b"{}") -> httpx2.Response:
    return httpx2.Response(200, content=body)


def serve_json(data: object) -> Scripted:
    return Scripted(ok(json.dumps(data).encode()))


def serve_xml(xml: str | bytes) -> Scripted:
    return Scripted(ok(xml.encode() if isinstance(xml, str) else xml))


def serve_fixture(directory: Path, name: str) -> Scripted:
    return Scripted(ok((directory / name).read_bytes()))
