"""Автентичність відправника: вердикт DMARC із заголовків листа, що пройшов ланцюжок
відправник → Cloudflare Email Routing → основний Gmail → пересилання → скринька застосунку.
Основа — знеособлена копія справжнього листа; варіанти — правки його заголовків."""

import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from domain.mail.sender_auth import AuthHeaders, SenderAuth, sender_auth
from infrastructure.gmail.parse import parse_message

FIXTURE = Path(__file__).parent / "gmail_fixtures" / "forwarded_company.eml"
RAW = FIXTURE.read_bytes().decode()
SENDER = "candidate@gmail.com"

Edit = Callable[[str], str]


def header_blocks(raw: str) -> list[str]:
    """Заголовки листа (без тіла), кожен із продовженнями рядків."""
    head = raw.split("\r\n\r\n", 1)[0]
    return re.split(r"\r\n(?=\S)", head)


def find(blocks: list[str], name: str, mark: str) -> int:
    """Індекс заголовка з цим іменем, у якому є mark (заголовків з однаковим іменем багато)."""
    return next(
        index
        for index, block in enumerate(blocks)
        if block.lower().startswith(f"{name.lower()}:") and mark in block
    )


def variant(*edits: tuple[str, str, Edit]) -> AuthHeaders:
    """Заголовки автентифікації справжнього листа після правок (ім'я, ознака, правка)."""
    blocks = header_blocks(RAW)
    for name, mark, edit in edits:
        index = find(blocks, name, mark)
        blocks[index] = edit(blocks[index])
    raw = "\r\n".join(blocks) + "\r\n\r\nbody"
    mail = parse_message(raw.encode(), message_id="m", received_at=datetime.now(UTC))
    return mail.auth_headers


def replace(old: str, new: str) -> Edit:
    def edit(block: str) -> str:
        assert old in block
        return block.replace(old, new)

    return edit


# Рядок верхнього Authentication-Results, який відрізняє його від нижнього (mx.cloudflare.net).
TOP = ("Authentication-Results", "mx.google.com")
CLOUDFLARE_AAR = ("ARC-Authentication-Results", "i=2; mx.cloudflare.net")
CLOUDFLARE_SEAL = ("ARC-Seal", "i=2;")
ARC_OK = "arc=pass (i=4"
ARC_BAD = "arc=fail (i=4"
SUMMARY_DMARC = "dmarc=pass fromdomain=gmail.com"


def test_real_chain_is_verified() -> None:
    assert sender_auth(variant(), SENDER) is SenderAuth.VERIFIED


def test_cloudflare_dmarc_fail_makes_the_sender_failed() -> None:
    headers = variant((*CLOUDFLARE_AAR, replace("dmarc=pass", "dmarc=fail")))

    assert sender_auth(headers, SENDER) is SenderAuth.FAILED


def test_cloudflare_verdict_wins_over_the_gmail_summary() -> None:
    # Підсумок Gmail каже fail, а Cloudflare, що перевіряв DMARC першим, — pass.
    headers = variant((*TOP, replace(SUMMARY_DMARC, "dmarc=fail fromdomain=gmail.com")))

    assert sender_auth(headers, SENDER) is SenderAuth.VERIFIED


def test_fake_authentication_results_below_the_real_one_is_ignored() -> None:
    # Верхній (справжній) каже fail; відправник вставив нижче свій «mx.google.com; dmarc=pass».
    blocks = header_blocks(RAW)
    top = find(blocks, *TOP)
    blocks[top] = (
        "Authentication-Results: mx.google.com; arc=none; "
        "dmarc=fail (p=NONE sp=QUARANTINE dis=NONE) header.from=gmail.com"
    )
    blocks.insert(
        top + 1,
        "Authentication-Results: mx.google.com; dmarc=pass header.from=gmail.com",
    )
    raw = "\r\n".join(blocks) + "\r\n\r\nbody"
    headers = parse_message(
        raw.encode(), message_id="m", received_at=datetime.now(UTC)
    ).auth_headers

    assert sender_auth(headers, SENDER) is SenderAuth.FAILED


def test_cloudflare_set_without_its_seal_is_ignored() -> None:
    # Печатку i=2 поставив не Cloudflare: його набір (fail) ігнорується, лишається підсумок
    # верхнього заголовка (pass).
    headers = variant(
        (*CLOUDFLARE_AAR, replace("dmarc=pass", "dmarc=fail")),
        (*CLOUDFLARE_SEAL, replace("d=cloudflare-email.net", "d=attacker.example")),
    )

    assert sender_auth(headers, SENDER) is SenderAuth.VERIFIED


def test_unsealed_cloudflare_pass_does_not_rescue_a_failing_summary() -> None:
    headers = variant(
        (*TOP, replace(SUMMARY_DMARC, "dmarc=fail fromdomain=gmail.com")),
        (*CLOUDFLARE_SEAL, replace("d=cloudflare-email.net", "d=attacker.example")),
    )

    assert sender_auth(headers, SENDER) is SenderAuth.FAILED


def test_arc_fail_falls_back_to_the_direct_verdict_of_the_top_header() -> None:
    # arc≠pass: Cloudflare (pass) не береться до уваги, вердикт — прямий dmarc зверху.
    failing = variant(
        (*TOP, replace(ARC_OK, ARC_BAD)),
        (*TOP, replace("dmarc=pass (p=NONE", "dmarc=fail (p=NONE")),
    )
    passing = variant((*TOP, replace(ARC_OK, ARC_BAD)))
    cloudflare_fail = variant(
        (*TOP, replace(ARC_OK, ARC_BAD)),
        (*CLOUDFLARE_AAR, replace("dmarc=pass", "dmarc=fail")),
    )

    assert sender_auth(failing, SENDER) is SenderAuth.FAILED
    assert sender_auth(passing, SENDER) is SenderAuth.VERIFIED
    assert sender_auth(cloudflare_fail, SENDER) is SenderAuth.VERIFIED


def test_top_header_from_another_server_is_unknown() -> None:
    headers = variant((*TOP, replace("mx.google.com;", "mx.attacker.example;")))

    assert sender_auth(headers, SENDER) is SenderAuth.UNKNOWN


def test_mail_without_authentication_headers_is_unknown() -> None:
    assert sender_auth((), SENDER) is SenderAuth.UNKNOWN
    arc_only = tuple(h for h in variant() if h[0] != "authentication-results")
    assert sender_auth(arc_only, SENDER) is SenderAuth.UNKNOWN


def test_verdict_for_another_domain_than_from_is_unknown() -> None:
    assert sender_auth(variant(), "hr@acme.example") is SenderAuth.UNKNOWN
    assert sender_auth(variant(), "") is SenderAuth.UNKNOWN


def test_domain_of_the_cloudflare_verdict_must_match_from() -> None:
    headers = variant(
        (*CLOUDFLARE_AAR, replace("header.from=gmail.com", "header.from=other.example"))
    )

    assert sender_auth(headers, SENDER) is SenderAuth.UNKNOWN
