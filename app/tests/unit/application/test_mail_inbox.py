"""Пошта користувача: адреса, ротація, «Вхідні» (збережені й відкинуті листи, пошук, вид,
сторінки), читалка з кодом пересилання Gmail, синк вручну, огляд для MCP. Чужої пошти не видно."""

from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from anyio.from_thread import BlockingPortal

from application.contracts.actor import Actor, Channel, Scope
from application.contracts.mail import (
    ForwardingData,
    MailDetailData,
    MailInboxData,
    MailSettingsData,
)
from application.mail.inbox import MailUseCases
from application.mail.sync import MailSyncUseCases
from domain.identity.ids import UserId
from domain.mail.inbox import (
    DROPPED_NOTICE_WINDOW,
    RECENT_MAIL_LIMIT,
    DroppedSummary,
    MailList,
    MailPage,
    MailQuery,
    ManualSync,
    ManualSyncLimit,
)
from domain.mail.mail import (
    MAIL_DAILY_LIMIT,
    DropReason,
    IncomingMail,
    MailboxError,
    MailCategory,
)
from domain.mail.sender_auth import SenderAuth
from domain.shared.errors import NotFound
from tests.support.clock import FakeClock
from tests.support.ids import SequentialIds
from tests.support.mail import (
    FakeMailbox,
    InMemoryMailUnitOfWork,
    MailStore,
    auth_headers,
    user,
)

MAILBOX = "mailroom@example.com"
NOW = datetime(2026, 10, 14, 12, tzinfo=UTC)
USER_A = user(1)
USER_B = user(2)
GOOGLE = "forwarding-noreply@google.com"
HOSTILE_TEXT = (
    "Hi\N{RIGHT-TO-LEFT OVERRIDE}evil\N{ZERO WIDTH SPACE} word\n\n\n\n\n"
    "https://p\N{CYRILLIC SMALL LETTER A}ypal.com/x"
)
NOT_CONFIGURED = "Пошту не налаштовано: нема адреси скриньки застосунку."


def actor(user_id: UserId) -> Actor:
    return Actor(
        user_id=user_id,
        channel=Channel.WEB,
        client_id="web",
        grant_id=None,
        scopes=frozenset(Scope),
        correlation_id="test",
    )


class InboxWorld:
    def __init__(self, portal: BlockingPortal, mailbox: str = MAILBOX) -> None:
        self.portal = portal
        self.clock = FakeClock(NOW)
        self.store = MailStore()
        self.mail = MailUseCases(
            lambda: InMemoryMailUnitOfWork(self.store), self.clock, mailbox
        )
        self.sync_mail = MailSyncUseCases(
            lambda: InMemoryMailUnitOfWork(self.store), self.clock, SequentialIds()
        )
        self.box = FakeMailbox()

    def call(
        self, method: Callable[..., Awaitable[object]], user_id: UserId, *args: object
    ) -> object:
        return self.portal.call(lambda: method(actor(user_id), *args))

    def settings(self, user_id: UserId) -> MailSettingsData:
        return self.portal.call(self.mail.settings, actor(user_id))

    def address(self, user_id: UserId) -> str:
        return self.settings(user_id).address

    def rotate(self, user_id: UserId) -> str:
        return self.portal.call(self.mail.rotate_address, actor(user_id))

    def request_sync(self, user_id: UserId) -> ManualSync:
        return self.portal.call(self.mail.request_sync, actor(user_id))

    def listing(self, user_id: UserId, **fields: object) -> MailList:
        query = MailQuery.parse(**fields)  # type: ignore[arg-type]
        return self.portal.call(self.mail.list_mail, actor(user_id), query)

    def subjects(self, user_id: UserId, **fields: object) -> list[str]:
        return [item.subject for item in self.listing(user_id, **fields).items]

    def detail(self, user_id: UserId, mail_id: int) -> MailDetailData:
        return self.portal.call(self.mail.get_mail, actor(user_id), mail_id)

    def overview(self, user_id: UserId) -> MailInboxData:
        return self.portal.call(self.mail.inbox_overview, actor(user_id))

    def deliver_and_sync(self, *mails: IncomingMail) -> None:
        self.box.deliver(*mails)
        self.portal.call(self.sync_mail.sync_mail, self.box, MAILBOX)


@pytest.fixture
def world(portal: BlockingPortal) -> InboxWorld:
    return InboxWorld(portal)


def mail(
    gmail_id: str,
    to: str,
    *,
    sender: str = "talent@acme.example",
    age: timedelta = timedelta(days=1),
    dmarc: str = "pass",
    subject: str = "",
    text: str = "untrusted body",
    name: str = "",
) -> IncomingMail:
    return IncomingMail(
        id=gmail_id,
        received_at=NOW - age,
        from_address=sender,
        from_name=name,
        auth_headers=auth_headers(sender, dmarc),
        delivered_to=(to, "taras@example.com"),
        subject=subject or f"Re: {gmail_id}",
        text=text,
    )


def confirmation(gmail_id: str, to: str, code: str, age: timedelta) -> IncomingMail:
    subject = f"(#{code}) Gmail Forwarding Confirmation - Receive Mail from a@b.c"
    return mail(gmail_id, to, sender=GOOGLE, age=age, subject=subject, text="")


# --- адреса, налаштування, ротація ---


def test_the_address_is_created_once_and_differs_per_user(world: InboxWorld) -> None:
    first = world.address(USER_A)

    assert first == world.address(USER_A)
    assert first.startswith("mailroom+")
    assert first.endswith("@example.com")
    assert world.address(USER_B) != first


def test_settings_of_a_new_user_have_no_sync_yet_and_two_manual_syncs(
    world: InboxWorld,
) -> None:
    settings = world.settings(USER_A)

    assert settings.rotated_at is None
    assert settings.synced_at is None
    assert not settings.sync_failed
    assert settings.sync_error == ""
    assert settings.manual == ManualSync(2)


def test_settings_show_the_last_successful_sync(world: InboxWorld) -> None:
    world.deliver_and_sync()

    settings = world.settings(USER_A)

    assert settings.synced_at == NOW
    assert not settings.sync_failed


def test_settings_show_a_failed_sync(world: InboxWorld) -> None:
    world.deliver_and_sync()
    world.box.error = MailboxError("Gmail відповів 500")
    world.clock.advance(timedelta(minutes=30))

    with pytest.raises(MailboxError):
        world.portal.call(world.sync_mail.sync_mail, world.box, MAILBOX)

    settings = world.settings(USER_A)
    assert settings.synced_at == NOW
    assert settings.sync_failed
    assert settings.sync_error == "Gmail відповів 500"


def test_rotation_gives_a_new_address_and_the_old_one_is_only_recorded(
    world: InboxWorld,
) -> None:
    old = world.address(USER_A)

    new = world.rotate(USER_A)

    assert new != old
    settings = world.settings(USER_A)
    assert settings.address == new
    assert settings.rotated_at is not None
    world.deliver_and_sync(mail("old", old), mail("new", new))
    assert [i.subject for i in world.listing(USER_A).items if not i.dropped] == [
        "Re: new"
    ]
    dropped = [i for i in world.listing(USER_A).items if i.dropped]
    assert [(i.subject, i.reason) for i in dropped] == [
        ("Re: old", DropReason.RETIRED_TAG)
    ]


def test_rotation_of_a_does_not_touch_b(world: InboxWorld) -> None:
    address_b = world.address(USER_B)

    world.rotate(USER_A)

    assert world.address(USER_B) == address_b
    assert world.settings(USER_B).rotated_at is None


@pytest.mark.parametrize(
    "use_case",
    ["settings", "rotate_address", "request_sync", "inbox_overview"],
)
def test_mail_needs_the_app_mailbox(portal: BlockingPortal, use_case: str) -> None:
    world = InboxWorld(portal, mailbox="")

    with pytest.raises(Exception, match="не налаштовано") as caught:
        world.call(getattr(world.mail, use_case), USER_A)

    assert str(caught.value) == NOT_CONFIGURED
    assert world.store.inboxes == {}
    assert world.store.sync_requests == []


@pytest.mark.parametrize("use_case", ["list_mail", "get_mail"])
def test_reading_mail_needs_the_app_mailbox_too(
    portal: BlockingPortal, use_case: str
) -> None:
    world = InboxWorld(portal, mailbox="")
    argument = MailQuery.parse() if use_case == "list_mail" else 1

    with pytest.raises(Exception, match="не налаштовано"):
        world.call(getattr(world.mail, use_case), USER_A, argument)


# --- «Вхідні» ---


def test_the_list_has_newest_first_and_only_own_mail(world: InboxWorld) -> None:
    to_a, to_b = world.address(USER_A), world.address(USER_B)
    world.deliver_and_sync(
        mail("old", to_a, age=timedelta(days=3)),
        mail("new", to_a, age=timedelta(hours=1)),
        mail("mid", to_a, age=timedelta(days=1)),
        mail("theirs", to_b),
    )

    assert world.subjects(USER_A) == ["Re: new", "Re: mid", "Re: old"]
    assert world.subjects(USER_B) == ["Re: theirs"]


def test_a_row_has_sender_subject_kind_and_verdict_but_no_text(
    world: InboxWorld,
) -> None:
    to_a = world.address(USER_A)
    world.deliver_and_sync(mail("m1", to_a, name="María", dmarc="fail"))

    row = world.listing(USER_A).items[0]

    assert (row.dropped, row.from_address, row.from_name, row.subject) == (
        False,
        "talent@acme.example",
        "María",
        "Re: m1",
    )
    assert (row.category, row.sender_auth, row.reason) == (
        MailCategory.SUSPICIOUS,
        SenderAuth.FAILED,
        None,
    )
    assert not hasattr(row, "text")


def test_the_first_page_has_twenty_rows_and_the_next_has_the_rest(
    world: InboxWorld,
) -> None:
    to_a = world.address(USER_A)
    world.deliver_and_sync(
        *(mail(f"m{n}", to_a, age=timedelta(hours=n)) for n in range(1, 46))
    )

    first = world.listing(USER_A)
    second = world.listing(USER_A, page=2)
    third = world.listing(USER_A, page=3)

    assert (first.page.total, len(first.items)) == (45, RECENT_MAIL_LIMIT)
    assert first.items[0].subject == "Re: m1"
    assert second.items[0].subject == "Re: m21"
    assert len(third.items) == 5
    assert (first.page.has_newer, first.page.has_older) == (False, True)
    assert (third.page.has_newer, third.page.has_older) == (True, False)


@pytest.mark.parametrize(("size", "rows"), [(20, 20), (50, 30), (100, 30)])
def test_page_sizes_20_50_and_100(world: InboxWorld, size: int, rows: int) -> None:
    to_a = world.address(USER_A)
    world.deliver_and_sync(
        *(mail(f"m{n}", to_a, age=timedelta(hours=n)) for n in range(1, 31))
    )

    assert len(world.listing(USER_A, per_page=size).items) == rows


def test_a_page_beyond_the_list_is_empty_but_keeps_the_total(
    world: InboxWorld,
) -> None:
    to_a = world.address(USER_A)
    world.deliver_and_sync(mail("m1", to_a))

    beyond = world.listing(USER_A, page=7)

    assert beyond.items == ()
    assert beyond.page.total == 1
    assert not beyond.page.in_range


def test_an_empty_inbox_is_an_empty_list(world: InboxWorld) -> None:
    listing = world.listing(USER_A)

    assert listing.items == ()
    assert listing.page == MailPage(1, 20, 0)


@pytest.mark.parametrize(
    ("text", "found"),
    [
        ("acme", ["Re: with-text", "Re: by-address"]),  # адреса відправника
        ("MARÍA", ["Re: by-name"]),  # ім'я, без урахування регістру
        ("interview", ["Re: with-text", "interview slot"]),  # тема й текст
        ("nothing like this", []),
    ],
)
def test_search_covers_sender_subject_and_text_case_insensitively(
    world: InboxWorld, text: str, found: list[str]
) -> None:
    to_a = world.address(USER_A)
    world.deliver_and_sync(
        mail(
            "with-text", to_a, text="Your interview is booked", age=timedelta(hours=4)
        ),
        mail(
            "by-name",
            to_a,
            name="María",
            sender="x@other.example",
            age=timedelta(hours=3),
        ),
        mail(
            "by-address",
            to_a,
            sender="hr@acme.example",
            text="hi",
            age=timedelta(hours=2),
        ),
        mail(
            "slot",
            to_a,
            subject="interview slot",
            sender="x@other.example",
            text="hi",
            age=timedelta(hours=1),
        ),
    )

    got = world.subjects(USER_A, text=text)

    assert sorted(got) == sorted(found) or set(got) == set(found)


def test_search_does_not_treat_wildcards_as_wildcards(world: InboxWorld) -> None:
    to_a = world.address(USER_A)
    world.deliver_and_sync(
        mail("m1", to_a, subject="100% sure"), mail("m2", to_a, subject="plain")
    )

    assert world.subjects(USER_A, text="%") == ["100% sure"]
    assert world.subjects(USER_A, text="_") == []


def test_search_never_finds_the_mail_of_another_user(world: InboxWorld) -> None:
    world.address(USER_A)
    to_b = world.address(USER_B)
    world.deliver_and_sync(mail("b1", to_b, subject="secret offer"))

    assert world.subjects(USER_A, text="secret") == []
    assert world.subjects(USER_B, text="secret") == ["secret offer"]


@pytest.mark.parametrize(
    ("kind", "subjects"),
    [
        ("company", ["company"]),
        ("linkedin_alert", ["alert"]),
        ("linkedin_message", ["message", "application"]),
        ("forwarding_confirmation", ["confirm"]),
        ("other", ["other", "forged"]),
    ],
)
def test_the_kind_filter_narrows_the_list(
    world: InboxWorld, kind: str, subjects: list[str]
) -> None:
    to_a = world.address(USER_A)
    sender = {
        "company": "talent@acme.example",
        "alert": "jobalerts-noreply@linkedin.com",
        "message": "messages-noreply@linkedin.com",
        "application": "jobs-noreply@linkedin.com",
        "confirm": GOOGLE,
        "other": "news@linkedin.com",
        "forged": "talent@acme.example",
    }
    world.deliver_and_sync(
        *(
            mail(
                name,
                to_a,
                sender=address,
                subject=name,
                dmarc="fail" if name == "forged" else "pass",
                age=timedelta(hours=index),
            )
            for index, (name, address) in enumerate(sender.items(), start=1)
        )
    )

    assert set(world.subjects(USER_A, kind=kind)) == set(subjects)


def test_kind_and_search_work_together(world: InboxWorld) -> None:
    to_a = world.address(USER_A)
    world.deliver_and_sync(
        mail("a", to_a, subject="Acme call"),
        mail("b", to_a, subject="Acme alert", sender="jobalerts-noreply@linkedin.com"),
    )

    assert world.subjects(USER_A, text="acme", kind="company") == ["Acme call"]


# --- відкинуті листи в «Вхідних» ---


def flood(world: InboxWorld, to: str, extra: int = 1) -> None:
    world.deliver_and_sync(
        *(
            mail(f"f{n}", to, age=timedelta(hours=10) - timedelta(minutes=n))
            for n in range(MAIL_DAILY_LIMIT + extra)
        )
    )


def test_a_dropped_mail_is_in_the_list_with_reason_sender_and_subject(
    world: InboxWorld,
) -> None:
    to_a = world.address(USER_A)
    flood(world, to_a)

    dropped = [i for i in world.listing(USER_A, per_page=100).items if i.dropped]

    assert len(dropped) == 1
    row = dropped[0]
    assert row.reason is DropReason.DAILY_LIMIT
    assert (row.from_address, row.subject) == ("talent@acme.example", "Re: f100")
    assert (row.category, row.sender_auth, row.from_name) == (None, None, "")


def test_the_dropped_mail_leaves_the_list_after_thirty_days(
    world: InboxWorld,
) -> None:
    to_a = world.address(USER_A)
    flood(world, to_a)
    assert world.listing(USER_A, kind="dropped").page.total == 1

    world.clock.advance(DROPPED_NOTICE_WINDOW)

    assert world.listing(USER_A, kind="dropped").page.total == 0


def test_the_dropped_kind_shows_only_dropped_and_other_kinds_hide_them(
    world: InboxWorld,
) -> None:
    to_a = world.address(USER_A)
    flood(world, to_a)

    dropped = world.listing(USER_A, kind="dropped")
    company = world.listing(USER_A, kind="company", per_page=100)

    assert [i.dropped for i in dropped.items] == [True]
    assert not any(i.dropped for i in company.items)
    assert company.page.total == MAIL_DAILY_LIMIT


def test_search_finds_a_dropped_mail_by_sender_and_subject_but_not_by_text(
    world: InboxWorld,
) -> None:
    to_a = world.address(USER_A)
    letters = [
        mail(f"f{n}", to_a, age=timedelta(hours=10) - timedelta(minutes=n))
        for n in range(MAIL_DAILY_LIMIT)
    ]
    over = mail(
        "over",
        to_a,
        sender="spam@flood.example",
        subject="Win a prize",
        text="secret-body",
        age=timedelta(hours=1),
    )
    world.deliver_and_sync(*letters, over)

    assert world.subjects(USER_A, text="flood.example") == ["Win a prize"]
    assert world.subjects(USER_A, text="prize") == ["Win a prize"]
    assert world.subjects(USER_A, text="secret-body") == []


def test_dropped_mail_of_a_is_not_in_the_list_of_b(world: InboxWorld) -> None:
    to_a = world.address(USER_A)
    world.address(USER_B)
    flood(world, to_a)

    assert world.listing(USER_B).items == ()


def test_dropped_and_stored_mail_are_ordered_by_time(world: InboxWorld) -> None:
    old = world.address(USER_A)
    new = world.rotate(USER_A)
    world.deliver_and_sync(
        mail("a", new, age=timedelta(hours=5)),
        mail("b", old, age=timedelta(hours=3)),
        mail("c", new, age=timedelta(hours=1)),
    )

    rows = world.listing(USER_A).items

    assert [(i.subject, i.dropped) for i in rows] == [
        ("Re: c", False),
        ("Re: b", True),
        ("Re: a", False),
    ]


# --- читалка ---


def test_the_reader_gives_the_mail_with_a_text_prepared_for_a_human(
    world: InboxWorld,
) -> None:
    to_a = world.address(USER_A)
    world.deliver_and_sync(mail("m1", to_a, text=HOSTILE_TEXT))
    row = world.listing(USER_A).items[0]

    detail = world.detail(USER_A, row.id)

    assert detail.mail.subject == "Re: m1"
    assert detail.text == "Hievil word\n\nhttps://xn--pypal-4ve.com/x"
    assert detail.forwarding is None


def test_the_mail_of_another_user_or_a_missing_one_is_not_found(
    world: InboxWorld,
) -> None:
    to_a = world.address(USER_A)
    world.address(USER_B)
    world.deliver_and_sync(mail("m1", to_a))
    mail_id = world.listing(USER_A).items[0].id

    with pytest.raises(NotFound):
        world.detail(USER_B, mail_id)
    with pytest.raises(NotFound):
        world.detail(USER_A, mail_id + 100)


def test_a_gmail_confirmation_is_a_normal_mail_with_its_code(
    world: InboxWorld,
) -> None:
    to_a = world.address(USER_A)
    world.deliver_and_sync(confirmation("c1", to_a, "418306552", timedelta(days=1)))
    row = world.listing(USER_A).items[0]

    detail = world.detail(USER_A, row.id)

    assert row.category is MailCategory.FORWARDING_CONFIRMATION
    assert detail.forwarding == ForwardingData(
        code="418306552",
        requested_by="a@b.c",
        received_at=NOW - timedelta(days=1),
        current=True,
    )
    assert not detail.forwarding.link_only


def test_a_gmail_confirmation_without_a_code_is_link_only(world: InboxWorld) -> None:
    to_a = world.address(USER_A)
    letter = mail(
        "c1",
        to_a,
        sender=GOOGLE,
        subject="Gmail Forwarding Confirmation",
        text="taras@example.com has requested to forward mail. Follow the link.",
    )
    world.deliver_and_sync(letter)

    detail = world.detail(USER_A, world.listing(USER_A).items[0].id)

    assert detail.forwarding is not None
    assert (detail.forwarding.code, detail.forwarding.requested_by) == (
        "",
        "taras@example.com",
    )
    assert detail.forwarding.link_only


def test_a_confirmation_from_before_the_rotation_is_not_current(
    world: InboxWorld,
) -> None:
    to_a = world.address(USER_A)
    world.deliver_and_sync(confirmation("c1", to_a, "111111111", timedelta(days=30)))
    new = world.rotate(USER_A)
    world.deliver_and_sync(confirmation("c2", new, "222222222", timedelta(days=1)))
    rows = {i.subject[:11]: i.id for i in world.listing(USER_A).items}

    old, fresh = (
        world.detail(USER_A, rows["(#111111111"]),
        world.detail(USER_A, rows["(#222222222"]),
    )

    assert old.forwarding is not None
    assert old.forwarding.current is False
    assert fresh.forwarding is not None
    assert fresh.forwarding.current is True


def test_only_a_verified_google_confirmation_carries_a_code(
    world: InboxWorld,
) -> None:
    to_a = world.address(USER_A)
    forged = replace(
        confirmation("c3", to_a, "333333333", timedelta(days=1)),
        auth_headers=auth_headers(GOOGLE, "fail"),
    )
    world.deliver_and_sync(forged)
    row = world.listing(USER_A).items[0]

    assert row.category is MailCategory.SUSPICIOUS
    assert world.detail(USER_A, row.id).forwarding is None


# --- синк вручну ---


def test_manual_sync_twice_then_the_limit_until_the_window_passes(
    world: InboxWorld,
) -> None:
    first = world.request_sync(USER_A)
    world.clock.advance(timedelta(minutes=5))
    second = world.request_sync(USER_A)
    world.clock.advance(timedelta(minutes=5))
    with pytest.raises(ManualSyncLimit) as refused:
        world.request_sync(USER_A)
    world.clock.advance(timedelta(minutes=21))
    later = world.request_sync(USER_A)

    assert first == ManualSync(1)
    assert second == ManualSync(0, NOW + timedelta(minutes=30))
    assert refused.value.next_at == NOW + timedelta(minutes=30)
    assert str(refused.value) == (
        "Синк уже запитано 2 рази за 30 хв — наступний о 14:30 (Мадрид)."
    )
    assert later == ManualSync(0, NOW + timedelta(minutes=35))
    assert len(world.store.sync_requests) == 3  # відмова нічого не записала


def test_the_manual_sync_counter_counts_only_own_requests(world: InboxWorld) -> None:
    world.request_sync(USER_A)
    world.request_sync(USER_A)

    assert world.settings(USER_A).manual.remaining == 0
    assert world.settings(USER_B).manual == ManualSync(2)
    assert world.request_sync(USER_B) == ManualSync(1)


def test_the_sync_process_marks_pending_requests_as_handled(
    world: InboxWorld,
) -> None:
    world.request_sync(USER_A)
    world.request_sync(USER_B)
    assert [done for _, _, done in world.store.sync_requests] == [None, None]

    world.deliver_and_sync()

    assert [done for _, _, done in world.store.sync_requests] == [NOW, NOW]
    # Виконані запити лишаються в ліміті: вікно рахує запити, а не їх виконання.
    assert world.settings(USER_A).manual.remaining == 1


def test_a_failed_sync_leaves_requests_pending(world: InboxWorld) -> None:
    world.request_sync(USER_A)
    world.box.error = MailboxError("down")

    with pytest.raises(MailboxError):
        world.portal.call(world.sync_mail.sync_mail, world.box, MAILBOX)

    assert [done for _, _, done in world.store.sync_requests] == [None]


# --- огляд для MCP ---


def test_the_overview_has_address_code_and_newest_mail_first(
    world: InboxWorld,
) -> None:
    to_a = world.address(USER_A)
    world.deliver_and_sync(
        confirmation("c1", to_a, "111111111", timedelta(days=3)),
        confirmation("c2", to_a, "222222222", timedelta(days=2)),
        mail("a1", to_a, age=timedelta(hours=1)),
    )

    overview = world.overview(USER_A)

    assert overview.address == to_a
    assert overview.forwarding is not None
    assert (overview.forwarding.code, overview.forwarding.requested_by) == (
        "222222222",
        "a@b.c",
    )
    assert overview.synced_at == NOW
    assert not overview.sync_failed
    assert overview.recent[0].subject == "Re: a1"
    assert [m.category for m in overview.recent] == [
        MailCategory.COMPANY,
        MailCategory.FORWARDING_CONFIRMATION,
        MailCategory.FORWARDING_CONFIRMATION,
    ]


def test_the_overview_has_at_most_twenty_stored_mails_and_no_dropped(
    world: InboxWorld,
) -> None:
    to_a = world.address(USER_A)
    flood(world, to_a, extra=5)

    overview = world.overview(USER_A)

    assert len(overview.recent) == RECENT_MAIL_LIMIT
    assert all(m.category is MailCategory.COMPANY for m in overview.recent)


def test_the_overview_has_no_code_when_none_came_or_it_is_from_before_rotation(
    world: InboxWorld,
) -> None:
    to_a = world.address(USER_A)
    assert world.overview(USER_A).forwarding is None
    world.deliver_and_sync(confirmation("c1", to_a, "111111111", timedelta(days=30)))
    assert world.overview(USER_A).forwarding is not None

    world.rotate(USER_A)

    assert world.overview(USER_A).forwarding is None


def test_the_overview_counts_only_own_drops_within_the_window(
    world: InboxWorld,
) -> None:
    to_a = world.address(USER_A)
    old = world.rotate(USER_A)
    new = world.address(USER_A)
    world.address(USER_B)
    world.deliver_and_sync(
        *(
            mail(f"f{n}", new, age=timedelta(hours=10) - timedelta(minutes=n))
            for n in range(MAIL_DAILY_LIMIT + 1)
        ),
        mail("old1", to_a, age=timedelta(hours=2)),
        mail("forged", new, dmarc="fail", age=timedelta(hours=11)),
    )
    assert old == new

    mine = world.overview(USER_A)
    theirs = world.overview(USER_B)

    assert mine.limit_drops.count == 1
    assert mine.old_address_drops == DroppedSummary(1, NOW - timedelta(hours=2))
    assert mine.suspicious == DroppedSummary(1, NOW - timedelta(hours=11))
    assert theirs.limit_drops == theirs.old_address_drops == DroppedSummary()
    assert theirs.suspicious == DroppedSummary()

    world.clock.advance(DROPPED_NOTICE_WINDOW)
    assert world.overview(USER_A).limit_drops == DroppedSummary()


def test_the_overview_of_b_has_nothing_of_a(world: InboxWorld) -> None:
    to_a = world.address(USER_A)
    world.deliver_and_sync(confirmation("c1", to_a, "111111111", timedelta(days=1)))

    theirs = world.overview(USER_B)

    assert theirs.recent == ()
    assert theirs.forwarding is None
    assert theirs.address != to_a
