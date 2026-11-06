"""Фейки виходу документів для core-тестів: рендер, перевірка PDF і файли без WeasyPrint, pypdf і диска.

«PDF» — це маркер; `Shop` пам'ятає, який задуманий текст за ним стоїть, тож інспектор повертає
текстовий шар, який lint вважає ідеальним (1 сторінка). Тест може змінити шар (`tweak`) або
зламати рендер чи запис файлу.
"""

from collections.abc import Callable
from dataclasses import dataclass, field, replace

from application.ports.documents import DocumentOutput
from domain.documents.document import CoverLetter, Cv
from domain.documents.ids import DocumentId
from domain.documents.layout import cover_letter_layout, cv_layout
from domain.documents.lint import Layout, PdfLayer
from domain.profile.contacts import Contacts


@dataclass
class Shop:
    layouts: dict[bytes, Layout] = field(default_factory=dict)
    # Що рендер отримав: (вид, вміст, контакти).
    rendered: list[tuple[str, Cv | CoverLetter, Contacts]] = field(default_factory=list)
    # Фото, з яким відрендерено кожне CV (None — без фото), у порядку рендерів.
    photos: list[bytes | None] = field(default_factory=list)
    files: dict[DocumentId, bytes] = field(default_factory=dict)
    # Змінює шар PDF, який бачить інспектор (сторінки, прихований текст…).
    tweak: Callable[[PdfLayer], PdfLayer] = field(default=lambda layer: layer)
    fail_render: bool = False
    fail_write: bool = False

    def register(self, layout: Layout) -> bytes:
        pdf = f"%PDF-fake-{len(self.layouts) + 1}".encode()
        self.layouts[pdf] = layout
        return pdf

    def output(self) -> DocumentOutput:
        return DocumentOutput(FakeRenderer(self), FakeInspector(self), FakeFiles(self))


class FakeRenderer:
    def __init__(self, shop: Shop) -> None:
        self._shop = shop

    async def render_cv(
        self, cv: Cv, contacts: Contacts, photo: bytes | None = None
    ) -> bytes:
        if self._shop.fail_render:
            raise RuntimeError("render failed")
        self._shop.rendered.append(("cv", cv, contacts))
        self._shop.photos.append(photo)
        return self._shop.register(cv_layout(cv, contacts))

    async def render_cover_letter(
        self, letter: CoverLetter, contacts: Contacts
    ) -> bytes:
        if self._shop.fail_render:
            raise RuntimeError("render failed")
        self._shop.rendered.append(("cl", letter, contacts))
        return self._shop.register(cover_letter_layout(letter, contacts))


class FakeInspector:
    def __init__(self, shop: Shop) -> None:
        self._shop = shop

    async def inspect(self, pdf: bytes) -> PdfLayer:
        layout = self._shop.layouts[pdf]
        return self._shop.tweak(PdfLayer("\n".join(layout.lines), 1))


class FakeFiles:
    def __init__(self, shop: Shop) -> None:
        self._shop = shop

    async def write(self, document_id: DocumentId, data: bytes) -> None:
        if self._shop.fail_write:
            raise OSError("disk full")
        self._shop.files[document_id] = data

    async def read(self, document_id: DocumentId) -> bytes | None:
        return self._shop.files.get(document_id)

    async def exists(self, document_id: DocumentId) -> bool:
        return document_id in self._shop.files

    async def delete(self, document_id: DocumentId) -> None:
        self._shop.files.pop(document_id, None)


def with_pages(pages: int) -> Callable[[PdfLayer], PdfLayer]:
    return lambda layer: replace(layer, pages=pages)


def with_hidden_text(text: str) -> Callable[[PdfLayer], PdfLayer]:
    return lambda layer: replace(layer, text=f"{layer.text}\n{text}")
