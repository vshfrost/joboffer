"""Use cases одноразових посилань на PDF: агент просить посилання, shell агента качає за ним файл
без сесії веба. REST і MCP викликають саме їх."""

from collections.abc import Callable

from application.contracts.actor import Actor
from application.contracts.documents import DownloadLinkData, PdfFileData
from application.ports.clock import Clock
from application.ports.documents import DocumentFiles
from application.ports.downloads import DownloadUnitOfWork
from application.ports.sessions import TokenGenerator
from domain.documents.download import DOWNLOAD_TTL
from domain.documents.layout import pdf_file_name
from domain.identity.session import TokenDigest
from domain.shared.errors import NotFound

NOT_VALID = "Посилання недійсне."


class DocumentDownloads:
    def __init__(
        self,
        unit_of_work: Callable[[], DownloadUnitOfWork],
        clock: Clock,
        tokens: TokenGenerator,
        files: DocumentFiles,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock
        self._tokens = tokens
        self._files = files

    async def create_link(self, actor: Actor, document_number: int) -> DownloadLinkData:
        """Одноразове посилання на 10 хвилин. `NotFound` — документа нема чи він чужий."""
        user = actor.user_id
        async with self._unit_of_work() as uow:
            document = await uow.documents.get(user, document_number)
            if document is None:
                raise NotFound(f"Документ {document_number} не знайдено.")
            full_name = (await uow.profiles.get(user)).contacts.full_name
            token = self._tokens.new()
            expires_at = self._clock.now() + DOWNLOAD_TTL
            await uow.download_links.add(
                user, document.id, TokenDigest.from_token(token), expires_at
            )
            await uow.commit()
        return DownloadLinkData(
            token=token,
            file_name=pdf_file_name(full_name, document.kind),
            expires_at=expires_at,
        )

    async def redeem(self, token: str) -> PdfFileData:
        """PDF за посиланням, яке при цьому стає використаним. `NotFound` — токена нема,
        його вже використано, строк минув чи файлу PDF нема (відповідь однакова; без файлу
        посилання лишається невикористаним)."""
        async with self._unit_of_work() as uow:
            grant = await uow.download_links.redeem(
                TokenDigest.from_token(token), self._clock.now()
            )
            if grant is None:
                raise NotFound(NOT_VALID)
            document = await uow.documents.get(grant.user_id, grant.document_number)
            if document is None:
                raise NotFound(NOT_VALID)
            full_name = (await uow.profiles.get(grant.user_id)).contacts.full_name
            data = await self._files.read(document.id)
            if data is None:
                raise NotFound(NOT_VALID)
            await uow.commit()
        return PdfFileData(data=data, file_name=pdf_file_name(full_name, document.kind))
