"""Вердикт DMARC із заголовків автентифікації, зібраних вручну (без листа-фікстури)."""

import pytest

from domain.mail.sender_auth import AuthHeaders, SenderAuth, sender_auth


def top(value: str) -> AuthHeaders:
    return (("authentication-results", value),)


@pytest.mark.parametrize(
    ("value", "verdict"),
    [
        ("mx.google.com; dmarc=pass header.from=acme.example", SenderAuth.VERIFIED),
        ("MX.Google.com; DMARC=PASS header.from=ACME.example", SenderAuth.VERIFIED),
        ("mx.google.com 1; dmarc=fail header.from=acme.example", SenderAuth.FAILED),
        ("mx.google.com; dmarc=none header.from=acme.example", SenderAuth.UNKNOWN),
        (
            "mx.google.com; dmarc=bestguesspass header.from=acme.example",
            SenderAuth.UNKNOWN,
        ),
        ("mx.google.com; dmarc=temperror header.from=acme.example", SenderAuth.UNKNOWN),
        ("mx.google.com; spf=pass smtp.mailfrom=acme.example", SenderAuth.UNKNOWN),
        ("mx.google.com; dmarc=pass", SenderAuth.UNKNOWN),
        (
            "mx.google.com; garbage; dmarc=pass header.from=acme.example",
            SenderAuth.VERIFIED,
        ),
        ("", SenderAuth.UNKNOWN),
    ],
)
def test_direct_dmarc_verdict_without_arc(value: str, verdict: SenderAuth) -> None:
    assert sender_auth(top(value), "hr@acme.example") is verdict


def test_semicolon_inside_quotes_or_a_comment_cannot_inject_a_verdict() -> None:
    quoted = (
        'mx.google.com; spf=pass smtp.mailfrom="x; dmarc=pass header.from=acme.example"; '
        "dmarc=fail header.from=acme.example"
    )
    commented = (
        "mx.google.com; spf=pass (domain of x; dmarc=pass header.from=acme.example) "
        "smtp.mailfrom=x; dmarc=fail header.from=acme.example"
    )

    assert sender_auth(top(quoted), "hr@acme.example") is SenderAuth.FAILED
    assert sender_auth(top(commented), "hr@acme.example") is SenderAuth.FAILED


def test_first_of_several_dmarc_results_decides() -> None:
    value = (
        "mx.google.com; dmarc=fail header.from=acme.example; "
        "dmarc=pass header.from=acme.example"
    )

    assert sender_auth(top(value), "hr@acme.example") is SenderAuth.FAILED


def chain(*sets: tuple[int, str, str]) -> AuthHeaders:
    """Верхній AR (arc=pass) і набори ARC (i, d печатки, authserv-id AAR) з dmarc=pass для
    acme.example, окрім набору 1, де dmarc=fail."""
    headers: list[tuple[str, str]] = [
        (
            "authentication-results",
            "mx.google.com; arc=pass (i=9); dmarc=fail header.from=acme.example",
        )
    ]
    for number, seal_domain, authserv in sets:
        verdict = "fail" if number == 1 else "pass"
        headers.append(
            ("arc-seal", f"i={number}; a=rsa-sha256; d={seal_domain}; cv=pass")
        )
        headers.append(
            (
                "arc-authentication-results",
                f"i={number}; {authserv}; dmarc={verdict} header.from=acme.example",
            )
        )
    return tuple(headers)


def test_lowest_cloudflare_sealed_set_decides() -> None:
    cloudflare = ("cloudflare-email.net", "mx.cloudflare.net")
    google = ("google.com", "mx.google.com")
    headers = chain((3, *cloudflare), (2, *google), (1, *cloudflare))

    assert sender_auth(headers, "hr@acme.example") is SenderAuth.FAILED
    # Без набору i=1 найнижчий запечатаний Cloudflare — i=3 (pass).
    assert sender_auth(chain((3, *cloudflare), (2, *google)), "hr@acme.example") is (
        SenderAuth.VERIFIED
    )


def test_cloudflare_authserv_in_a_set_sealed_by_google_is_ignored() -> None:
    headers = chain((1, "google.com", "mx.cloudflare.net"))

    # Печатка не Cloudflare → набір ігнорується → прямий dmarc=fail зверху.
    assert sender_auth(headers, "hr@acme.example") is SenderAuth.FAILED


def test_cloudflare_set_without_dmarc_is_unknown() -> None:
    headers = (
        (
            "authentication-results",
            "mx.google.com; arc=pass (i=3 dmarc=pass fromdomain=acme.example)",
        ),
        ("arc-seal", "i=2; a=rsa-sha256; d=cloudflare-email.net; cv=pass"),
        ("arc-authentication-results", "i=2; mx.cloudflare.net; spf=pass"),
    )

    assert sender_auth(headers, "hr@acme.example") is SenderAuth.UNKNOWN


def test_gmail_summary_without_a_domain_is_unknown() -> None:
    headers = top("mx.google.com; arc=pass (i=1 dmarc=pass)")

    assert sender_auth(headers, "hr@acme.example") is SenderAuth.UNKNOWN


def test_nested_comment_cannot_inject_a_verdict() -> None:
    value = (
        "mx.google.com; spf=pass (a (nested; dmarc=pass header.from=acme.example) b) "
        "smtp.mailfrom=x; dmarc=fail header.from=acme.example"
    )

    assert sender_auth(top(value), "hr@acme.example") is SenderAuth.FAILED


def test_arc_set_with_nothing_but_its_number_is_ignored() -> None:
    headers = (
        ("authentication-results", "mx.google.com; arc=pass (i=3)"),
        ("arc-seal", "i=2; a=rsa-sha256; d=cloudflare-email.net; cv=pass"),
        ("arc-authentication-results", "i=2"),
    )

    assert sender_auth(headers, "hr@acme.example") is SenderAuth.UNKNOWN
