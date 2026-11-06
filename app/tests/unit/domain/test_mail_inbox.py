"""«Вхідні»: текст листа для людини, ліміт синку вручну, сторінки, фільтри, час за Мадридом."""

from datetime import UTC, datetime, timedelta

import pytest

from domain.mail.inbox import (
    DISPLAY_TEXT_LIMIT,
    MAIL_PAGE_SIZES,
    MANUAL_SYNC_LIMIT,
    MANUAL_SYNC_WINDOW,
    RECENT_MAIL_LIMIT,
    MailKind,
    MailPage,
    MailQuery,
    ManualSync,
    ManualSyncLimit,
    display_text,
    manual_sync,
)
from domain.mail.mail import MailCategory
from domain.shared.errors import InvalidFields
from domain.shared.local_time import local_day, local_minute, local_time


def test_display_text_drops_invisible_characters_and_extra_blank_lines() -> None:
    text = "Hi\u202eevil\u200b word\ufeff\x07 ok\r\nline 2\n\n\n\n  \n\tline 3"

    assert display_text(text) == "Hievil word ok\nline 2\n\n\tline 3"


@pytest.mark.parametrize(
    ("text", "shown"),
    [
        (  # кирилична «а» в paypal
            "Go to https://p\u0430ypal.com/login?next=1 now",
            "Go to https://xn--pypal-4ve.com/login?next=1 now",
        ),
        (
            "https://user@\u0435x\u0430mple.com:8443/path",
            "https://user@xn--xmple-4ve7a.com:8443/path",
        ),
        (  # не IDNA-ім'я — коди символів
            "https://a..b.\u0440\u0444/x",
            "https://a..b.\\u0440\\u0444/x",
        ),
        (  # зламаний IPv6 — коди не-ASCII символів
            "http://[::1/\u0448",
            "http://[::1/\\u0448",
        ),
        (
            "https://xn--80a.com/ and https://example.com/a?b=c",
            "https://xn--80a.com/ and https://example.com/a?b=c",
        ),
    ],
)
def test_display_text_shows_link_hosts_in_ascii(text: str, shown: str) -> None:
    assert display_text(text) == shown


def test_display_text_keeps_markup_as_text_for_the_template_to_escape() -> None:
    assert display_text("<script>alert(1)</script>") == "<script>alert(1)</script>"


def test_display_text_is_cut_at_the_limit() -> None:
    shown = display_text("я" * (DISPLAY_TEXT_LIMIT + 1))

    assert shown.startswith("я" * DISPLAY_TEXT_LIMIT + "\n…")
    assert f"показано перші {DISPLAY_TEXT_LIMIT} символів" in shown
    assert display_text("я" * DISPLAY_TEXT_LIMIT) == "я" * DISPLAY_TEXT_LIMIT


SYNC_NOW = datetime(2026, 10, 15, 12, tzinfo=UTC)


def minutes_ago(*minutes: int) -> list[datetime]:
    return [SYNC_NOW - timedelta(minutes=m) for m in minutes]


def test_manual_sync_limit_is_two_per_half_hour() -> None:
    assert MANUAL_SYNC_LIMIT == 2
    assert MANUAL_SYNC_WINDOW.total_seconds() == 30 * 60


@pytest.mark.parametrize(
    ("requested", "state"),
    [
        ([], ManualSync(2)),
        (minutes_ago(10), ManualSync(1)),
        (minutes_ago(5, 10), ManualSync(0, SYNC_NOW + timedelta(minutes=20))),
        # рівно 30 хв тому — уже поза вікном
        (minutes_ago(30, 5), ManualSync(1)),
        (minutes_ago(45, 40), ManualSync(2)),
        # понад ліміт (паралельні запити): звільниться, коли вийде передостанній
        (minutes_ago(1, 20, 29), ManualSync(0, SYNC_NOW + timedelta(minutes=10))),
    ],
)
def test_manual_sync_counts_requests_in_the_sliding_window(
    requested: list[datetime], state: ManualSync
) -> None:
    assert manual_sync(requested, SYNC_NOW) == state


def test_manual_sync_limit_tells_when_the_next_one_is_possible() -> None:
    error = ManualSyncLimit(datetime(2026, 10, 15, 12, 20, tzinfo=UTC))

    assert (
        str(error) == "Синк уже запитано 2 рази за 30 хв — наступний о 14:20 (Мадрид)."
    )
    assert error.next_at == datetime(2026, 10, 15, 12, 20, tzinfo=UTC)


@pytest.mark.parametrize(
    ("utc", "local"),
    [
        # Літній час (CEST, UTC+2): лист о 22:30 UTC — уже наступний день за Мадридом.
        (datetime(2026, 10, 17, 22, 30, tzinfo=UTC), "2026-10-18 00:30"),
        # Перехід на зимовий час 2026-10-25 о 01:00 UTC: 02:30 за Мадридом буває двічі.
        (datetime(2026, 10, 25, 0, 30, tzinfo=UTC), "2026-10-25 02:30"),
        (datetime(2026, 10, 25, 1, 30, tzinfo=UTC), "2026-10-25 02:30"),
        (datetime(2026, 10, 25, 2, 30, tzinfo=UTC), "2026-10-25 03:30"),
        # Зимовий час (CET, UTC+1).
        (datetime(2026, 12, 1, 23, 30, tzinfo=UTC), "2026-12-02 00:30"),
    ],
)
def test_local_time_is_madrid_with_daylight_saving(utc: datetime, local: str) -> None:
    assert f"{local_time(utc):%Y-%m-%d %H:%M}" == local


def test_local_time_keeps_the_moment() -> None:
    moment = datetime(2026, 10, 17, 22, 30, tzinfo=UTC)

    assert local_time(moment) == moment


@pytest.mark.parametrize(
    ("page", "shown"),
    [
        # (перший, останній, є новіші, є старіші, сторінка в межах списку)
        (MailPage(1, 20, 87), (1, 20, False, True, True)),
        (MailPage(2, 20, 87), (21, 40, True, True, True)),
        (MailPage(5, 20, 87), (81, 87, True, False, True)),
        (MailPage(1, 20, 20), (1, 20, False, False, True)),
        (MailPage(1, 20, 0), (1, 0, False, False, False)),
        (MailPage(6, 20, 87), (101, 87, True, False, False)),
    ],
)
def test_mail_page_bounds(
    page: MailPage, shown: tuple[int, int, bool, bool, bool]
) -> None:
    assert (
        page.first,
        page.last,
        page.has_newer,
        page.has_older,
        page.in_range,
    ) == shown


@pytest.mark.parametrize(
    ("utc", "minute", "day"),
    [
        # літній час (UTC+2)
        (datetime(2026, 7, 1, 10, 5, tzinfo=UTC), "2026-07-01 12:05", "2026-07-01"),
        # о 22:30 UTC за Мадридом уже наступний день
        (datetime(2026, 10, 24, 22, 30, tzinfo=UTC), "2026-10-25 00:30", "2026-10-25"),
        # перехід на зимовий час 2026-10-25 о 01:00 UTC: до нього UTC+2, після — UTC+1
        (datetime(2026, 10, 25, 0, 59, tzinfo=UTC), "2026-10-25 02:59", "2026-10-25"),
        (datetime(2026, 10, 25, 1, 0, tzinfo=UTC), "2026-10-25 02:00", "2026-10-25"),
        # зимовий час (UTC+1)
        (datetime(2026, 12, 1, 23, 30, tzinfo=UTC), "2026-12-02 00:30", "2026-12-02"),
    ],
)
def test_local_minute_and_day_are_madrid_time(
    utc: datetime, minute: str, day: str
) -> None:
    assert local_minute(utc) == minute
    assert local_day(utc) == day


@pytest.mark.parametrize(
    ("kind", "categories"),
    [
        (MailKind.COMPANY, {MailCategory.COMPANY}),
        (MailKind.LINKEDIN_ALERT, {MailCategory.LINKEDIN_ALERT}),
        (
            MailKind.LINKEDIN_MESSAGE,
            {MailCategory.LINKEDIN_MESSAGE, MailCategory.LINKEDIN_APPLICATION},
        ),
        (
            MailKind.FORWARDING_CONFIRMATION,
            {MailCategory.FORWARDING_CONFIRMATION},
        ),
        (MailKind.OTHER, {MailCategory.OTHER, MailCategory.SUSPICIOUS}),
        (MailKind.DROPPED, set()),
    ],
)
def test_a_kind_is_a_group_of_stored_categories(
    kind: MailKind, categories: set[MailCategory]
) -> None:
    assert kind.categories == categories


def test_every_stored_category_belongs_to_exactly_one_kind() -> None:
    for category in MailCategory:
        owners = [kind for kind in MailKind if category in kind.categories]
        assert len(owners) == 1, category


def test_defaults_are_the_first_twenty_without_filters() -> None:
    query = MailQuery.parse()

    assert query == MailQuery("", None, MailPage(1, RECENT_MAIL_LIMIT))
    assert MAIL_PAGE_SIZES == (20, 50, 100)
    assert RECENT_MAIL_LIMIT == 20


def test_a_query_takes_text_kind_and_page() -> None:
    query = MailQuery.parse(text="  Acme  ", kind="dropped", page=3, per_page=50)

    assert query == MailQuery("Acme", MailKind.DROPPED, MailPage(3, 50))


@pytest.mark.parametrize("size", [20, 50, 100])
def test_allowed_page_sizes_are_accepted(size: int) -> None:
    assert MailQuery.parse(per_page=size).page.size == size


@pytest.mark.parametrize(
    ("fields", "problems"),
    [
        ({"per_page": 10}, {"per_page": "per_page — один з: 20, 50, 100."}),
        ({"per_page": 0}, {"per_page": "per_page — один з: 20, 50, 100."}),
        ({"page": 0}, {"page": "Сторінка — від 1."}),
        ({"page": -2}, {"page": "Сторінка — від 1."}),
        (
            {"kind": "newsletter"},
            {
                "kind": "Вид — один з: company, linkedin_alert, linkedin_message, "
                "forwarding_confirmation, other, dropped."
            },
        ),
        ({"text": "x" * 201}, {"q": "Пошуковий запит — не довше 200 символів."}),
    ],
)
def test_a_bad_query_names_each_wrong_field(
    fields: dict[str, object], problems: dict[str, str]
) -> None:
    with pytest.raises(InvalidFields) as caught:
        MailQuery.parse(**fields)  # type: ignore[arg-type]

    assert {p.field: p.message for p in caught.value.problems} == problems


def test_all_wrong_query_fields_are_reported_together() -> None:
    with pytest.raises(InvalidFields) as caught:
        MailQuery.parse(kind="x", page=0, per_page=7)

    assert [p.field for p in caught.value.problems] == ["kind", "page", "per_page"]


def test_a_query_of_exactly_200_characters_is_accepted() -> None:
    assert MailQuery.parse(text="x" * 200).text == "x" * 200
