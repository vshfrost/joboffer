"""RSS-стрічки DOU і Djinni: розбір назви, форми стрічки, ворожий і зламаний XML."""

import httpx2
import pytest
from anyio.from_thread import BlockingPortal

from domain.sources.failure import FailureReason, SourceError
from domain.sources.kinds import FeedSource, SourceKind
from domain.sources.target import SourceTarget
from infrastructure.sources.rss import split_title
from tests.support.sources_net import Scripted, serve_xml

DOU = SourceTarget(FeedSource.DOU, "category=Python&remote")
DJINNI = SourceTarget(FeedSource.DJINNI, "primary_keyword=Python")
FEEDS: list[tuple[SourceKind, SourceTarget]] = [
    (FeedSource.DOU, DOU),
    (FeedSource.DJINNI, DJINNI),
]


def feed(*items: str) -> str:
    return (
        f'<rss version="2.0"><channel><title>t</title>{"".join(items)}</channel></rss>'
    )


def item(
    title: str, link: str = "https://x.example.com/1", text: str = "<p>Hi</p>"
) -> str:
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (
        f"<item><title>{title}</title><link>{link}</link>"
        f"<description>{escaped}</description></item>"
    )


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        (
            "Senior Python Engineer в Acme, Київ, віддалено",
            ("Senior Python Engineer", "Acme", ["Київ", "віддалено"]),
        ),
        (
            "Python Developer в Partner Dev, до&nbsp;$1500, віддалено",
            ("Python Developer", "Partner Dev", ["до $1500", "віддалено"]),
        ),
        (
            "Middle PHP Developer у Brightloop",
            ("Middle PHP Developer", "Brightloop", []),
        ),
        ("Backend Engineer at Scale AI", ("Backend Engineer", "Scale AI", [])),
        ("Backend Engineer @ Acme", ("Backend Engineer", "Acme", [])),
        # «at» без великої літери — не компанія.
        ("Engineer at heart", ("Engineer at heart", "", [])),
        ("Python Developer", ("Python Developer", "", [])),
        ("  Spaced \n title ", ("Spaced title", "", [])),
        # Останній роздільник: посада може містити «в».
        ("Інженер в тестуванні в Acme", ("Інженер в тестуванні", "Acme", [])),
    ],
)
def test_split_title(title: str, expected: tuple[str, str, list[str]]) -> None:
    assert split_title(title) == expected


@pytest.mark.parametrize(("kind", "target"), FEEDS)
def test_items_without_title_or_usable_link_are_dropped(
    portal: BlockingPortal, kind: SourceKind, target: SourceTarget
) -> None:
    xml = feed(
        item(
            "Python Developer в Acme, віддалено",
            "https://x.example.com/a?utm_source=rss",
        ),
        item("", "https://x.example.com/b"),
        item("No link", ""),
        item("Bad link", "ftp://x.example.com/c"),
        "<item/>",
    )

    (posting,) = portal.call(serve_xml(xml).source(kind).fetch, target)

    assert posting.url == "https://x.example.com/a"


@pytest.mark.parametrize(("kind", "target"), FEEDS)
def test_empty_feed_is_not_an_error(
    portal: BlockingPortal, kind: SourceKind, target: SourceTarget
) -> None:
    assert portal.call(serve_xml(feed()).source(kind).fetch, target) == []


BILLION_LAUGHS = """<?xml version="1.0"?>
<!DOCTYPE lolz [
 <!ENTITY lol "lol">
 <!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
 <!ENTITY lol2 "&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;&lol1;">
 <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
]>
<rss version="2.0"><channel><item><title>&lol3;</title><link>https://x.example.com/1</link></item></channel></rss>"""
EXTERNAL_ENTITY = """<?xml version="1.0"?>
<!DOCTYPE rss [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<rss version="2.0"><channel><item><title>&xxe;</title><link>https://x.example.com/1</link></item></channel></rss>"""
PLAIN_DTD = """<?xml version="1.0"?>
<!DOCTYPE rss>
<rss version="2.0"><channel><item><title>A</title><link>https://x.example.com/1</link></item></channel></rss>"""


@pytest.mark.parametrize(
    "xml",
    [
        pytest.param(BILLION_LAUGHS, id="entity-expansion"),
        pytest.param(EXTERNAL_ENTITY, id="external-entity"),
        pytest.param(PLAIN_DTD, id="any-dtd"),
        pytest.param("<rss><channel><item>", id="truncated"),
        pytest.param("not xml at all", id="garbage"),
        pytest.param("", id="empty"),
        pytest.param(b"\xff\xfe<rss/>", id="bad-encoding"),
        pytest.param("<html><body>Blocked</body></html>", id="not-rss"),
        pytest.param('<rss version="2.0"></rss>', id="no-channel"),
        pytest.param('<feed xmlns="http://www.w3.org/2005/Atom"/>', id="atom"),
    ],
)
def test_hostile_or_non_rss_xml_is_invalid(
    portal: BlockingPortal, xml: str | bytes
) -> None:
    for kind, target in FEEDS:
        with pytest.raises(SourceError) as error:
            portal.call(serve_xml(xml).source(kind).fetch, target)

        assert error.value.reason is FailureReason.INVALID


@pytest.mark.parametrize(("kind", "target"), FEEDS)
@pytest.mark.parametrize(
    ("status", "reason", "requests"),
    [
        (500, FailureReason.UNAVAILABLE, 2),
        (429, FailureReason.RATE_LIMITED, 2),
        (404, FailureReason.NOT_FOUND, 1),
        (403, FailureReason.REJECTED, 1),
    ],
)
def test_feed_http_errors_become_failure_codes(
    portal: BlockingPortal,
    kind: SourceKind,
    target: SourceTarget,
    status: int,
    reason: FailureReason,
    requests: int,
) -> None:
    served = Scripted(httpx2.Response(status))

    with pytest.raises(SourceError) as error:
        portal.call(served.source(kind).fetch, target)

    assert error.value.reason is reason
    assert len(served.requests) == requests
