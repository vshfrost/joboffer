"""Кроки для features/mail_*.feature і features/replies_*.feature: use cases пошти (синк, «Вхідні»,
налаштування) і відповідей на подачі (зіставлення, розбір, список, черги для вебу) + in-memory адаптери.

Скринька застосунку — `FakeMailbox`, сховище — `InMemoryMailUnitOfWork`; час стоїть на `NOW`, лист
«надходить» у минулому (`отриманий N год. тому`). Два користувачі: «Богдан» і «Наталя». Лист у сценарії має
id скриньки («m1»): тема за замовчуванням «Re: m1», за темою його і впізнають у «Вхідних».
Умови листа йдуть через кому: `у скриньці є лист "m1" на мою адресу, від "hr@acme.example", отриманий 2 дн. тому`.
Подачі для відповідей: `я подався на вакансію "Backend" у компанію "Acme", з доменами "acme.example"`; вакансію
далі називають за посадою (у межах користувача посади різні).
"""

import functools
import re
from collections.abc import Callable
from dataclasses import fields
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from anyio.from_thread import BlockingPortal
from pytest_bdd import given as bdd_given
from pytest_bdd import parsers, scenarios
from pytest_bdd import then as bdd_then
from pytest_bdd import when as bdd_when

from application.applications.use_cases import ApplicationUseCases
from application.contracts.actor import Actor, Channel, Scope
from application.contracts.applications import ApplicationInput
from application.contracts.jobs import AddedJob, AddOutcome, JobInput, JobSearchInput
from application.contracts.mail import MailDetailData, MailInboxData, MailSettingsData
from application.contracts.replies import ReviewedReplyData, ReviewInput
from application.jobs.use_cases import JobUseCases
from application.mail.inbox import MailUseCases
from application.mail.replies import ReplyUseCases
from application.mail.sync import MailSyncUseCases, SyncReport
from domain.identity.ids import UserId
from domain.mail.board import ReplyBoard, ReplyQuery
from domain.mail.forwarded import ForwardedMail
from domain.mail.inbox import MailListItem, MailQuery, ManualSyncLimit
from domain.mail.mail import (
    MAX_DROPPED_SUBJECT,
    DroppedRecord,
    IncomingMail,
    MailboxError,
)
from domain.mail.replies import Reply
from domain.profile.contacts import Contacts
from domain.profile.profile import Profile
from domain.shared.errors import DomainError, InvalidFields
from domain.shared.local_time import local_time
from tests.support import linkedin_alerts
from tests.support.applications import InMemoryApplicationUnitOfWork
from tests.support.clock import FakeClock
from tests.support.ids import SequentialIds
from tests.support.jobs import InMemoryJobUnitOfWork
from tests.support.mail import (
    FakeMailbox,
    InMemoryMailUnitOfWork,
    MailStore,
    auth_headers,
    user,
)

scenarios(
    "features/mail_sync.feature",
    "features/mail_inbox.feature",
    "features/mail_settings.feature",
    "features/mail_users.feature",
    "features/replies_board.feature",
    "features/linkedin_alerts.feature",
    "features/replies_match.feature",
    "features/replies_review.feature",
    "features/replies_users.feature",
)

Step = Callable[..., Any]
MAILBOX = "mailroom@example.com"
NOW = datetime(2026, 10, 14, 12, tzinfo=UTC)
USERS = {"Богдан": user(1), "Наталя": user(2)}
# Відмінок «у кого»: `статус подачі "Backend" у <ім’я> — "applied"`.
GENITIVE = {"Богдана": "Богдан", "Наталі": "Наталя"}
UNITS = {"хв.": "minutes", "год.": "hours", "дн.": "days"}
ADDRESS = re.compile(r"^mailroom\+[a-z2-7]{12}@example\.com$")


def rx(pattern: str) -> Any:
    return parsers.re(pattern)


def succeeded(step: Step) -> Step:
    """Крок-передумова: дія має вдатися, інакше сценарій не про те."""

    @functools.wraps(step)
    def wrapper(*args: Any, **kwargs: Any) -> None:
        step(*args, **kwargs)
        world: World = kwargs["world"]
        assert world.error is None, world.error

    return wrapper


def action(pattern: str) -> Callable[[Step], Step]:
    """Один текст — і «Припустимо я …», і «Якщо я …»: `(?:змінюю|змінив|змінила)`."""

    def decorate(step: Step) -> Step:
        bdd_given(rx(pattern), stacklevel=2)(succeeded(step))
        bdd_when(rx(pattern), stacklevel=2)(step)
        return step

    return decorate


def actor_of(user_id: UserId) -> Actor:
    return Actor(
        user_id=user_id,
        channel=Channel.WEB,
        client_id="web",
        grant_id=None,
        scopes=frozenset(Scope),
        correlation_id="test",
    )


class World:
    def __init__(self, portal: BlockingPortal) -> None:
        self.portal = portal
        self.clock = FakeClock(NOW)
        self.store = MailStore()
        self.box = FakeMailbox()
        self.sync_mail = MailSyncUseCases(
            lambda: InMemoryMailUnitOfWork(self.store), self.clock, SequentialIds()
        )
        self.mail = self.use_cases(MAILBOX)
        # Вакансії й подачі лежать у тому самому сховищі, що й пошта: синк бачить їх у своїй транзакції.
        self.jobs = JobUseCases(
            lambda: InMemoryJobUnitOfWork(self.store.jobs), self.clock, SequentialIds()
        )
        self.applications = ApplicationUseCases(
            lambda: InMemoryApplicationUnitOfWork(self.store.jobs), self.clock
        )
        self.replies = ReplyUseCases(
            lambda: InMemoryMailUnitOfWork(self.store), self.clock
        )
        self.job_numbers: dict[tuple[str, str], int] = {}
        self.me = "Богдан"
        self.error: Exception | None = None
        self.report: SyncReport | None = None
        self.items: list[MailListItem] | None = None
        self.total: int | None = None
        self.detail: MailDetailData | None = None
        self.settings: MailSettingsData | None = None
        self.address: str | None = None
        self.listed: list[Reply] | None = None
        self.board: ReplyBoard | None = None
        self.reviewed: ReviewedReplyData | None = None
        self.overview: MailInboxData | None = None
        self.added: AddedJob | None = None
        # Перша адреса користувача до ротації й теми листів за id скриньки.
        self.previous: dict[str, str] = {}
        self.subjects: dict[str, str] = {}
        self.cursor_before: str | None = None
        self.requested_at: list[datetime] = []
        self.seen: list[str] = []

    def use_cases(self, mailbox: str) -> MailUseCases:
        return MailUseCases(
            lambda: InMemoryMailUnitOfWork(self.store), self.clock, mailbox
        )

    @property
    def actor(self) -> Actor:
        return actor_of(USERS[self.me])

    def reset_outcome(self) -> None:
        self.error = None
        self.report = None
        self.items = None
        self.total = None
        self.detail = None
        self.settings = None
        self.address = None
        self.listed = None
        self.board = None
        self.reviewed = None
        self.overview = None
        self.added = None

    def attempt(self, call: Callable[[], Any]) -> Any:
        """Виконує дію; помилка домену чи скриньки запамʼятовується для кроків «Тоді»."""
        self.reset_outcome()
        try:
            return call()
        except (DomainError, MailboxError) as error:
            self.error = error
            return None

    def address_of(self, name: str) -> str:
        return self.portal.call(self.mail.settings, actor_of(USERS[name])).address

    def deliver(self, gmail_id: str, to: tuple[str, ...], **fields_: Any) -> None:
        sender = fields_.get("sender", "talent@acme.example")
        subject = fields_.get("subject", f"Re: {gmail_id}")
        self.subjects[gmail_id] = subject
        self.box.deliver(
            IncomingMail(
                id=gmail_id,
                received_at=NOW - fields_.get("age", timedelta(days=1)),
                message_id=f"<{gmail_id}@mail>",
                in_reply_to=fields_.get("in_reply_to", ""),
                from_address=sender,
                from_name=fields_.get("name", ""),
                auth_headers=auth_headers(sender, fields_.get("dmarc", "pass")),
                delivered_to=(*to, "taras@example.com"),
                subject=subject,
                text=mail_text(fields_),
            )
        )

    def sync(self) -> None:
        self.report = None
        self.error = None
        try:
            self.report = self.portal.call(self.sync_mail.sync_mail, self.box, MAILBOX)
        except MailboxError as error:
            self.error = error

    def list_mail(self, query: MailQuery, actor: Actor | None = None) -> None:
        listed = self.attempt(
            lambda: self.portal.call(self.mail.list_mail, actor or self.actor, query)
        )
        if listed is not None:
            self.items, self.total = list(listed.items), listed.page.total

    def all_items(self, name: str) -> list[MailListItem]:
        """Усі рядки «Вхідних» користувача: сторінки по 100, поки не скінчаться."""
        found: list[MailListItem] = []
        number = 1
        while True:
            query = MailQuery.parse(page=number, per_page=100)
            listed = self.portal.call(self.mail.list_mail, actor_of(USERS[name]), query)
            found += listed.items
            if not listed.page.has_older:
                return found
            number += 1

    def in_inbox(self, name: str, gmail_id: str) -> list[MailListItem]:
        subject = self.subjects[gmail_id]
        return [
            i
            for i in self.all_items(name)
            if i.subject == (subject[:MAX_DROPPED_SUBJECT] if i.dropped else subject)
        ]

    def dropped_record(self, gmail_id: str) -> DroppedRecord:
        return self.store.dropped[gmail_id][1]

    def job_number(self, name: str, title: str) -> int:
        return self.job_numbers[(name, title)]

    def status_of(self, name: str, title: str) -> str:
        found = self.portal.call(
            self.applications.get_application,
            actor_of(USERS[name]),
            self.job_number(name, title),
        )
        assert found is not None, f"подачі на «{title}» нема"
        return found.status.value

    def all_replies(self, name: str) -> list[Reply]:
        """Усі відповіді користувача: нерозібрані й розібрані."""
        actor = actor_of(USERS[name])
        return [
            reply
            for reviewed in (False, True)
            for reply in self.portal.call(
                functools.partial(
                    self.replies.list_replies, actor, reviewed=reviewed, limit=50
                )
            )
        ]

    def reply_of(self, name: str, gmail_id: str) -> Reply | None:
        subject = self.subjects[gmail_id]
        found = [r for r in self.all_replies(name) if r.mail.subject == subject]
        assert len(found) <= 1, found
        return found[0] if found else None


@pytest.fixture
def world(portal: BlockingPortal) -> World:
    return World(portal)


def code_of(world: World) -> str:
    assert world.error is not None, "помилки не було"
    return str(getattr(world.error, "code", "mailbox_error"))


# --- хто я, адреси ------------------------------------------------------------------------------


@bdd_given(rx(r'^я — користувач "(?P<name>[^"]*)"$'))
@bdd_given(rx(r'^я стаю користувачем "(?P<name>[^"]*)"$'))
@bdd_when(rx(r'^я стаю користувачем "(?P<name>[^"]*)"$'))
def become_user(world: World, name: str) -> None:
    world.me = name
    world.reset_outcome()


@action(r"^я (?:змінюю|змінив|змінила) особисту адресу пошти$")
def rotate_address(world: World) -> None:
    before = world.address_of(world.me)
    rotated = world.attempt(
        lambda: world.portal.call(world.mail.rotate_address, world.actor)
    )
    if rotated is not None:
        world.previous[world.me] = before
        world.address = rotated


# --- листи у скриньці ---------------------------------------------------------------------------

CLAUSES = (
    (r'^від "(?P<v>[^"]*)"$', "sender"),
    (r'^з темою "(?P<v>[^"]*)"$', "subject"),
    (r'^з текстом "(?P<v>[^"]*)"$', "text"),
    (r'^з цитатою "(?P<v>[^"]*)"$', "cite"),
    (r'^з іменем відправника "(?P<v>[^"]*)"$', "name"),
)
DIGESTS = {
    "madrid": linkedin_alerts.MADRID,
    "barcelona": linkedin_alerts.BARCELONA,
    "spain": linkedin_alerts.SPAIN,
}
DIGEST = re.compile(r'^з дайджестом "(?P<name>[^"]*)"$')
VACANCIES = re.compile(
    r'^з (?:вакансіями|вакансією) "(?P<jobs>[^"]*)"'
    r"(?: і блоком (?P<broken>із двома посиланнями|лише з посиланням))?$"
)
AGE = re.compile(r"^отриманий (?P<n>\d+) (?P<unit>хв\.|год\.|дн\.) тому$")
LONG_SUBJECT = re.compile(r"^з темою із (?P<n>\d+) символів$")


def alert_text(clause: str) -> str | None:
    """Текст листа-алерту LinkedIn за умовою листа; None — умова не про алерт."""
    if digest := DIGEST.match(clause):
        return DIGESTS[digest["name"]]
    if clause == "з дайджестом без вакансій":
        return "Привіт! Тут нема жодної вакансії."
    if listed := VACANCIES.match(clause):
        return digest_text(listed["jobs"].split("; "), listed["broken"])
    return None


def digest_text(jobs: list[str], broken: str | None) -> str:
    """Лист-алерт LinkedIn: блоки `id|посада|компанія|локація` між рядками з дефісів, за потреби —
    зламаний блок наприкінці. `{x400}` у полі — 400 символів «x»."""
    link = (
        "Переглянути вакансію: https://www.linkedin.com/comm/jobs/view/{}?trackingId=x"
    )
    blocks: list[str] = []
    for item in jobs:
        number, title, company, location = (
            re.sub(r"\{x(\d+)\}", lambda m: "x" * int(m[1]), part)
            for part in item.split("|")
        )
        blocks.append(
            f"{title}\n{company}\n{location}\nПодати заявку\n{link.format(number)}"
        )
    if broken == "із двома посиланнями":
        blocks.append(
            f"Title\nCompany\nCity\n{link.format(4400000008)}\n{link.format(4400000009)}"
        )
    elif broken:
        blocks.append(link.format(4400000007))
    return "Нові вакансії:\n\n" + "".join(f"{b}\n\n{'-' * 40}\n\n" for b in blocks)


def recipient(world: World, to: str) -> tuple[str, ...]:
    other = re.fullmatch(r'на адресу користувача "(?P<name>[^"]*)"', to)
    if other:
        return (world.address_of(other.group("name")),)
    if to == "на мою адресу":
        return (world.address_of(world.me),)
    if to == "на мою колишню адресу":
        return (world.previous[world.me],)
    if to == "на адресу з невідомим tag":
        return ("mailroom+zzzzzzzzzzzz@example.com",)
    return ()


def mail_text(fields_: dict[str, Any]) -> str:
    """Текст листа: власний (або «untrusted body»), блок пересланого листа Gmail згори, цитата знизу."""
    forward = fields_.get("forward")
    text = fields_.get("text", "Hola" if forward else "untrusted body")
    if forward:
        sender, subject = forward
        text = (
            "---------- Forwarded message ---------\n"
            f"From: Ana Recruiter <{sender}>\n"
            "Date: Mon, Oct 19, 2026 at 10:15 AM\n"
            f"Subject: {subject}\n"
            "To: Owner <owner@owner.example>\n\n"
            f"{text}"
        )
    if "cite" in fields_:
        text = f"{text}\n> {fields_['cite']}"
    return str(text)


FORWARD = re.compile(
    r'^з пересланим листом від "(?P<sender>[^"]*)" з темою "(?P<subject>[^"]*)"$'
)
THREAD = re.compile(r'^у відповідь на лист "(?P<gmail_id>[^"]*)"$')


def mail_fields(gmail_id: str, conditions: str) -> dict[str, Any]:
    found: dict[str, Any] = {}
    for clause in filter(None, conditions.split(", ")):
        if clause in {"з DMARC fail", "з DMARC none"}:
            found["dmarc"] = clause.rpartition(" ")[2]
        elif forwarded := FORWARD.match(clause):
            found["forward"] = (forwarded["sender"], forwarded["subject"])
        elif threaded := THREAD.match(clause):
            found["in_reply_to"] = f"<{threaded['gmail_id']}@mail>"
        elif (alert := alert_text(clause)) is not None:
            found["text"] = alert
        elif aged := AGE.match(clause):
            found["age"] = timedelta(**{UNITS[aged["unit"]]: int(aged["n"])})
        elif long := LONG_SUBJECT.match(clause):
            found["subject"] = f"{gmail_id} " + "я" * (
                int(long["n"]) - len(gmail_id) - 1
            )
        else:
            for pattern, name in CLAUSES:
                matched = re.match(pattern, clause)
                if matched:
                    found[name] = matched["v"]
                    break
            else:
                raise AssertionError(f"невідома умова листа: {clause}")
    return found


@bdd_given(
    rx(
        r'^у скриньці є лист "(?P<gmail_id>[^"]*)" (?P<to>на мою адресу|на мою колишню адресу|'
        r'на адресу користувача "[^"]*"|на адресу з невідомим tag|без особистої адреси)'
        r"(?:, (?P<conditions>.+))?$"
    )
)
def mailbox_has_mail(
    world: World, gmail_id: str, to: str, conditions: str | None
) -> None:
    world.deliver(
        gmail_id, recipient(world, to), **mail_fields(gmail_id, conditions or "")
    )


@bdd_given(rx(r"^у скриньці є (?P<count>\d+) листів на мою адресу$"))
def mailbox_has_many(world: World, count: str) -> None:
    to = recipient(world, "на мою адресу")
    for n in range(1, int(count) + 1):
        world.deliver(f"bulk{n}", to, age=timedelta(hours=5) - timedelta(minutes=n))


@bdd_given(rx(r'^скринька недоступна з помилкою "(?P<message>[^"]*)"$'))
def mailbox_fails(world: World, message: str) -> None:
    state = world.store.sync.get(MAILBOX)
    world.cursor_before = None if state is None else state.history_id
    world.box.error = MailboxError(message)


@bdd_given("скринька знову працює")
def mailbox_works(world: World) -> None:
    world.box.error = None


@bdd_given("курсор скриньки протух")
def cursor_expired(world: World) -> None:
    world.box.expired_before = world.box.cursor + 1


@bdd_given("синк пошти уже виконується в іншому процесі")
def sync_busy(world: World) -> None:
    world.store.sync_busy = True


# --- синк ---------------------------------------------------------------------------------------


@action(r"^відбувається (?:синк|ще один синк) пошти$")
def run_sync(world: World) -> None:
    world.sync()


@bdd_given("синк пошти зазнає збою")
def run_failing_sync(world: World) -> None:
    world.sync()
    assert isinstance(world.error, MailboxError), "синк мав упасти"


@bdd_then(rx(r"^синк зберіг (?P<count>\d+) лист\w*$"))
def sync_stored(world: World, count: str) -> None:
    assert world.error is None, world.error
    assert world.report is not None
    assert world.report.stored == int(count)


@bdd_then(rx(r"^синк пропустив (?P<count>\d+) уже відом\w+ лист\w*$"))
def sync_known(world: World, count: str) -> None:
    assert world.report is not None
    assert world.report.known == int(count)


@bdd_then(
    rx(r'^синк відкинув лист "(?P<gmail_id>[^"]*)" з причиною "(?P<reason>[^"]*)"$')
)
def sync_dropped(world: World, gmail_id: str, reason: str) -> None:
    assert world.report is not None
    found = [(d.gmail_id, d.reason.value) for d in world.report.dropped]
    assert (gmail_id, reason) in found, found


@bdd_then(rx(r"^синк відкинув (?P<count>\d+) лист\w*$"))
def sync_dropped_count(world: World, count: str) -> None:
    assert world.report is not None
    assert len(world.report.dropped) == int(count)


@bdd_then("синк нічого не зберіг і не відкинув")
def sync_nothing(world: World) -> None:
    assert world.error is None, world.error
    assert world.report is not None
    assert (world.report.stored, world.report.dropped) == (0, [])


@bdd_then("синк нічого не робить, бо вже йде в іншому процесі")
def sync_locked(world: World) -> None:
    assert world.report is not None
    assert world.report.locked
    assert (world.report.stored, world.report.dropped) == (0, [])
    assert world.box.fetched == []


@bdd_then(rx(r"^синк перечитав листи за (?P<days>\d+) днів$"))
def sync_resynced(world: World, days: str) -> None:
    assert world.report is not None
    assert world.report.resynced
    assert world.box.since_calls[-1] == NOW - timedelta(days=int(days))


@bdd_then(rx(r'^синк завершується помилкою скриньки "(?P<message>[^"]*)"$'))
def sync_failed(world: World, message: str) -> None:
    assert isinstance(world.error, MailboxError), world.error
    assert str(world.error) == message


@bdd_then("курсор синку лишився тим, що був до збою")
def cursor_kept(world: World) -> None:
    state = world.store.sync.get(MAILBOX)
    assert state is not None
    assert state.history_id == world.cursor_before


@bdd_then(rx(r'^у налаштуваннях видно помилку синку "(?P<message>[^"]*)"$'))
def settings_error(world: World, message: str) -> None:
    data = world.portal.call(world.mail.settings, world.actor)
    assert data.sync_failed
    assert data.sync_error == message


@bdd_then("у налаштуваннях помилки синку нема")
def settings_no_error(world: World) -> None:
    data = world.portal.call(world.mail.settings, world.actor)
    assert not data.sync_failed
    assert data.sync_error == ""


# --- що у «Вхідних» -----------------------------------------------------------------------------


@bdd_then(rx(r'^у моїх Вхідних є збережений лист "(?P<gmail_id>[^"]*)"$'))
def inbox_has_stored(world: World, gmail_id: str) -> None:
    found = world.in_inbox(world.me, gmail_id)
    assert [i.dropped for i in found] == [False], found


@bdd_then(
    rx(
        r'^у моїх Вхідних є відкинутий лист "(?P<gmail_id>[^"]*)" з причиною "(?P<reason>[^"]*)"$'
    )
)
def inbox_has_dropped(world: World, gmail_id: str, reason: str) -> None:
    found = world.in_inbox(world.me, gmail_id)
    assert [(i.dropped, i.reason and i.reason.value) for i in found] == [
        (True, reason)
    ], found


@bdd_then(rx(r'^у моїх Вхідних нема листа "(?P<gmail_id>[^"]*)"$'))
def inbox_lacks(world: World, gmail_id: str) -> None:
    assert world.in_inbox(world.me, gmail_id) == []


@bdd_then(rx(r'^лист "(?P<gmail_id>[^"]*)" не видно нікому у Вхідних$'))
def nobody_sees(world: World, gmail_id: str) -> None:
    for name in USERS:
        assert world.in_inbox(name, gmail_id) == [], name


@bdd_then(rx(r"^у моїх Вхідних (?P<count>\d+) лист\w*$"))
def inbox_count(world: World, count: str) -> None:
    assert len(world.all_items(world.me)) == int(count)


@bdd_then(
    rx(
        r'^лист "(?P<gmail_id>[^"]*)" у моїх Вхідних позначено як "(?P<category>[^"]*)"$'
    )
)
def inbox_category(world: World, gmail_id: str, category: str) -> None:
    (found,) = world.in_inbox(world.me, gmail_id)
    assert found.category is not None
    assert found.category.value == category


@bdd_then(
    rx(
        r'^про відкинутий лист "(?P<gmail_id>[^"]*)" збережено лише адресу відправника '
        r'"(?P<sender>[^"]*)" і тему довжиною (?P<length>\d+) символів$'
    )
)
def dropped_audit(world: World, gmail_id: str, sender: str, length: str) -> None:
    record = world.dropped_record(gmail_id)
    assert record.from_address == sender
    assert len(record.subject) == int(length) == MAX_DROPPED_SUBJECT
    assert record.subject == world.subjects[gmail_id][:MAX_DROPPED_SUBJECT]


@bdd_then(rx(r'^про відкинутий лист "(?P<gmail_id>[^"]*)" тексту не збережено$'))
def dropped_without_text(world: World, gmail_id: str) -> None:
    record = world.dropped_record(gmail_id)
    assert {f.name for f in fields(record)} == {
        "gmail_id",
        "reason",
        "received_at",
        "from_address",
        "subject",
    }
    assert "untrusted body" not in repr(record)


# --- «Вхідні»: пошук, вид, сторінки, читалка ----------------------------------------------------


def gmail_ids(world: World, items: list[MailListItem]) -> list[str]:
    by_subject = {
        (subject[:MAX_DROPPED_SUBJECT]): gmail_id
        for gmail_id, subject in world.subjects.items()
    }
    return [by_subject[item.subject] for item in items]


def shown(text: str) -> list[str]:
    return [] if text.strip() == "" else [part.strip() for part in text.split(";")]


@bdd_given(rx(r"^пошту не налаштовано$"))
def mail_not_configured(world: World) -> None:
    world.mail = world.use_cases("")


@bdd_when(
    rx(
        r"^я переглядаю Вхідні(?: з пошуком \"(?P<text>[^\"]*)\")?(?: виду \"(?P<kind>[^\"]*)\")?"
        r"(?: сторінку (?P<page>\d+))?(?: по (?P<per_page>\d+))?$"
    )
)
def browse_inbox(
    world: World,
    text: str | None,
    kind: str | None,
    page: str | None,
    per_page: str | None,
) -> None:
    def parse() -> MailQuery:
        return MailQuery.parse(
            text=text or "",
            kind=kind or "",
            page=int(page or 1),
            per_page=int(per_page or 20),
        )

    query = world.attempt(parse)
    if query is not None:
        world.list_mail(query)


@bdd_then(rx(r'^у списку за порядком: "(?P<ids>[^"]*)"$'))
def listed_order(world: World, ids: str) -> None:
    assert world.error is None, world.error
    assert world.items is not None, "список не запитували"
    assert gmail_ids(world, world.items) == shown(ids)


@bdd_then(rx(r"^на сторінці (?P<count>\d+) лист\w*, усього (?P<total>\d+)$"))
def page_counts(world: World, count: str, total: str) -> None:
    assert world.error is None, world.error
    assert world.items is not None, "список не запитували"
    assert (len(world.items), world.total) == (int(count), int(total))


def number_of(world: World, gmail_id: str) -> int:
    """Номер листа у «Вхідних» його власника: за ним лист відкривають."""
    owner = world.store.messages[gmail_id][0]
    name = next(name for name, user_id in USERS.items() if user_id == owner)
    (found,) = [i for i in world.in_inbox(name, gmail_id) if not i.dropped]
    return found.id


@bdd_when(rx(r'^я відкриваю лист "(?P<gmail_id>[^"]*)"$'))
def open_mail(world: World, gmail_id: str) -> None:
    number = number_of(world, gmail_id)
    world.detail = world.attempt(
        lambda: world.portal.call(world.mail.get_mail, world.actor, number)
    )


@bdd_then(rx(r'^у деталях код пересилання "(?P<code>\d+)" від "(?P<sender>[^"]*)"$'))
def forwarding_code(world: World, code: str, sender: str) -> None:
    assert world.error is None, world.error
    assert world.detail is not None
    forwarding = world.detail.forwarding
    assert forwarding is not None, "даних пересилання нема"
    assert (forwarding.code, forwarding.requested_by) == (code, sender)
    assert not forwarding.link_only


@bdd_then("у деталях лише посилання, без коду")
def forwarding_link_only(world: World) -> None:
    assert world.detail is not None
    forwarding = world.detail.forwarding
    assert forwarding is not None, "даних пересилання нема"
    assert forwarding.link_only


@bdd_then("у деталях даних пересилання нема")
def no_forwarding(world: World) -> None:
    assert world.error is None, world.error
    assert world.detail is not None
    assert world.detail.forwarding is None


@bdd_then(rx(r'^у деталях текст листа "(?P<text>[^"]*)"$'))
def detail_text(world: World, text: str) -> None:
    assert world.detail is not None
    assert world.detail.text == text


# --- помилки ------------------------------------------------------------------------------------


@bdd_then(rx(r'^отримую помилку "(?P<code>[^"]*)" з текстом "(?P<message>[^"]*)"$'))
def error_message(world: World, code: str, message: str) -> None:
    assert world.error is not None, "помилки не було"
    assert code_of(world) == code
    assert isinstance(world.error, DomainError), world.error
    assert world.error.message == message


@bdd_then(rx(r'^отримую помилку "(?P<code>[^"]*)"$'))
def error_code(world: World, code: str) -> None:
    assert code_of(world) == code


@bdd_then(rx(r'^проблема в полі "(?P<field>[^"]*)": "(?P<message>[^"]*)"$'))
def field_problem(world: World, field: str, message: str) -> None:
    assert isinstance(world.error, InvalidFields), world.error
    problems = {p.field: p.message for p in world.error.problems}
    assert problems == {field: message}


# --- налаштування: адреса, ротація, синк вручну -------------------------------------------------


@action(r"^я (?:відкриваю|відкрив|відкрила) налаштування пошти$")
def open_settings(world: World) -> None:
    world.settings = world.attempt(
        lambda: world.portal.call(world.mail.settings, world.actor)
    )
    if world.settings is not None:
        world.seen.append(world.settings.address)


@bdd_then("моя адреса — це скринька застосунку з особистим tag")
def address_shape(world: World) -> None:
    assert world.settings is not None, world.error
    assert ADDRESS.match(world.settings.address), world.settings.address


@bdd_then("адреса така сама, як минулого разу")
def address_stable(world: World) -> None:
    assert len(world.seen) >= 2
    assert world.seen[-1] == world.seen[-2]


@bdd_then(rx(r'^адреса користувача "(?P<name>[^"]*)" відрізняється від моєї$'))
def addresses_differ(world: World, name: str) -> None:
    assert world.address_of(name) != world.address_of(world.me)


@bdd_then("адреса нова, не та, що була до ротації")
def address_new(world: World) -> None:
    assert world.address is not None, world.error
    assert ADDRESS.match(world.address), world.address
    assert world.address != world.previous[world.me]


@bdd_then("у налаштуваннях моя адреса — нова, а ротацію позначено")
def settings_after_rotation(world: World) -> None:
    data = world.portal.call(world.mail.settings, world.actor)
    assert data.address != world.previous[world.me]
    assert data.rotated_at is not None


@bdd_then("до ротації адреса ротацію не показувала")
def not_rotated(world: World) -> None:
    assert world.settings is not None
    assert world.settings.rotated_at is None


@action(r"^я (?:запитую|запитав|запитала) синк пошти вручну$")
def request_sync(world: World) -> None:
    requested = world.attempt(
        lambda: world.portal.call(world.mail.request_sync, world.actor)
    )
    if requested is not None:
        world.requested_at.append(world.clock.now())


@bdd_given(rx(r"^минає (?P<minutes>\d+) хв\.$"))
@bdd_when(rx(r"^минає (?P<minutes>\d+) хв\.$"))
def time_passes(world: World, minutes: str) -> None:
    world.clock.advance(timedelta(minutes=int(minutes)))


@bdd_then(rx(r"^у налаштуваннях лишилось (?P<count>\d+) синк\w* вручну$"))
def manual_left(world: World, count: str) -> None:
    data = world.portal.call(world.mail.settings, world.actor)
    assert data.manual.remaining == int(count)


@bdd_then(
    rx(r'^запит синку відхилено: час повтору — "(?P<time>\d\d:\d\d)" за Мадридом$')
)
def sync_limit_time(world: World, time: str) -> None:
    assert isinstance(world.error, ManualSyncLimit), world.error
    assert f"{local_time(world.error.next_at):%H:%M}" == time
    assert world.error.next_at == world.requested_at[0] + timedelta(minutes=30)
    assert f"наступний о {time} (Мадрид)" in world.error.message


@bdd_then(rx(r"^(?P<count>\d+) запит\w* синку позначено виконаними$"))
def requests_handled(world: World, count: str) -> None:
    handled = [r for r in world.store.sync_requests if r[2] is not None]
    assert len(handled) == int(count)


@bdd_then(rx(r"^(?P<count>\d+) запит\w* синку чека\w+ на виконання$"))
def requests_pending(world: World, count: str) -> None:
    pending = [r for r in world.store.sync_requests if r[2] is None]
    assert len(pending) == int(count)


# --- кілька користувачів ------------------------------------------------------------------------


@bdd_when(rx(r'^я відкриваю лист "(?P<gmail_id>[^"]*)" користувача "(?P<name>[^"]*)"$'))
def open_foreign_mail(world: World, gmail_id: str, name: str) -> None:
    """Номер чужого листа відомий його власникові; я пробую відкрити саме його."""
    owner = actor_of(USERS[name])
    listed = world.portal.call(world.mail.list_mail, owner, MailQuery.parse())
    (found,) = [i for i in listed.items if i.subject == world.subjects[gmail_id]]
    world.detail = world.attempt(
        lambda: world.portal.call(world.mail.get_mail, world.actor, found.id)
    )


@bdd_then(rx(r"^листа не видно: отримую помилку \"not_found\"$"))
def mail_hidden(world: World) -> None:
    assert world.detail is None
    assert code_of(world) == "not_found"


# --- відповіді на подачі: подачі, профіль ---------------------------------------------------------

APPLIED_CLAUSES = (
    (r'^з доменами "(?P<v>[^"]*)"$', "company_domains"),
    (r'^з адресами "(?P<v>[^"]*)"$', "company_emails"),
    (r'^через ATS "(?P<v>[^"]*)"$', "ats"),
    (r'^у статусі "(?P<v>[^"]*)"$', "status"),
)


def applied_fields(conditions: str) -> dict[str, Any]:
    found: dict[str, Any] = {}
    for clause in filter(None, conditions.split(", ")):
        for pattern, name in APPLIED_CLAUSES:
            matched = re.match(pattern, clause)
            if matched:
                found[name] = matched["v"]
                break
        else:
            raise AssertionError(f"невідома умова подачі: {clause}")
    return found


@bdd_given(
    rx(
        r'^я (?:подався|подалась) на вакансію "(?P<title>[^"]*)" у компанію "(?P<company>[^"]*)"'
        r"(?:, (?P<conditions>.+))?$"
    )
)
def applied_to(world: World, title: str, company: str, conditions: str | None) -> None:
    fields_ = applied_fields(conditions or "")
    added = world.portal.call(
        world.jobs.add_job,
        world.actor,
        JobInput(text=f"{title} at {company}", title=title, company=company),
    )
    world.job_numbers[(world.me, title)] = added.job_number
    world.portal.call(
        world.applications.mark_applied,
        world.actor,
        added.job_number,
        ApplicationInput(
            channel="email",
            ats=fields_.get("ats", ""),
            company_domains=fields_.get("company_domains", "").split(";"),
            company_emails=fields_.get("company_emails", "").split(";"),
        ),
    )
    if "status" in fields_:
        world.portal.call(
            world.applications.set_application_status,
            world.actor,
            added.job_number,
            fields_["status"],
        )


@bdd_given(rx(r'^мій email у профілі — "(?P<email>[^"]*)"$'))
def profile_email(world: World, email: str) -> None:
    world.store.profiles[USERS[world.me]] = Profile(contacts=Contacts(email=email))


@bdd_given("записи зіставлення листів видалено")
def replies_wiped(world: World) -> None:
    world.store.replies.clear()


# --- відповіді на подачі: зіставлення -----------------------------------------------------------


@bdd_then(
    rx(
        r"^синк зіставив (?P<matched>\d+) лист\w*, не зіставив (?P<unmatched>\d+), "
        r"подач у replied — (?P<replied>\d+)$"
    )
)
def sync_matched(world: World, matched: str, unmatched: str, replied: str) -> None:
    assert world.error is None, world.error
    assert world.report is not None
    found = world.report.replies
    assert (found.matched, found.unmatched, found.replied) == (
        int(matched),
        int(unmatched),
        int(replied),
    )


@bdd_then(
    rx(
        r'^лист "(?P<gmail_id>[^"]*)" зіставлено з вакансією "(?P<title>[^"]*)" '
        r'з впевненістю "(?P<confidence>[^"]*)" за ознакою "(?P<by>[^"]*)"$'
    )
)
def reply_matched(
    world: World, gmail_id: str, title: str, confidence: str, by: str
) -> None:
    reply = world.reply_of(world.me, gmail_id)
    assert reply is not None, "запису зіставлення нема"
    assert reply.job is not None, "вакансію не знайдено"
    assert reply.job.job_number == world.job_number(world.me, title)
    assert reply.confidence is not None
    assert reply.matched_by is not None
    assert (reply.confidence.value, reply.matched_by.value) == (confidence, by)


@bdd_then(rx(r'^лист "(?P<gmail_id>[^"]*)" не зіставлено з жодною вакансією$'))
def reply_unmatched(world: World, gmail_id: str) -> None:
    reply = world.reply_of(world.me, gmail_id)
    assert reply is not None, "запису зіставлення нема"
    assert (reply.job, reply.confidence, reply.matched_by) == (None, None, None)


@bdd_then(rx(r'^для листа "(?P<gmail_id>[^"]*)" підказано тип "(?P<kind>[^"]*)"$'))
def reply_suggested(world: World, gmail_id: str, kind: str) -> None:
    reply = world.reply_of(world.me, gmail_id)
    assert reply is not None, "запису зіставлення нема"
    assert reply.suggested_type.value == kind


@bdd_then(rx(r'^у моїх відповідях є лист "(?P<gmail_id>[^"]*)"$'))
def replies_have(world: World, gmail_id: str) -> None:
    assert world.reply_of(world.me, gmail_id) is not None


@bdd_then(rx(r'^у моїх відповідях нема листа "(?P<gmail_id>[^"]*)"$'))
def replies_lack(world: World, gmail_id: str) -> None:
    assert world.reply_of(world.me, gmail_id) is None


@bdd_then(rx(r"^у моїх відповідях рівно (?P<count>\d+) лист\w*$"))
def replies_count(world: World, count: str) -> None:
    assert len(world.all_replies(world.me)) == int(count)


@bdd_then(
    rx(
        r'^статус подачі "(?P<title>[^"]*)"(?: у (?P<owner>Богдана|Наталі))? — "(?P<status>[^"]*)"$'
    )
)
def application_status(
    world: World, title: str, owner: str | None, status: str
) -> None:
    name = GENITIVE[owner] if owner else world.me
    assert world.status_of(name, title) == status


@bdd_then(rx(r'^відправник листа "(?P<gmail_id>[^"]*)" — "(?P<auth>[^"]*)"$'))
def reply_sender_auth(world: World, gmail_id: str, auth: str) -> None:
    reply = world.reply_of(world.me, gmail_id)
    assert reply is not None, "запису зіставлення нема"
    assert reply.mail.sender_auth.value == auth


# --- відповіді на подачі: ручне пересилання --------------------------------------------------------

FORWARDED = r'ручне пересилання від "(?P<name>[^"]*)" <(?P<address>[^>]*)> з темою "(?P<subject>[^"]*)"'


def forwarded_of(found: re.Match[str]) -> ForwardedMail:
    return ForwardedMail(found["address"], found["name"], found["subject"])


@bdd_then(rx(rf'^в листі "(?P<gmail_id>[^"]*)" позначено {FORWARDED}$'))
def reply_forwarded(
    world: World, gmail_id: str, name: str, address: str, subject: str
) -> None:
    reply = world.reply_of(world.me, gmail_id)
    assert reply is not None, "запису зіставлення нема"
    assert reply.forwarded == ForwardedMail(address, name, subject)


@bdd_then(rx(r'^в листі "(?P<gmail_id>[^"]*)" ручного пересилання не позначено$'))
def reply_not_forwarded(world: World, gmail_id: str) -> None:
    reply = world.reply_of(world.me, gmail_id)
    assert reply is not None, "запису зіставлення нема"
    assert reply.forwarded is None


@action(r"^я (?:запитую|запитав|запитала) огляд пошти для агента$")
def request_overview(world: World) -> None:
    world.overview = world.attempt(
        lambda: world.portal.call(world.mail.inbox_overview, world.actor)
    )


def overview_forward(world: World, gmail_id: str) -> ForwardedMail | None:
    assert world.error is None, world.error
    assert world.overview is not None, "огляд не запитували"
    subject = world.subjects[gmail_id]
    (found,) = [m for m in world.overview.recent if m.subject == subject]
    return world.overview.forwarded.get(found.id)


@bdd_then(rx(rf'^в огляді пошти лист "(?P<gmail_id>[^"]*)" — {FORWARDED}$'))
def overview_forwarded(
    world: World, gmail_id: str, name: str, address: str, subject: str
) -> None:
    assert overview_forward(world, gmail_id) == ForwardedMail(address, name, subject)


@bdd_then(rx(r'^в огляді пошти лист "(?P<gmail_id>[^"]*)" — не ручне пересилання$'))
def overview_not_forwarded(world: World, gmail_id: str) -> None:
    assert overview_forward(world, gmail_id) is None


# --- відповіді на подачі: розбір і список ---------------------------------------------------------


@bdd_given(rx(r'^я додав вакансію "(?P<title>[^"]*)" без подачі$'))
def job_without_application(world: World, title: str) -> None:
    added = world.portal.call(
        world.jobs.add_job, world.actor, JobInput(text=title, title=title)
    )
    world.job_numbers[(world.me, title)] = added.job_number


@bdd_given(rx(r'^подача "(?P<title>[^"]*)" переведена у статус "(?P<status>[^"]*)"$'))
def application_moved(world: World, title: str, status: str) -> None:
    world.portal.call(
        world.applications.set_application_status,
        world.actor,
        world.job_number(world.me, title),
        status,
    )


REVIEW = (
    r'^я (?:розбираю|розібрав|розібрала) відповідь (?P<which>на лист "[^"]*"(?: користувача "[^"]*")?|\d+) '
    r'як "(?P<kind>[^"]*)"(?: (?P<job>для вакансії "[^"]*"|для вакансії \d+|без вакансії))?$'
)
WHICH = re.compile(
    r'^на лист "(?P<gmail_id>[^"]*)"(?: користувача "(?P<owner>[^"]*)")?$'
)
JOB = re.compile(r'^для вакансії (?:"(?P<title>[^"]*)"|(?P<number>\d+))$')


@action(REVIEW)
def review_reply(world: World, which: str, kind: str, job: str | None) -> None:
    named = WHICH.match(which)
    if named is None:
        reply_id = int(which)
    else:
        reply = world.reply_of(named["owner"] or world.me, named["gmail_id"])
        assert reply is not None, "відповіді на цей лист нема"
        reply_id = reply.id
    job_number = None
    if job and (target := JOB.match(job)):
        job_number = (
            int(target["number"])
            if target["number"]
            else world.job_number(world.me, target["title"])
        )
    world.reviewed = world.attempt(
        lambda: world.portal.call(
            world.replies.review_reply,
            world.actor,
            ReviewInput(reply_id=reply_id, type=kind, job_number=job_number),
        )
    )


@bdd_then(
    rx(
        r'^відповідь на лист "(?P<gmail_id>[^"]*)" розібрана як "(?P<kind>[^"]*)" '
        r'(?P<job>для вакансії "[^"]*"|без вакансії)$'
    )
)
def reply_reviewed(world: World, gmail_id: str, kind: str, job: str) -> None:
    reply = world.reply_of(world.me, gmail_id)
    assert reply is not None, "відповіді нема"
    assert reply.type is not None
    assert reply.type.value == kind
    assert reply.reviewed_at == NOW
    if target := JOB.match(job):
        assert reply.job is not None
        assert reply.job.job_number == world.job_number(world.me, target["title"])
    else:
        assert reply.job is None


@bdd_then(rx(r'^відповідь на лист "(?P<gmail_id>[^"]*)" ще не розібрана$'))
def reply_not_reviewed(world: World, gmail_id: str) -> None:
    reply = world.reply_of(world.me, gmail_id)
    assert reply is not None, "відповіді нема"
    assert (reply.type, reply.reviewed_at) == (None, None)


@bdd_when(
    rx(
        r"^я переглядаю (?P<reviewed>розібрані )?відповіді(?: з limit (?P<limit>-?\d+))?$"
    )
)
def browse_replies(world: World, reviewed: str | None, limit: str | None) -> None:
    arguments: dict[str, Any] = {"reviewed": reviewed is not None}
    if limit is not None:
        arguments["limit"] = int(limit)
    world.listed = world.attempt(
        lambda: world.portal.call(
            functools.partial(world.replies.list_replies, world.actor, **arguments)
        )
    )


def reply_ids(world: World, replies: list[Reply]) -> list[str]:
    by_subject = {subject: gmail_id for gmail_id, subject in world.subjects.items()}
    return [by_subject[reply.mail.subject] for reply in replies]


@bdd_then(rx(r'^у списку відповідей за порядком: "(?P<ids>[^"]*)"$'))
def replies_order(world: World, ids: str) -> None:
    assert world.error is None, world.error
    assert world.listed is not None, "список не запитували"
    assert reply_ids(world, world.listed) == shown(ids)


@bdd_then(rx(r"^у списку відповідей (?P<count>\d+) лист\w*$"))
def replies_listed_count(world: World, count: str) -> None:
    assert world.error is None, world.error
    assert world.listed is not None, "список не запитували"
    assert len(world.listed) == int(count)


@bdd_then(
    rx(
        r'^у списку моїх (?P<reviewed>розібраних )?відповідей за порядком: "(?P<ids>[^"]*)"$'
    )
)
def my_replies_order(world: World, reviewed: str | None, ids: str) -> None:
    found = world.portal.call(
        functools.partial(
            world.replies.list_replies, world.actor, reviewed=reviewed is not None
        )
    )
    assert reply_ids(world, found) == shown(ids)


# --- відповіді для вебу: черги, лічильники, пошук ---------------------------------------------------

# Назви черг у вебі → значення `queue` в API; невідома назва йде як є.
QUEUES = {"До розбору": "matched", "Без вакансії": "unmatched", "Розібрані": "reviewed"}


def show_board(world: World, **query: Any) -> None:
    parsed = world.attempt(lambda: ReplyQuery.parse(**query))
    if parsed is not None:
        world.board = world.attempt(
            lambda: world.portal.call(world.replies.board, world.actor, parsed)
        )


@bdd_when(
    rx(
        r'^я переглядаю чергу "(?P<queue>[^"]*)"(?: за пошуком "(?P<text>[^"]*)")?'
        r"(?: за пошуком із (?P<long>\d+) символів)?"
        r"(?: сторінку (?P<page>\d+) по (?P<per_page>\d+))?$"
    )
)
def browse_board(
    world: World,
    queue: str,
    text: str | None,
    long: str | None,
    page: str | None,
    per_page: str | None,
) -> None:
    show_board(
        world,
        queue=QUEUES.get(queue, queue),
        text="я" * int(long) if long else text or "",
        page=int(page or 1),
        per_page=int(per_page or 20),
    )


@bdd_when("я переглядаю відповіді без вибору черги")
def browse_default_queue(world: World) -> None:
    show_board(world)


@bdd_then(rx(r'^у черзі за порядком: "(?P<ids>[^"]*)"$'))
def board_order(world: World, ids: str) -> None:
    assert world.error is None, world.error
    assert world.board is not None, "чергу не запитували"
    assert reply_ids(world, list(world.board.items)) == shown(ids)


@bdd_then(
    rx(
        r"^лічильники: до розбору (?P<matched>\d+), без вакансії (?P<unmatched>\d+), "
        r"розібрані (?P<reviewed>\d+)$"
    )
)
def board_counts(world: World, matched: str, unmatched: str, reviewed: str) -> None:
    assert world.error is None, world.error
    assert world.board is not None, "чергу не запитували"
    counts = world.board.counts
    assert (counts.matched, counts.unmatched, counts.reviewed) == (
        int(matched),
        int(unmatched),
        int(reviewed),
    )


@bdd_then(rx(r"^на сторінці (?P<count>\d+) відповід\w*, усього (?P<total>\d+)$"))
def board_page(world: World, count: str, total: str) -> None:
    assert world.error is None, world.error
    assert world.board is not None, "чергу не запитували"
    assert (len(world.board.items), world.board.page.total) == (int(count), int(total))


# --- LinkedIn-алерти → вакансії ------------------------------------------------------------------


def vacancies(world: World, name: str, **search: Any) -> list[Any]:
    found = world.portal.call(
        world.jobs.list_jobs, actor_of(USERS[name]), JobSearchInput(limit=200, **search)
    )
    return sorted(found, key=lambda job: job.job_number)


def vacancy(world: World, number: str) -> Any:
    return world.portal.call(world.jobs.get_job, world.actor, int(number))


def mail_number(world: World, gmail_id: str) -> int:
    return list(world.store.messages).index(gmail_id) + 1


@action(
    r'^я (?:додаю|додав|додала) вакансію з текстом "(?P<text>[^"]*)" і посиланням "(?P<url>[^"]*)"$'
)
def add_job_with_link(world: World, text: str, url: str) -> None:
    world.added = world.attempt(
        lambda: world.portal.call(
            world.jobs.add_job, world.actor, JobInput(text=text, url=url)
        )
    )


@bdd_then(
    rx(
        r"^синк розібрав (?P<alerts>\d+) алерт\w*: створено (?P<created>\d+), "
        r"уже відомих (?P<known>\d+), з помилкою (?P<failed>\d+)$"
    )
)
def sync_alerts(
    world: World, alerts: str, created: str, known: str, failed: str
) -> None:
    assert world.error is None, world.error
    assert world.report is not None
    found = world.report.alerts
    assert (found.alerts, found.created, found.known, found.failed) == (
        int(alerts),
        int(created),
        int(known),
        int(failed),
    )


@bdd_then(rx(r"^у моїх вакансіях (?P<count>\d+) вакансі\w+$"))
def my_job_count(world: World, count: str) -> None:
    assert len(vacancies(world, world.me)) == int(count)


@bdd_then(rx(r'^у вакансіях користувача "(?P<name>[^"]*)" (?P<count>\d+) вакансі\w+$'))
def user_job_count(world: World, name: str, count: str) -> None:
    assert len(vacancies(world, name)) == int(count)


@bdd_then(rx(r"^у вкладці «Потрібен текст» (?P<count>\d+) вакансі\w+$"))
def needs_text_count(world: World, count: str) -> None:
    assert len(vacancies(world, world.me, needs_text=True)) == int(count)


@bdd_then(rx(r'^вакансії за порядком посад: "(?P<titles>[^"]*)"$'))
def jobs_in_order(world: World, titles: str) -> None:
    assert [job.title for job in vacancies(world, world.me)] == titles.split("; ")


@bdd_then(
    rx(
        r'^вакансія (?P<number>\d+) — "(?P<title>[^"]*)" у компанії "(?P<company>[^"]*)", '
        r'локація "(?P<location>[^"]*)", посилання "(?P<url>[^"]*)"$'
    )
)
def job_fields(
    world: World, number: str, title: str, company: str, location: str, url: str
) -> None:
    job = vacancy(world, number)
    assert (job.title, job.company, job.location, job.url) == (
        title,
        company,
        location,
        url,
    )


@bdd_then(rx(r'^вакансія (?P<number>\d+) має джерело "(?P<source>[^"]*)"$'))
def job_source(world: World, number: str, source: str) -> None:
    assert vacancy(world, number).source == source


@bdd_then(rx(r"^вакансія (?P<number>\d+) потребує тексту$"))
def job_needs_text(world: World, number: str) -> None:
    job = vacancy(world, number)
    assert (job.needs_text, job.text) == (True, None)


@bdd_then(rx(r'^вакансія (?P<number>\d+) має текст "(?P<text>[^"]*)"$'))
def job_text(world: World, number: str, text: str) -> None:
    assert vacancy(world, number).text == text


@bdd_then(
    rx(r"^вакансія (?P<number>\d+) має компанію довжиною (?P<size>\d+) символів$")
)
def job_company_length(world: World, number: str, size: str) -> None:
    assert len(vacancy(world, number).company) == int(size)


@bdd_then(rx(r"^до вакансії (?P<number>\d+) дописано текст$"))
def text_added(world: World, number: str) -> None:
    assert world.error is None, world.error
    assert world.added is not None
    assert (world.added.job_number, world.added.outcome) == (
        int(number),
        AddOutcome.TEXT_ADDED,
    )


@bdd_then(rx(r'^лист "(?P<gmail_id>[^"]*)" розібрано як алерт$'))
def alert_processed(world: World, gmail_id: str) -> None:
    assert mail_number(world, gmail_id) in world.store.alerts_processed


@bdd_then(rx(r'^лист "(?P<gmail_id>[^"]*)" не розібрано як алерт$'))
def alert_not_processed(world: World, gmail_id: str) -> None:
    assert mail_number(world, gmail_id) not in world.store.alerts_processed


@bdd_then(rx(r'^на листі "(?P<gmail_id>[^"]*)" помилка розбору "(?P<error>[^"]*)"$'))
def mail_parse_error(world: World, gmail_id: str, error: str) -> None:
    assert world.store.messages[gmail_id][1].parse_error == error


@bdd_then(rx(r'^на листі "(?P<gmail_id>[^"]*)" помилки розбору нема$'))
def mail_without_parse_error(world: World, gmail_id: str) -> None:
    assert world.store.messages[gmail_id][1].parse_error == ""
