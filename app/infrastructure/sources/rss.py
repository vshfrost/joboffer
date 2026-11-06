"""Спільне для RSS-стрічок: безпечний розбір XML і перетворення елемента в вакансію. XML з
мережі — недовірені дані: розбір через defusedxml (без DTD, сутностей і зовнішніх ресурсів),
тож «billion laughs» і XXE відхиляються, а не виконуються."""

import html
import re

# Лише типи й виняток: сам розбір — defusedxml.
from xml.etree.ElementTree import Element, ParseError

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import fromstring

from domain.shared.text import html_to_text
from domain.sources.failure import FailureReason, SourceError
from domain.sources.filtering import infer_mode
from domain.sources.posting import Posting, sanitize

BASE_URLS = {
    "dou": "https://jobs.dou.ua/vacancies/feeds/",
    "djinni": "https://djinni.co/jobs/rss/",
}
# «Посада в Компанія, місто, віддалено» (DOU), «Посада у Компанія» (Djinni), «Role at Company»;
# після «at» / «@» компанія пишеться з великої («… at heart» — не компанія).
COMPANY_SEPARATOR = re.compile(
    r"^(?P<position>.+) (?:(?:в|у) (?P<local>\S.*)|(?:at|@) (?P<foreign>[A-ZА-ЯІЇЄҐ0-9].*))$"
)


def feed_items(body: bytes) -> list[Element]:
    """Елементи `<item>` стрічки RSS 2.0. Не XML, небезпечний XML (DTD, сутності) чи не RSS →
    `SourceError(INVALID)`."""
    try:
        root: Element = fromstring(body, forbid_dtd=True)
    except (ParseError, DefusedXmlException, ValueError) as exc:
        raise SourceError(FailureReason.INVALID) from exc
    channel = root.find("channel")
    if root.tag != "rss" or channel is None:
        raise SourceError(FailureReason.INVALID)
    return channel.findall("item")


def field(item: Element, name: str) -> str:
    return item.findtext(name) or ""


def split_title(title: str) -> tuple[str, str, list[str]]:
    """«Senior Python Engineer в Acme, Київ, віддалено» → (посада, компанія, решта через
    кому). Без компанії в назві — (назва, "", [])."""
    # У назвах DOU трапляється подвійне екранування («до&nbsp;$1500»).
    title = " ".join(html.unescape(title).split())
    match = COMPANY_SEPARATOR.fullmatch(title)
    if match is None:
        return title, "", []
    company, *places = (
        part.strip() for part in (match["local"] or match["foreign"]).split(",")
    )
    return match["position"].strip(), company, places


def rss_posting(
    item: Element,
    *,
    title: str,
    company: str,
    places: list[str],
    countries: tuple[str, ...] = (),
) -> Posting | None:
    """Вакансія зі стрічки: опис — HTML → текст, URL без трекінгу. Структурованої локації нема,
    тож формат береться зі слів у назві й тексті, а місто й країну профіль шукає в тексті."""
    text = html_to_text(field(item, "description"))
    return sanitize(
        Posting(
            title=title,
            url=field(item, "link").strip(),
            text=text,
            company=company or None,
            locations=tuple(places),
            countries=countries,
            work_mode=infer_mode([*places, title, text]),
            locations_in_text=True,
        )
    )


def feed_postings(body: bytes, *, countries: tuple[str, ...] = ()) -> list[Posting]:
    """Вакансії стрічки; без назви чи придатного посилання — пропущені."""
    postings = []
    for item in feed_items(body):
        position, company, places = split_title(field(item, "title"))
        posting = rss_posting(
            item, title=position, company=company, places=places, countries=countries
        )
        if posting is not None:
            postings.append(posting)
    return postings
