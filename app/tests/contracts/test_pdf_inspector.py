"""PypdfInspector: PDF очима парсера ATS — текст, сторінки, шрифти без вбудовування (без pango)."""

from io import BytesIO

import pytest
from anyio.from_thread import BlockingPortal
from pypdf import PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject

from infrastructure.pdf.inspector import PypdfInspector
from infrastructure.pdf.pdftotext import PdftotextMissing, PdftotextReader


def font(subtype: str, **entries: object) -> DictionaryObject:
    return DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject(subtype),
            **{NameObject(f"/{key}"): value for key, value in entries.items()},
        }
    )


def pdf_with(pages: int, fonts: DictionaryObject | None = None) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        page = writer.add_blank_page(100, 100)
        if fonts is not None:
            page[NameObject("/Resources")] = DictionaryObject(
                {NameObject("/Font"): fonts}
            )
    data = BytesIO()
    writer.write(data)
    return data.getvalue()


def test_pages_are_counted(portal: BlockingPortal) -> None:
    layer = portal.call(PypdfInspector().inspect, pdf_with(3))

    assert (layer.pages, layer.unembedded_fonts) == (3, ())


def test_a_pdf_without_text_has_an_empty_text_layer(portal: BlockingPortal) -> None:
    assert portal.call(PypdfInspector().inspect, pdf_with(1)).text.strip() == ""


def test_fonts_that_are_not_embedded_are_found_by_name(portal: BlockingPortal) -> None:
    writer = PdfWriter()
    writer.add_blank_page(100, 100)  # без шрифтів
    page = writer.add_blank_page(100, 100)
    fonts = DictionaryObject(
        {
            NameObject("/F1"): font("/Type1", BaseFont=NameObject("/Helvetica")),
            NameObject("/F2"): font("/Type3"),
            NameObject("/F3"): font(
                "/Type0",
                BaseFont=NameObject("/Courier"),
                DescendantFonts=ArrayObject(
                    [font("/CIDFontType2", FontDescriptor=DictionaryObject())]
                ),
            ),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): fonts})
    data = BytesIO()
    writer.write(data)

    layer = portal.call(PypdfInspector().inspect, data.getvalue())

    # Type3 малює гліфи сам — вбудовувати нічого; Type0 дивимось по нащадку.
    assert (layer.pages, layer.unembedded_fonts) == (2, ("Courier", "Helvetica"))


def test_a_font_with_a_font_file_is_embedded(portal: BlockingPortal) -> None:
    descriptor = DictionaryObject({NameObject("/FontFile2"): DictionaryObject()})
    fonts = DictionaryObject(
        {
            NameObject("/F1"): font(
                "/TrueType",
                BaseFont=NameObject("/DejaVuSans"),
                FontDescriptor=descriptor,
            )
        }
    )

    layer = portal.call(PypdfInspector().inspect, pdf_with(1, fonts))

    assert layer.unembedded_fonts == ()


class StubReader:
    """Другий парсер — зовнішній процес, тож у цьому тесті підмінений."""

    async def read(self, pdf: bytes) -> str:
        return "second parser text"


def test_the_text_of_the_second_parser_rides_along(portal: BlockingPortal) -> None:
    layer = portal.call(PypdfInspector(StubReader()).inspect, pdf_with(1))

    assert layer.second_text == "second parser text"


def test_without_a_second_parser_there_is_no_second_text(
    portal: BlockingPortal,
) -> None:
    assert portal.call(PypdfInspector().inspect, pdf_with(1)).second_text is None


def test_a_missing_second_utility_fails_the_inspection(portal: BlockingPortal) -> None:
    inspector = PypdfInspector(PdftotextReader("pdftotext-that-is-not-installed"))

    with pytest.raises(PdftotextMissing):
        portal.call(inspector.inspect, pdf_with(1))
