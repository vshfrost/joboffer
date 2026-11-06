"""PDF очима парсера ATS (pypdf): текстовий шар, сторінки, шрифти без вбудовування."""

import asyncio
from collections.abc import Iterator
from dataclasses import replace
from io import BytesIO
from typing import Protocol, cast

from pypdf import PageObject, PdfReader
from pypdf.generic import ArrayObject, DictionaryObject

from domain.documents.lint import PdfLayer

FONT_FILES = ("/FontFile", "/FontFile2", "/FontFile3")


class PypdfInspector:
    def __init__(self, second: SecondParser | None = None) -> None:
        self._second = second

    async def inspect(self, pdf: bytes) -> PdfLayer:
        layer = await asyncio.to_thread(_inspect, pdf)
        if self._second is None:
            return layer
        return replace(layer, second_text=await self._second.read(pdf))


class SecondParser(Protocol):
    async def read(self, pdf: bytes) -> str: ...


def _inspect(pdf: bytes) -> PdfLayer:
    reader = PdfReader(BytesIO(pdf))
    text = "\n".join(page.extract_text() for page in reader.pages)
    unembedded = {name for page in reader.pages for name in _unembedded(page)}
    return PdfLayer(text, len(reader.pages), tuple(sorted(unembedded)))


def _unembedded(page: PageObject) -> Iterator[str]:
    resources = page.get("/Resources")
    fonts = None if resources is None else resources.get_object().get("/Font")
    if fonts is None:
        return
    for reference in fonts.get_object().values():
        font = reference.get_object()
        # Type3 малює гліфи самим PDF — вбудовувати нічого.
        if font.get("/Subtype") != "/Type3" and not _embedded(font):
            yield str(font.get("/BaseFont", "?")).lstrip("/")


def _embedded(font: DictionaryObject) -> bool:
    if "/DescendantFonts" in font:
        # Type0: шрифт із файлом — перший (і єдиний) нащадок.
        descendants = cast(ArrayObject, font["/DescendantFonts"].get_object())
        font = cast(DictionaryObject, descendants[0].get_object())
    descriptor = font.get("/FontDescriptor")
    return descriptor is not None and any(
        key in descriptor.get_object() for key in FONT_FILES
    )
