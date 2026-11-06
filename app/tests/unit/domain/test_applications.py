"""Подачі (домен): матриця переходів, дата, канал, ATS, домени й адреси компанії — правила v1."""

from datetime import date

import pytest

from domain.applications.application import (
    ACTIVE_STATUSES,
    CLOSED_STATUSES,
    MAX_CONTACTS,
    TRANSITIONS,
    ApplicationChannel,
    ApplicationStatus,
    AtsPlatform,
    NewApplication,
    allowed_transitions,
    check_transition,
    parse_status,
    parse_status_filter,
)
from domain.shared.errors import InvalidFields, InvalidValue

TODAY = date(2026, 3, 2)
S = ApplicationStatus

# Матриця v1: з кожного статусу — куди можна, решта заборонено.
ALLOWED = {
    S.APPLIED: {S.REPLIED, S.INTERVIEW, S.OFFER, S.REJECTED, S.WITHDRAWN},
    S.REPLIED: {S.INTERVIEW, S.OFFER, S.REJECTED, S.WITHDRAWN},
    S.INTERVIEW: {S.OFFER, S.REJECTED, S.WITHDRAWN},
    S.OFFER: {S.WITHDRAWN},
    S.REJECTED: set(),
    S.WITHDRAWN: set(),
}
ALL_PAIRS = [(a, b) for a in S for b in S]
MOVES = [(a, b) for a, b in ALL_PAIRS if b in ALLOWED[a]]
SAME = [(a, a) for a in S]
CLOSED = [(a, b) for a, b in ALL_PAIRS if not ALLOWED[a] and a != b]
BACKWARDS = [
    (a, b) for a, b in ALL_PAIRS if ALLOWED[a] and a != b and b not in ALLOWED[a]
]


def parse(**fields: object) -> NewApplication:
    base: dict[str, object] = {
        "applied_on": "2026-03-01",
        "today": TODAY,
        "channel": "email",
        "ats": "",
        "company_domains": [],
        "company_emails": [],
    }
    return NewApplication.parse(**(base | fields))  # type: ignore[arg-type]


def problems(**fields: object) -> list[tuple[str, str]]:
    with pytest.raises(InvalidFields) as caught:
        parse(**fields)
    return [(p.field, p.message) for p in caught.value.problems]


def test_the_transition_table_is_the_v1_matrix() -> None:
    assert {a: set(b) for a, b in TRANSITIONS.items()} == ALLOWED


def test_there_are_six_statuses_in_the_funnel_order() -> None:
    assert [s.value for s in S] == [
        "applied",
        "replied",
        "interview",
        "offer",
        "rejected",
        "withdrawn",
    ]


def test_active_and_closed_groups_split_the_statuses() -> None:
    assert {S.APPLIED, S.REPLIED, S.INTERVIEW, S.OFFER} == ACTIVE_STATUSES
    assert {S.REJECTED, S.WITHDRAWN} == CLOSED_STATUSES


@pytest.mark.parametrize(("current", "new"), MOVES)
def test_every_allowed_move_changes_the_status(
    current: ApplicationStatus, new: ApplicationStatus
) -> None:
    assert check_transition(current, new) is True


@pytest.mark.parametrize(("current", "new"), SAME)
def test_the_same_status_changes_nothing(
    current: ApplicationStatus, new: ApplicationStatus
) -> None:
    assert check_transition(current, new) is False


@pytest.mark.parametrize(("current", "new"), CLOSED)
def test_a_closed_application_never_moves(
    current: ApplicationStatus, new: ApplicationStatus
) -> None:
    with pytest.raises(InvalidValue) as caught:
        check_transition(current, new)
    assert caught.value.field == "status"
    assert caught.value.message == (
        f"Подачу вже закрито ({current.value}): статус більше не змінюється."
    )


@pytest.mark.parametrize(("current", "new"), BACKWARDS)
def test_a_move_back_is_refused_with_the_v1_text(
    current: ApplicationStatus, new: ApplicationStatus
) -> None:
    with pytest.raises(InvalidValue) as caught:
        check_transition(current, new)
    assert caught.value.field == "status"
    assert caught.value.message == (
        f"Статус {current.value} → {new.value} неможливий: він рухається лише вперед "
        "(applied → replied → interview → offer; rejected і withdrawn закривають подачу)."
    )


def test_every_pair_is_covered_exactly_once() -> None:
    assert len(MOVES) + len(SAME) + len(CLOSED) + len(BACKWARDS) == len(S) ** 2


@pytest.mark.parametrize("status", list(S))
def test_allowed_transitions_follow_the_matrix_in_funnel_order(
    status: ApplicationStatus,
) -> None:
    assert allowed_transitions(status) == tuple(s for s in S if s in ALLOWED[status])


def test_a_status_is_parsed_from_its_name_with_spaces_trimmed() -> None:
    assert parse_status(" interview ") is S.INTERVIEW


def test_an_unknown_status_names_the_allowed_ones() -> None:
    with pytest.raises(InvalidValue) as caught:
        parse_status("hired")
    assert caught.value.field == "status"
    assert caught.value.message == (
        "Статус — один з: applied, replied, interview, offer, rejected, withdrawn."
    )


def test_a_status_filter_by_name_is_that_status() -> None:
    assert parse_status_filter("offer") == {S.OFFER}


def test_the_active_group_filter_is_the_four_open_statuses() -> None:
    assert parse_status_filter("active") == ACTIVE_STATUSES


def test_the_closed_group_filter_is_the_two_closing_statuses() -> None:
    assert parse_status_filter("closed") == CLOSED_STATUSES


def test_an_unknown_status_filter_is_refused() -> None:
    with pytest.raises(InvalidValue) as caught:
        parse_status_filter("hired")
    assert caught.value.field == "status"
    assert caught.value.message == (
        "Статус — один з: applied, replied, interview, offer, rejected, withdrawn, "
        "active, closed."
    )


# --- дата подачі ---


def test_an_empty_date_is_today() -> None:
    assert parse(applied_on="").applied_on == TODAY


def test_a_blank_date_is_today() -> None:
    assert parse(applied_on="   ").applied_on == TODAY


def test_a_past_date_is_kept() -> None:
    assert parse(applied_on="2026-02-27").applied_on == date(2026, 2, 27)


def test_today_itself_is_accepted() -> None:
    assert parse(applied_on="2026-03-02").applied_on == TODAY


def test_a_future_date_is_refused() -> None:
    assert problems(applied_on="2026-03-03") == [
        ("applied_on", "Дата подачі не може бути в майбутньому.")
    ]


@pytest.mark.parametrize(
    "value", ["02.03.2026", "2026-3-2", "2026/03/02", "yesterday", "2026-02-30", "x"]
)
def test_a_date_not_in_iso_format_is_refused(value: str) -> None:
    assert problems(applied_on=value) == [
        ("applied_on", "Дата подачі — у форматі YYYY-MM-DD.")
    ]


def test_a_date_with_non_ascii_digits_is_refused() -> None:
    assert problems(applied_on="２０２６-０３-０１") == [
        ("applied_on", "Дата подачі — у форматі YYYY-MM-DD.")
    ]


# --- канал і ATS ---


@pytest.mark.parametrize("channel", list(ApplicationChannel))
def test_every_channel_is_accepted(channel: ApplicationChannel) -> None:
    assert parse(channel=channel.value).channel is channel


def test_a_channel_is_trimmed() -> None:
    assert parse(channel=" ats ").channel is ApplicationChannel.ATS


def test_an_unknown_channel_names_the_allowed_ones() -> None:
    assert problems(channel="phone") == [
        ("channel", "Канал — один з: email, ats, linkedin, referral.")
    ]


def test_an_empty_channel_is_refused() -> None:
    assert problems(channel="")[0][0] == "channel"


def test_ats_is_optional() -> None:
    assert parse(ats="").ats is None
    assert parse(ats="  ").ats is None


@pytest.mark.parametrize("ats", list(AtsPlatform))
def test_every_ats_platform_is_accepted(ats: AtsPlatform) -> None:
    assert parse(ats=ats.value).ats is ats


def test_an_unknown_ats_names_the_allowed_ones() -> None:
    assert problems(ats="workday") == [
        (
            "ats",
            "ATS — один з: greenhouse, lever, ashby, workable, smartrecruiters, other.",
        )
    ]


# --- домени компанії ---


@pytest.mark.parametrize(
    "value",
    [
        "https://www.Acme.com/jobs",
        "@acme.com",
        "ACME.com.",
        "  acme.com  ",
        "www.acme.com",
        "http://acme.com:8080/x?y=1#z",
        "https://user:pass@acme.com/",
        "@WWW.Acme.Com.",
    ],
)
def test_a_company_domain_is_normalised(value: str) -> None:
    assert parse(company_domains=[value]).company_domains == ("acme.com",)


def test_a_subdomain_is_kept() -> None:
    assert parse(company_domains=["mail.acme.co.uk"]).company_domains == (
        "mail.acme.co.uk",
    )


def test_duplicate_domains_are_dropped_keeping_the_order() -> None:
    domains = ["b.com", "https://www.a.com", "B.COM", "a.com", "c.io"]
    assert parse(company_domains=domains).company_domains == ("b.com", "a.com", "c.io")


def test_empty_domain_entries_are_skipped() -> None:
    assert parse(company_domains=["", "  ", "acme.com"]).company_domains == (
        "acme.com",
    )


@pytest.mark.parametrize(
    "value", ["acme", "not a domain", "https://", "acme..com", "-acme.com", "a@b.com"]
)
def test_a_bad_domain_is_refused_with_the_value(value: str) -> None:
    assert problems(company_domains=[value]) == [
        ("company_domains", f"Некоректний домен компанії: {value.strip()}.")
    ]


def test_ten_domains_are_allowed() -> None:
    domains = [f"c{n}.com" for n in range(MAX_CONTACTS)]
    assert len(parse(company_domains=domains).company_domains) == MAX_CONTACTS


def test_eleven_domains_are_refused() -> None:
    domains = [f"c{n}.com" for n in range(MAX_CONTACTS + 1)]
    assert problems(company_domains=domains) == [
        ("company_domains", "Не більше 10 доменів компанії.")
    ]


def test_duplicates_do_not_count_towards_the_domain_limit() -> None:
    domains = [f"c{n}.com" for n in range(MAX_CONTACTS)] * 2
    assert len(parse(company_domains=domains).company_domains) == MAX_CONTACTS


# --- адреси компанії ---


def test_an_address_is_lowercased_and_trimmed() -> None:
    assert parse(company_emails=["  Jane.Doe@Acme.COM "]).company_emails == (
        "jane.doe@acme.com",
    )


def test_duplicate_addresses_are_dropped_keeping_the_order() -> None:
    emails = ["b@x.com", "a@x.com", "B@X.com"]
    assert parse(company_emails=emails).company_emails == ("b@x.com", "a@x.com")


def test_empty_address_entries_are_skipped() -> None:
    assert parse(company_emails=[" ", "a@x.com"]).company_emails == ("a@x.com",)


@pytest.mark.parametrize(
    "value", ["jane", "jane@", "@acme.com", "jane@acme", "jane @acme.com", "a@@b.com"]
)
def test_a_bad_address_is_refused_with_the_value(value: str) -> None:
    assert problems(company_emails=[value]) == [
        ("company_emails", f"Некоректна адреса компанії: {value.strip()}.")
    ]


def test_eleven_addresses_are_refused() -> None:
    emails = [f"r{n}@acme.com" for n in range(MAX_CONTACTS + 1)]
    assert problems(company_emails=emails) == [
        ("company_emails", "Не більше 10 адрес компанії.")
    ]


def test_all_the_problems_of_a_form_come_together() -> None:
    assert problems(
        applied_on="soon", channel="phone", ats="x", company_domains=["no"]
    ) == [
        ("applied_on", "Дата подачі — у форматі YYYY-MM-DD."),
        ("channel", "Канал — один з: email, ats, linkedin, referral."),
        (
            "ats",
            "ATS — один з: greenhouse, lever, ashby, workable, smartrecruiters, other.",
        ),
        ("company_domains", "Некоректний домен компанії: no."),
    ]


def test_a_full_form_is_parsed_into_details() -> None:
    assert parse(
        applied_on="2026-02-20",
        channel="ats",
        ats="lever",
        company_domains=["https://www.acme.com", "jobs.acme.com"],
        company_emails=["HR@acme.com"],
    ) == NewApplication(
        applied_on=date(2026, 2, 20),
        channel=ApplicationChannel.ATS,
        ats=AtsPlatform.LEVER,
        company_domains=("acme.com", "jobs.acme.com"),
        company_emails=("hr@acme.com",),
    )
