"""ATS-lint: детермінована перевірка PDF документа, без LLM. Звіряє текст, який бачить парсер
ATS (витягнутий з PDF), із задуманим: той самий порядок, нічого зайвого чи прихованого, без
невидимих символів, заголовки окремими рядками, шрифти вбудовані, сторінок не забагато. Рахує
покриття ключових слів з аналізу. Гігієна тексту (подвійні пробіли, переноси всередині поля, маркери
списку, шаблони «[…]») і покриття рахуються й по самому тексту, без рендеру. Документ із зауваженнями
не зберігається: Claude перевіряє його (check_*) і виправляє до збереження."""

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import StrEnum

from domain.analysis.keywords import spellings

# Невидимі людині, але видимі парсеру: format (zero-width, bidi, soft hyphen, BOM, tag-символи),
# керівні, приватні й сурогати. Пробіли й переноси рядків — не про це.
INVISIBLE_CATEGORIES = frozenset({"Cf", "Cc", "Co", "Cs"})
# Маркер пункту списку малює шаблон, у вмісті його нема.
LIST_MARKERS = frozenset({"•"})
SNIPPET_WORDS = 8
MAX_SNIPPETS = 3
# Рядок у PDF, що закінчується дефісом усередині слова («micro-» / «services», «event-» /
# «driven»): так верстка переносить довгі слова, читається як одне слово.
HYPHEN_BREAK = re.compile(r"(?<=\w-)[ \t]*\n[ \t]*(?=\w)")
# «[Company]», «[Hiring Manager]» — шаблон, який Claude забув заповнити.
PLACEHOLDER = re.compile(r"\[[^\]]*\]")
# Будь-який пробільний символ, крім звичайного пробілу: перенос рядка, табуляція, nbsp…
ODD_SPACE = re.compile(r"[^\S ]")
DOUBLE_SPACE = re.compile(r" {2,}")
# Маркер пункту на початку тексту: «•», «- », «– », «* ».
LEADING_MARKER = re.compile(r"[•·▪●‣◦]|[-–—*]\s")


class LintCode(StrEnum):
    INVISIBLE_CHARS = "invisible_chars"
    UNEXPECTED_TEXT = "unexpected_text"
    MISSING_TEXT = "missing_text"
    ORDER = "order"
    HEADINGS = "headings"
    FONTS_NOT_EMBEDDED = "fonts_not_embedded"
    PAGES = "pages"
    PARSER_MISMATCH = "parser_mismatch"
    # Текст ще до рендеру: поле не пройшло розбір, факти чи фото (текст — із повідомлення помилки).
    INVALID_VALUE = "invalid_value"
    LINE_BREAK = "line_break"
    DOUBLE_SPACE = "double_space"
    LIST_MARKER = "list_marker"
    PLACEHOLDER = "placeholder"


@dataclass(frozen=True, slots=True)
class Layout:
    """Задуманий текст документа в порядку читання — як його малює шаблон PDF.
    furniture — колонтитул: що шаблон повторює на сторінках (ім'я, посада); він, як і
    номери сторінок, може стояти між сторінками і не вважається зайвим текстом."""

    lines: tuple[str, ...]
    headings: tuple[str, ...]
    max_pages: int
    furniture: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PdfLayer:
    """Що в PDF бачить парсер: текстовий шар, кількість сторінок, шрифти без вбудовування."""

    text: str
    pages: int
    unembedded_fonts: tuple[str, ...] = ()
    second_text: str | None = None


@dataclass(frozen=True, slots=True)
class LintIssue:
    code: LintCode
    message: str


@dataclass(frozen=True, slots=True)
class KeywordCoverage:
    """Ключові слова з аналізу вакансії: є в тексті PDF чи нема."""

    covered: tuple[str, ...]
    missing: tuple[str, ...]

    @property
    def percent(self) -> int:
        total = len(self.covered) + len(self.missing)
        return round(100 * len(self.covered) / total) if total else 100

    def meets(self, threshold: int) -> bool:
        """Точне порівняння без округлення: 43 із 48 (89,6 %) не досягають 90."""
        return 100 * len(self.covered) >= threshold * (
            len(self.covered) + len(self.missing)
        )


@dataclass(frozen=True, slots=True)
class LintReport:
    """Звіт на момент збереження. keywords None — вакансію ще не проаналізовано."""

    pages: int
    issues: tuple[LintIssue, ...] = ()
    keywords: KeywordCoverage | None = None

    @property
    def passed(self) -> bool:
        """Покриття ключових слів не впливає: слово без факту під ним і не має бути в CV."""
        return not self.issues


def lint(layout: Layout, layer: PdfLayer, keywords: tuple[str, ...] = ()) -> LintReport:
    text = HYPHEN_BREAK.sub("", layer.text)
    issues = (
        *_invisible(layout, layer),
        *_text(layout, text, layer.pages),
        *_headings(layout, text),
        *_format(layout, layer),
        *_second_parser(text, layer.second_text),
    )
    coverage = _coverage(keywords, text) if keywords else None
    return LintReport(layer.pages, issues, coverage)


def _invisible(layout: Layout, layer: PdfLayer) -> Iterator[LintIssue]:
    in_content = False
    for line in layout.lines:
        if found := _invisible_chars(line):
            in_content = True
            yield LintIssue(
                LintCode.INVISIBLE_CHARS,
                f"Невидимі символи {found} у рядку {_quote(line)} — прибери їх.",
            )
    # Те, що прийшло з вмісту, у PDF уже назване вище; тут — лише те, що додав рендер.
    if not in_content and (found := _invisible_chars(layer.text)):
        yield LintIssue(LintCode.INVISIBLE_CHARS, f"Невидимі символи {found} у PDF.")


def _text(layout: Layout, text: str, pages: int) -> Iterator[LintIssue]:
    expected = _words("\n".join(layout.lines))
    expected_keys = [word.casefold() for word in expected]
    actual = _without_furniture(expected_keys, _words(text), layout.furniture, pages)
    actual_keys = [word.casefold() for word in actual]
    if expected_keys == actual_keys:
        return
    if Counter(expected_keys) == Counter(actual_keys):
        start = next(
            i
            for i, pair in enumerate(zip(expected_keys, actual_keys, strict=True))
            if pair[0] != pair[1]
        )
        yield LintIssue(
            LintCode.ORDER,
            "PDF читається в іншому порядку, ніж задумано (кілька колонок?), "
            f"починаючи з {_quote(' '.join(actual[start:]))}.",
        )
        return
    missing: list[str] = []
    extra: list[str] = []
    matcher = SequenceMatcher(None, expected_keys, actual_keys, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in {"delete", "replace"}:
            missing.append(_quote(" ".join(expected[i1:i2])))
        if tag in {"insert", "replace"}:
            extra.append(_quote(" ".join(actual[j1:j2])))
    if extra:
        yield LintIssue(
            LintCode.UNEXPECTED_TEXT,
            f"У PDF є текст, якого нема в документі (прихований?): {_some(extra)}.",
        )
    if missing:
        yield LintIssue(
            LintCode.MISSING_TEXT,
            f"Текст документа не витягується з PDF: {_some(missing)}.",
        )


def _without_furniture(
    expected_keys: list[str], actual: list[str], furniture: tuple[str, ...], pages: int
) -> list[str]:
    """Прибирає з країв вставок колонтитул і номери сторінок: між сторінками вони законні.
    Що лишилося від вставки — справді зайвий текст."""
    phrases = [[w.casefold() for w in _words(phrase)] for phrase in furniture]
    reversed_phrases = [phrase[::-1] for phrase in phrases]
    numbers = {str(page) for page in range(1, pages + 1)}
    actual_keys = [word.casefold() for word in actual]
    matcher = SequenceMatcher(None, expected_keys, actual_keys, autojunk=False)
    drop: list[tuple[int, int]] = []
    for tag, _, _, j1, j2 in matcher.get_opcodes():
        if tag != "insert":
            continue
        chunk = actual_keys[j1:j2]
        head = _furniture_prefix(chunk, phrases, numbers)
        tail = 0
        if head < len(chunk):
            tail = _furniture_prefix(chunk[::-1], reversed_phrases, numbers)
        drop += [(j2 - tail, j2), (j1, j1 + head)]
    for j1, j2 in sorted(drop, reverse=True):
        del actual[j1:j2]
    return actual


def _furniture_prefix(
    words: list[str], phrases: list[list[str]], numbers: set[str]
) -> int:
    """Скільки слів на початку — колонтитул чи номери сторінок."""
    i = 0
    while i < len(words):
        phrase = next((p for p in phrases if p and words[i : i + len(p)] == p), None)
        if phrase is not None:
            i += len(phrase)
        elif words[i] in numbers:
            i += 1
        else:
            break
    return i


def _headings(layout: Layout, text: str) -> Iterator[LintIssue]:
    lines = {_key(line) for line in text.splitlines()}
    missing = [heading for heading in layout.headings if _key(heading) not in lines]
    if missing:
        yield LintIssue(
            LintCode.HEADINGS,
            f"Заголовки не окремим рядком у PDF: {', '.join(missing)}.",
        )


def _format(layout: Layout, layer: PdfLayer) -> Iterator[LintIssue]:
    if layer.unembedded_fonts:
        yield LintIssue(
            LintCode.FONTS_NOT_EMBEDDED,
            f"Шрифти не вбудовані: {', '.join(layer.unembedded_fonts)}.",
        )
    if layer.pages > layout.max_pages:
        yield LintIssue(
            LintCode.PAGES,
            f"{layer.pages} сторінок, а можна до {layout.max_pages} — скороти.",
        )


def _second_parser(text: str, second_text: str | None) -> Iterator[LintIssue]:
    """Слова, які бачить перший парсер, а другий — ні: порядок рядків у двох парсерів різний,
    тож порівнюється склад слів."""
    if second_text is None:
        return
    seen = Counter(
        word.casefold() for word in _words(HYPHEN_BREAK.sub("", second_text))
    )
    lost: list[str] = []
    for word in _words(text):
        if seen[word.casefold()] > 0:
            seen[word.casefold()] -= 1
        else:
            lost.append(word)
    if lost:
        yield LintIssue(
            LintCode.PARSER_MISMATCH,
            "Другий парсер PDF (pdftotext) не бачить слів, які бачить перший: "
            f"{_some([_quote(word) for word in lost])} — проблема шаблону?",
        )


def _coverage(keywords: tuple[str, ...], text: str) -> KeywordCoverage:
    haystack = _key(text)
    covered: list[str] = []
    missing: list[str] = []
    seen: set[frozenset[str]] = set()
    for keyword in keywords:
        keys = frozenset(filter(None, map(_key, spellings(keyword))))
        if not keys or keys in seen:
            continue
        seen.add(keys)
        found = any(
            re.search(rf"(?<!\w){re.escape(key)}(?!\w)", haystack) for key in keys
        )
        (covered if found else missing).append(keyword)
    return KeywordCoverage(tuple(covered), tuple(missing))


def keyword_coverage(
    keywords: tuple[str, ...], lines: tuple[str, ...]
) -> KeywordCoverage | None:
    """Покриття ключових слів у задуманому тексті (без рендеру). None — слів нема."""
    return _coverage(keywords, "\n".join(lines)) if keywords else None


def cv_text_issues(
    fields: Iterable[str], bullets: Iterable[str]
) -> tuple[LintIssue, ...]:
    """Гігієна сирого тексту CV до рендеру: поле — один рядок без невидимих символів, переносів,
    табуляцій і подвійних пробілів, без шаблонів «[…]»; пункт (bullet) ще й без маркера списку."""
    marked = tuple(bullets)
    return tuple(_text_issues((*fields, *marked), marked, placeholders=True))


def letter_text_issues(text: str) -> tuple[LintIssue, ...]:
    """Те саме для листа: одинарний перенос і порожній рядок між абзацами дозволені, тож
    перевіряється кожен рядок окремо. Шаблон «[…]» у листі ловить домен (`CoverLetter`)."""
    lines = tuple(line.strip() for line in text.splitlines() if line.strip())
    return tuple(_text_issues(lines, lines, placeholders=False))


def _text_issues(
    fields: Iterable[str], marked: Iterable[str], *, placeholders: bool
) -> Iterator[LintIssue]:
    invisible: list[str] = []
    odd: list[str] = []
    double: list[str] = []
    template: list[str] = []
    for text in fields:
        shown = _quote(text)
        if found := _invisible_chars(text):
            invisible.append(f"{found} у {shown}")
        if match := ODD_SPACE.search(text):
            odd.append(f"U+{ord(match.group()):04X} у {shown}")
        if DOUBLE_SPACE.search(text.strip()):
            double.append(shown)
        if placeholders and (match := PLACEHOLDER.search(text)):
            template.append(f"{match.group()} у {shown}")
    listed = [_quote(text) for text in marked if LEADING_MARKER.match(text.lstrip())]
    for code, details, message in (
        (LintCode.INVISIBLE_CHARS, invisible, "Невидимі символи — прибери їх"),
        (
            LintCode.LINE_BREAK,
            odd,
            "Переноси рядків, табуляції чи незвичні пробіли всередині поля "
            "(кожне поле — один рядок)",
        ),
        (LintCode.DOUBLE_SPACE, double, "Подвійні пробіли — залиш один"),
        (
            LintCode.LIST_MARKER,
            listed,
            "Пункт починається з маркера списку, а його малює шаблон — прибери",
        ),
        (LintCode.PLACEHOLDER, template, "Незаповнений шаблон у квадратних дужках"),
    ):
        if details:
            yield LintIssue(code, f"{message}: {_some(details)}.")


def is_invisible(char: str) -> bool:
    """Символ, якого людина не бачить, а парсер бачить (пробіли й переноси — видимі)."""
    return not char.isspace() and unicodedata.category(char) in INVISIBLE_CATEGORIES


def _words(text: str) -> list[str]:
    """Слова тексту так, як їх порівнює lint: NFKC (лігатури → літери), без невидимих
    символів (про них — окрема перевірка) і без маркерів списку."""
    clean = "".join(
        c for c in unicodedata.normalize("NFKC", text) if not is_invisible(c)
    )
    return [word for word in clean.split() if word not in LIST_MARKERS]


def _key(text: str) -> str:
    return " ".join(_words(text)).casefold()


def _invisible_chars(text: str) -> str:
    found = sorted({c for c in text if is_invisible(c)})
    return ", ".join(f"U+{ord(c):04X}" for c in found)


def _quote(text: str) -> str:
    words = text.split()
    tail = " …" if len(words) > SNIPPET_WORDS else ""
    return f"«{' '.join(words[:SNIPPET_WORDS])}{tail}»"


def _some(snippets: list[str]) -> str:
    more = len(snippets) - MAX_SNIPPETS
    return "; ".join(snippets[:MAX_SNIPPETS]) + (f" і ще {more}" if more > 0 else "")
