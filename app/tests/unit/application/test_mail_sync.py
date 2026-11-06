"""Синк пошти: нові листи скриньки застосунку розкладаються по користувачах за tag особистої
адреси; скринька й сховища — у пам'яті."""

from dataclasses import fields, replace
from datetime import UTC, datetime, timedelta

import pytest
from anyio.from_thread import BlockingPortal

from application.mail.sync import DroppedMail, MailSyncUseCases, SyncReport
from domain.identity.ids import UserId
from domain.mail.mail import (
    MAIL_DAILY_LIMIT,
    MAIL_DAILY_WINDOW,
    RESYNC_WINDOW,
    DroppedRecord,
    DropReason,
    IncomingMail,
    MailboxError,
    MailCategory,
    MailSyncState,
    personal_address,
)
from domain.mail.sender_auth import SenderAuth
from tests.support.clock import FakeClock
from tests.support.ids import SequentialIds
from tests.support.mail import (
    FakeMailbox,
    InMemoryJobReplies,
    InMemoryMailUnitOfWork,
    MailStore,
    auth_headers,
    user,
)

MAILBOX = "mailroom@example.com"
NOW = datetime(2026, 10, 14, 12, tzinfo=UTC)
USER_A = user(1)
USER_B = user(2)


class MailWorld:
    def __init__(self, portal: BlockingPortal, clock: FakeClock) -> None:
        self.portal = portal
        self.clock = clock
        self.store = MailStore()
        self.sync_mail = MailSyncUseCases(
            lambda: InMemoryMailUnitOfWork(self.store), clock, SequentialIds()
        )

    def address_of(self, user_id: UserId) -> str:
        async def ensure() -> str:
            async with InMemoryMailUnitOfWork(self.store) as uow:
                inbox = await uow.mail_inboxes.ensure(user_id)
                await uow.commit()
            return personal_address(MAILBOX, inbox.tag)

        return self.portal.call(ensure)

    def rotate(self, user_id: UserId) -> str:
        async def rotate() -> str:
            async with InMemoryMailUnitOfWork(self.store) as uow:
                inbox = await uow.mail_inboxes.rotate(user_id)
                await uow.commit()
            return personal_address(MAILBOX, inbox.tag)

        return self.portal.call(rotate)

    def sync(self, box: FakeMailbox, address: str = MAILBOX) -> SyncReport:
        return self.portal.call(self.sync_mail.sync_mail, box, address)

    def stored(self) -> dict[str, tuple[UserId, MailCategory]]:
        return {
            gmail_id: (owner, category)
            for gmail_id, (owner, _, category, _) in self.store.messages.items()
        }

    def dropped(self) -> dict[str, tuple[UserId, DroppedRecord]]:
        return dict(self.store.dropped)


@pytest.fixture
def world(portal: BlockingPortal) -> MailWorld:
    return MailWorld(portal, FakeClock(NOW))


def mail(
    gmail_id: str,
    to: str = "",
    *,
    sender: str = "talent@acme.example",
    age: timedelta = timedelta(days=1),
    dmarc: str = "pass",
) -> IncomingMail:
    return IncomingMail(
        id=gmail_id,
        received_at=NOW - age,
        from_address=sender,
        auth_headers=auth_headers(sender, dmarc),
        delivered_to=(to, "taras@example.com") if to else ("taras@example.com",),
        subject=f"Re: {gmail_id}",
        text="untrusted body",
    )


def burst(prefix: str, to: str, count: int, start: timedelta) -> list[IncomingMail]:
    """`count` листів щохвилини, старші першими; перший — `start` тому."""
    return [
        mail(f"{prefix}{n}", to, age=start - timedelta(minutes=n)) for n in range(count)
    ]


def test_first_sync_reads_the_resync_window_and_routes_by_tag(
    world: MailWorld,
) -> None:
    to_a, to_b = world.address_of(USER_A), world.address_of(USER_B)
    box = FakeMailbox()
    box.deliver(
        mail("old", to_a, age=RESYNC_WINDOW + timedelta(days=1)),
        mail("a1", to_a),
        mail("b1", to_b, sender="jobalerts-noreply@linkedin.com"),
        mail("confirm", to_b, sender="forwarding-noreply@google.com"),
    )

    report = world.sync(box, MAILBOX.upper())

    assert box.since_calls == [NOW - RESYNC_WINDOW]
    assert report.resynced
    assert report.stored == 3
    assert world.stored() == {
        "a1": (USER_A, MailCategory.COMPANY),
        "b1": (USER_B, MailCategory.LINKEDIN_ALERT),
        "confirm": (USER_B, MailCategory.FORWARDING_CONFIRMATION),
    }
    assert world.store.sync[MAILBOX] == MailSyncState(
        history_id=str(box.cursor), synced_at=NOW
    )


def test_mail_with_tag_of_a_never_reaches_b(world: MailWorld) -> None:
    to_a = world.address_of(USER_A)
    world.address_of(USER_B)
    box = FakeMailbox()
    box.deliver(mail("a1", to_a), mail("a2", to_a))

    world.sync(box)

    assert {owner for owner, _ in world.stored().values()} == {USER_A}


def test_next_sync_reads_only_changes_after_the_cursor(world: MailWorld) -> None:
    to_a = world.address_of(USER_A)
    box = FakeMailbox()
    box.deliver(mail("a1", to_a))
    world.sync(box)
    box.deliver(mail("a2", to_a))
    box.fetched.clear()

    report = world.sync(box)

    assert not report.resynced
    assert box.fetched == ["a2"]
    assert report.stored == 1
    assert box.since_calls == [NOW - RESYNC_WINDOW]  # лише перший синк
    assert world.store.sync[MAILBOX].history_id == str(box.cursor)


def test_stored_mail_is_not_fetched_again(world: MailWorld) -> None:
    to_a = world.address_of(USER_A)
    box = FakeMailbox()
    box.deliver(mail("a1", to_a))
    world.sync(box)
    del world.store.sync[MAILBOX]  # курсор втрачено — ресинк того самого
    box.fetched.clear()

    report = world.sync(box)

    assert box.fetched == []
    assert report.known == 1
    assert report.stored == 0
    assert len(world.store.messages) == 1


def test_expired_cursor_falls_back_to_resync(world: MailWorld) -> None:
    to_a = world.address_of(USER_A)
    box = FakeMailbox()
    world.sync(box)
    box.deliver(mail("a1", to_a))
    box.expired_before = box.cursor + 1

    report = world.sync(box)

    assert report.resynced
    assert world.stored() == {"a1": (USER_A, MailCategory.COMPANY)}
    assert len(box.since_calls) == 2


def test_mail_without_a_known_tag_is_only_audited(world: MailWorld) -> None:
    world.address_of(USER_A)
    box = FakeMailbox()
    box.deliver(
        mail("plain", "mailroom@example.com"),
        mail("rotated", "mailroom+zzzzzzzzzzzz@example.com"),
        mail("direct"),
    )

    report = world.sync(box)

    assert report.dropped == [
        DroppedMail("plain", DropReason.NO_TAG),
        DroppedMail("rotated", DropReason.UNKNOWN_TAG),
        DroppedMail("direct", DropReason.NO_TAG),
    ]
    assert world.store.messages == {}
    assert world.store.dropped == {}  # власника нема — лише аудит
    assert world.store.sync[MAILBOX].history_id == str(box.cursor)


def test_the_audit_note_of_a_dropped_mail_has_no_content() -> None:
    note = DroppedMail("g1", DropReason.NO_TAG)

    assert [field.name for field in fields(note)] == ["gmail_id", "reason"]


def test_mail_gone_before_reading_is_counted(world: MailWorld) -> None:
    box = FakeMailbox()
    box.deliver(mail("a1", world.address_of(USER_A)))
    box.gone.add("a1")

    report = world.sync(box)

    assert report.gone == 1
    assert world.store.messages == {}


def test_sync_running_elsewhere_does_nothing(world: MailWorld) -> None:
    box = FakeMailbox()
    box.deliver(mail("a1", world.address_of(USER_A)))
    world.store.sync_busy = True

    report = world.sync(box)

    assert report.locked
    assert box.since_calls == box.fetched == []
    assert world.store.sync == {}


def test_mailbox_error_is_recorded_and_nothing_else_changes(
    world: MailWorld,
) -> None:
    to_a = world.address_of(USER_A)
    box = FakeMailbox()
    box.deliver(mail("a1", to_a))
    world.sync(box)
    box.deliver(mail("a2", to_a))
    box.error = MailboxError("Gmail відповів 500")
    world.clock.advance(timedelta(minutes=30))

    with pytest.raises(MailboxError):
        world.sync(box)

    state = world.store.sync[MAILBOX]
    assert state.last_error == "Gmail відповів 500"
    assert state.failed_at == world.clock.now()
    assert state.history_id == str(box.cursor - 1)  # курсор не зрушив
    assert set(world.store.messages) == {"a1"}

    box.error = None
    world.sync(box)

    assert world.store.sync[MAILBOX].last_error == ""
    assert set(world.store.messages) == {"a1", "a2"}


def test_first_sync_error_leaves_no_cursor(world: MailWorld) -> None:
    box = FakeMailbox(error=MailboxError("down"))

    with pytest.raises(MailboxError):
        world.sync(box)

    assert world.store.sync[MAILBOX].history_id is None


def test_mail_listed_twice_is_stored_once(world: MailWorld) -> None:
    letter = mail("a1", world.address_of(USER_A))
    box = FakeMailbox()
    world.sync(box)
    box.deliver(letter, letter)  # той самий лист у двох записах змін

    report = world.sync(box)

    assert report.stored == 1
    assert report.known == 1
    assert list(world.store.messages) == ["a1"]


def test_mail_over_the_daily_limit_is_recorded_for_its_owner_not_stored(
    world: MailWorld,
) -> None:
    to_a = world.address_of(USER_A)
    box = FakeMailbox()
    flood = burst("f", to_a, MAIL_DAILY_LIMIT + 2, timedelta(hours=10))
    box.deliver(*flood)

    report = world.sync(box)

    over = [letter.id for letter in flood[MAIL_DAILY_LIMIT:]]
    assert report.stored == MAIL_DAILY_LIMIT
    assert report.dropped == [DroppedMail(i, DropReason.DAILY_LIMIT) for i in over]
    assert not set(over) & set(world.store.messages)
    assert {
        gmail_id: (owner, record.reason)
        for gmail_id, (owner, record) in world.dropped().items()
    } == dict.fromkeys(over, (USER_A, DropReason.DAILY_LIMIT))


def test_a_dropped_mail_keeps_the_sender_and_the_subject_but_not_the_text(
    world: MailWorld,
) -> None:
    to_a = world.address_of(USER_A)
    box = FakeMailbox()
    flood = burst("f", to_a, MAIL_DAILY_LIMIT, timedelta(hours=10))
    last = replace(
        mail("over", to_a, sender="spam@flood.example", age=timedelta(hours=1)),
        subject="Win " + "x" * 500,
    )
    box.deliver(*flood, last)

    world.sync(box)

    owner, record = world.dropped()["over"]
    assert owner == USER_A
    assert record == DroppedRecord(
        "over",
        DropReason.DAILY_LIMIT,
        NOW - timedelta(hours=1),
        "spam@flood.example",
        ("Win " + "x" * 500)[:200],
    )
    assert "untrusted body" not in repr(record)


def test_dropped_mail_is_not_read_or_counted_again(world: MailWorld) -> None:
    to_a = world.address_of(USER_A)
    box = FakeMailbox()
    box.deliver(*burst("f", to_a, MAIL_DAILY_LIMIT + 1, timedelta(hours=10)))
    world.sync(box)
    del world.store.sync[MAILBOX]  # курсор втрачено — ресинк того самого
    box.fetched.clear()

    report = world.sync(box)

    assert report.resynced
    assert box.fetched == []
    assert report.known == MAIL_DAILY_LIMIT + 1
    assert report.dropped == []
    assert len(world.store.dropped) == 1


def test_daily_limit_is_a_sliding_window(world: MailWorld) -> None:
    to_a = world.address_of(USER_A)
    box = FakeMailbox()
    start = MAIL_DAILY_WINDOW + timedelta(hours=2)
    box.deliver(*burst("f", to_a, MAIL_DAILY_LIMIT, start))
    # Через добу й хвилину після першого листа вікно вже звільнило одне місце.
    box.deliver(
        mail("next", to_a, age=start - MAIL_DAILY_WINDOW - timedelta(minutes=1))
    )

    report = world.sync(box)

    assert report.stored == MAIL_DAILY_LIMIT + 1
    assert report.dropped == []


def test_daily_limit_of_a_does_not_touch_b(world: MailWorld) -> None:
    to_a, to_b = world.address_of(USER_A), world.address_of(USER_B)
    box = FakeMailbox()
    box.deliver(*burst("f", to_a, MAIL_DAILY_LIMIT + 1, timedelta(hours=10)))
    box.deliver(mail("b1", to_b, age=timedelta(hours=1)))

    world.sync(box)

    assert world.stored()["b1"] == (USER_B, MailCategory.COMPANY)
    assert {owner for owner, _ in world.dropped().values()} == {USER_A}


def test_mail_to_the_old_address_is_recorded_for_its_owner_once(
    world: MailWorld,
) -> None:
    old = world.address_of(USER_A)
    new = world.rotate(USER_A)
    world.address_of(USER_B)
    box = FakeMailbox()
    box.deliver(
        mail("old1", old, age=timedelta(hours=5)),
        mail("old2", old, age=timedelta(hours=2)),
        mail("new1", new),
    )

    report = world.sync(box)
    del world.store.sync[MAILBOX]  # курсор втрачено — ресинк того самого
    box.fetched.clear()
    again = world.sync(box)

    assert report.dropped == [
        DroppedMail("old1", DropReason.RETIRED_TAG),
        DroppedMail("old2", DropReason.RETIRED_TAG),
    ]
    assert world.stored() == {"new1": (USER_A, MailCategory.COMPANY)}
    assert {
        gmail_id: (owner, record.reason, record.from_address, record.subject)
        for gmail_id, (owner, record) in world.dropped().items()
    } == {
        "old1": (USER_A, DropReason.RETIRED_TAG, "talent@acme.example", "Re: old1"),
        "old2": (USER_A, DropReason.RETIRED_TAG, "talent@acme.example", "Re: old2"),
    }
    assert box.fetched == []
    assert again.known == 3
    assert again.dropped == []


def test_old_address_of_a_is_not_routed_to_b(world: MailWorld) -> None:
    old_a = world.address_of(USER_A)
    world.rotate(USER_A)
    old_b = world.address_of(USER_B)
    world.rotate(USER_B)
    box = FakeMailbox()
    box.deliver(mail("a", old_a), mail("b", old_b))

    world.sync(box)

    assert {gmail_id: owner for gmail_id, (owner, _) in world.dropped().items()} == {
        "a": USER_A,
        "b": USER_B,
    }


def test_sync_stores_the_sender_verdict_and_sorts_forged_mail_apart(
    world: MailWorld,
) -> None:
    to_a = world.address_of(USER_A)
    box = FakeMailbox()
    box.deliver(
        mail("ok", to_a, age=timedelta(hours=4)),
        mail("unsure", to_a, age=timedelta(hours=3), dmarc="none"),
        mail("forged", to_a, age=timedelta(hours=2), dmarc="fail"),
        mail(
            "alert",
            to_a,
            sender="jobalerts-noreply@linkedin.com",
            age=timedelta(hours=1),
            dmarc="fail",
        ),
    )

    report = world.sync(box)

    assert report.stored == 4
    assert world.stored() == {
        "ok": (USER_A, MailCategory.COMPANY),
        "unsure": (USER_A, MailCategory.COMPANY),
        "forged": (USER_A, MailCategory.SUSPICIOUS),
        "alert": (USER_A, MailCategory.SUSPICIOUS),
    }
    assert {
        gmail_id: auth for gmail_id, (_, _, _, auth) in world.store.messages.items()
    } == {
        "ok": SenderAuth.VERIFIED,
        "unsure": SenderAuth.UNKNOWN,
        "forged": SenderAuth.FAILED,
        "alert": SenderAuth.FAILED,
    }


def test_only_a_verified_google_confirmation_is_a_forwarding_confirmation(
    world: MailWorld,
) -> None:
    to_a = world.address_of(USER_A)
    box = FakeMailbox()
    google = "forwarding-noreply@google.com"
    box.deliver(
        mail("real", to_a, sender=google, age=timedelta(days=3)),
        mail("unsure", to_a, sender=google, age=timedelta(days=2), dmarc="none"),
        mail("forged", to_a, sender=google, age=timedelta(days=1), dmarc="fail"),
    )

    world.sync(box)

    assert world.stored() == {
        "real": (USER_A, MailCategory.FORWARDING_CONFIRMATION),
        "unsure": (USER_A, MailCategory.OTHER),
        "forged": (USER_A, MailCategory.SUSPICIOUS),
    }


def test_forged_mail_of_a_stays_with_a(world: MailWorld) -> None:
    to_a, to_b = world.address_of(USER_A), world.address_of(USER_B)
    box = FakeMailbox()
    box.deliver(mail("a1", to_a, dmarc="fail"), mail("b1", to_b, dmarc="pass"))

    world.sync(box)

    assert world.stored() == {
        "a1": (USER_A, MailCategory.SUSPICIOUS),
        "b1": (USER_B, MailCategory.COMPANY),
    }


def test_a_failure_while_matching_replies_rolls_back_the_whole_sync(
    world: MailWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    box = FakeMailbox()
    box.deliver(mail("a1", world.address_of(USER_A)))

    async def broken(self: InMemoryJobReplies) -> None:
        raise RuntimeError("boom")

    with monkeypatch.context() as patched:
        patched.setattr(InMemoryJobReplies, "pending", broken)
        with pytest.raises(RuntimeError, match="boom"):
            world.sync(box)

    assert world.stored() == {}
    assert world.store.sync == {}
    # Наступний синк повторює те саме: лист зберігається й зіставляється.
    report = world.sync(box)
    assert (report.stored, report.replies.unmatched) == (1, 1)
    assert set(world.stored()) == {"a1"}
