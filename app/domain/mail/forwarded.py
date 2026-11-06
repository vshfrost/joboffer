"""Ручне пересилання: користувач сам пересилає відповідь компанії зі своєї пошти, тож From
листа — його власна адреса, а справжній відправник — у блоці пересланого листа. Лист вважається
ручним пересиланням, лише якщо From = email із профілю власника і DMARC пройдено (verified):
інакше це підробка «від себе». Текст листа — недовірені дані, тож відправник із блоку не
перевірений: статус подачі за таким листом сам не змінюється."""

import re
from dataclasses import dataclass

from domain.mail.sender_auth import SenderAuth
from domain.shared.text import is_invisible, one_line

# Скільки рядків заголовка читається після рядка «Forwarded message»: Gmail дає 4–5.
HEADER_LINES = 8
NAME_LIMIT = 200
SUBJECT_LIMIT = 300

# Заголовок блоку: Gmail (EN / ES / UK) і Apple Mail; береться перший, тобто верхній.
BLOCK_START = re.compile(
    r"^(?:-{2,}\s*(?:forwarded message|mensaje reenviado|переслане повідомлення)\s*-{2,}"
    r"|(?P<apple>begin forwarded message:?))$",
    re.IGNORECASE,
)
HEADER = re.compile(r"^([^\W\d_]+):\s*(.*)$")
FROM_LABELS = {"from", "de", "від"}
SUBJECT_LABELS = {"subject", "asunto", "тема"}
ADDRESS = re.compile(r"[a-z0-9._%+'-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)+", re.IGNORECASE)
ADDRESS_LIMIT = 254


@dataclass(frozen=True, slots=True)
class ForwardedMail:
    """Відправник і тема пересланого листа за блоком у тексті: недовірені дані."""

    from_address: str
    from_name: str = ""
    subject: str = ""


def manual_forward(
    owner_email: str, from_address: str, sender_auth: SenderAuth, text: str
) -> ForwardedMail | None:
    """Блок пересланого листа, якщо лист — ручне пересилання власника: From = його email із
    профілю (без регістру), відправник verified, у тексті є блок з адресою в рядку From."""
    if (
        sender_auth is not SenderAuth.VERIFIED
        or not owner_email
        or from_address.lower() != owner_email.strip().lower()
    ):
        return None
    return forwarded_block(text)


def forwarded_block(text: str) -> ForwardedMail | None:
    """Верхній блок пересланого листа: відправник (адреса, як у From, — нижнім регістром; ім'я)
    і тема. Блок без адреси в рядку From — не блок."""
    lines = [line.strip() for line in text.splitlines()]
    start, apple = _block_start(lines)
    if start is None:
        return None
    first = start + 1
    if apple:
        # Apple Mail лишає порожній рядок між «Begin forwarded message:» і заголовком.
        while first < len(lines) and not lines[first]:
            first += 1
    sender = ""
    subject = ""
    for line in lines[first : first + HEADER_LINES]:
        if not line:
            break
        header = HEADER.match(line)
        if header is None:
            continue
        label, value = header.group(1).lower(), header.group(2)
        if label in FROM_LABELS:
            sender = sender or value
        elif label in SUBJECT_LABELS:
            subject = subject or value
    found = ADDRESS.search(sender)
    if found is None or len(found.group()) > ADDRESS_LIMIT:
        return None
    name = ADDRESS.sub("", sender).replace("<>", "").replace('"', "")
    return ForwardedMail(
        from_address=found.group().lower(),
        from_name=_clean(name, NAME_LIMIT),
        subject=_clean(subject, SUBJECT_LIMIT),
    )


def _block_start(lines: list[str]) -> tuple[int | None, bool]:
    """Рядок, з якого починається верхній блок, і чи це Apple Mail."""
    for number, line in enumerate(lines):
        found = BLOCK_START.match(line)
        if found:
            return number, found.group("apple") is not None
    return None, False


def _clean(value: str, limit: int) -> str:
    visible = "".join(char for char in value if not is_invisible(char))
    return one_line(visible)[:limit]
