"""Текст з недовірених джерел (листи): один рядок, невидимі символи, HTML → простий текст."""

import re
import unicodedata
from collections.abc import Iterable
from html.parser import HTMLParser

# Невидимі людині, але видимі парсеру: format (zero-width, bidi, soft hyphen, BOM, tag-символи),
# керівні, приватні й сурогати. Пробіли й переноси рядків — не про це.
INVISIBLE_CATEGORIES = frozenset({"Cf", "Cc", "Co", "Cs"})
# Вміст цих тегів — не текст.
SKIPPED_TAGS = frozenset({"head", "script", "style", "title"})
# Теги, що в тексті дають новий рядок.
BLOCK_TAGS = frozenset(
    {"br", "p", "div", "tr", "li", "ul", "ol", "table", "blockquote", "hr"}
    | {f"h{level}" for level in range(1, 7)}
)
MAX_BLANK_LINES = 1


def one_line(text: str) -> str:
    """Один рядок: пробіли й переноси всередині стискаються до одного пробілу, краї обрізаються."""
    return " ".join(text.split())


def is_invisible(char: str) -> bool:
    """Символ, якого людина не бачить, а парсер бачить (пробіли й переноси — видимі)."""
    return not char.isspace() and unicodedata.category(char) in INVISIBLE_CATEGORIES


def tidy_lines(lines: Iterable[str]) -> str:
    """Рядки без пробілів по краях, не більше одного порожнього підряд."""
    result: list[str] = []
    blank = 0
    for raw_line in lines:
        line = " ".join(raw_line.split())
        blank = blank + 1 if not line else 0
        if blank <= MAX_BLANK_LINES:
            result.append(line)
    return "\n".join(result).strip()


def html_to_text(html: str) -> str:
    """HTML → простий текст (stdlib): без тегів, скриптів і стилів, блоки — окремі рядки.
    Вхід — недовірені дані; результат — лише текст."""
    parser = _HtmlText()
    parser.feed(html)
    parser.close()
    return tidy_lines("".join(parser.parts).splitlines())


class _HtmlText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skipped = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in SKIPPED_TAGS:
            self._skipped += 1
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIPPED_TAGS:
            self._skipped = max(self._skipped - 1, 0)
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skipped:
            # Переноси й відступи в HTML-коді — не текст: як у браузері, це один пробіл.
            self.parts.append(re.sub(r"\s+", " ", data))
