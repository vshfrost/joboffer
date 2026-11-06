"""Зіставлення листа компанії з подачами й підказка типу (правила з v1): пріоритет ознак —
тред, адреса, домен, ATS-відправник з назвою компанії, лише назва."""

from datetime import UTC, datetime

import pytest

from domain.applications.application import ApplicationStatus, AtsPlatform
from domain.mail.replies import (
    DEFAULT_REPLIES_LIMIT,
    MAX_REPLIES_LIMIT,
    AppliedJob,
    Confidence,
    MatchedBy,
    ReplyMail,
    ReplyMatch,
    ReplyType,
    ats_platform,
    check_replies_limit,
    match_reply,
    parse_reply_type,
    suggest_type,
)
from domain.shared.errors import InvalidValue

NOW = datetime(2026, 10, 15, 14, tzinfo=UTC)
APPLIED = ApplicationStatus.APPLIED


def reply(
    sender: str,
    subject: str = "",
    text: str = "",
    name: str = "",
    in_reply_to: str = "",
) -> ReplyMail:
    return ReplyMail(
        id=1,
        received_at=NOW,
        from_address=sender,
        from_name=name,
        subject=subject,
        text=text,
        in_reply_to=in_reply_to,
    )


def test_a_reply_in_the_thread_of_an_applied_job_matches_it_with_high_confidence() -> (
    None
):
    jobs = (
        AppliedJob(1, "Backend", "Acme", APPLIED),
        AppliedJob(2, "Data", "Bolt", APPLIED),
    )

    found = match_reply(reply("someone@gmail.com", in_reply_to="<a@b>"), jobs, 2)

    assert found == ReplyMatch(2, Confidence.HIGH, MatchedBy.THREAD)


def test_a_thread_job_that_is_not_an_application_is_ignored() -> None:
    jobs = (AppliedJob(1, "Backend", "Acme", APPLIED),)

    assert match_reply(reply("news@startupjobs.example", "25 roles"), jobs, 99) == (
        ReplyMatch()
    )


def test_the_thread_beats_the_company_address_and_domain() -> None:
    thread = AppliedJob(1, "Backend", "Zeta", APPLIED)
    by_domain = AppliedJob(2, "Backend", "Acme", APPLIED, None, ("acme.com",))

    found = match_reply(reply("hr@acme.com"), (thread, by_domain), 1)

    assert found == ReplyMatch(1, Confidence.HIGH, MatchedBy.THREAD)


def test_a_known_company_address_beats_the_domain() -> None:
    first = AppliedJob(10, "Backend", "Acme", APPLIED, None, ("acme.com",))
    second = AppliedJob(
        11, "Platform", "Acme", APPLIED, None, ("acme.com",), ("ana@acme.com",)
    )

    found = match_reply(reply("ana@acme.com"), (first, second), None)

    assert found == ReplyMatch(11, Confidence.HIGH, MatchedBy.EMAIL)


def test_the_company_domain_or_its_subdomain_matches_but_a_lookalike_does_not() -> None:
    job = AppliedJob(10, "Backend", "Acme", APPLIED, None, ("acme.com",))

    exact = match_reply(reply("jobs@acme.com"), (job,), None)
    subdomain = match_reply(reply("jobs@eu.acme.com"), (job,), None)
    lookalike = match_reply(reply("jobs@notacme.com"), (job,), None)

    assert exact == ReplyMatch(10, Confidence.HIGH, MatchedBy.DOMAIN)
    assert subdomain == ReplyMatch(10, Confidence.HIGH, MatchedBy.DOMAIN)
    assert lookalike == ReplyMatch()


@pytest.mark.parametrize(
    ("sender", "platform"),
    [
        ("no-reply@us.greenhouse-mail.io", AtsPlatform.GREENHOUSE),
        ("no-reply@greenhouse.io", AtsPlatform.GREENHOUSE),
        ("no-reply@hire.lever.co", AtsPlatform.LEVER),
        ("no-reply@ashbyhq.com", AtsPlatform.ASHBY),
        ("noreply@candidates.workablemail.com", AtsPlatform.WORKABLE),
        ("noreply@workable.com", AtsPlatform.WORKABLE),
        ("noreply@smartrecruiters.com", AtsPlatform.SMARTRECRUITERS),
    ],
)
def test_an_ats_sender_with_the_company_name_and_the_same_ats_matches(
    sender: str, platform: AtsPlatform
) -> None:
    job = AppliedJob(30, "Backend", "Bolt", APPLIED, platform)

    found = match_reply(reply(sender, "Your application to Bolt"), (job,), None)

    assert found == ReplyMatch(30, Confidence.HIGH, MatchedBy.ATS)


def test_an_ats_sender_without_the_company_name_matches_nothing() -> None:
    job = AppliedJob(30, "Backend", "Bolt", APPLIED, AtsPlatform.LEVER)

    assert match_reply(reply("no-reply@hire.lever.co", "Hi"), (job,), None) == (
        ReplyMatch()
    )


def test_an_ats_sender_of_another_platform_falls_back_to_the_name_with_low_confidence() -> (
    None
):
    other_ats = AppliedJob(31, "Backend", "Bolt", APPLIED, AtsPlatform.ASHBY)
    no_ats = AppliedJob(32, "Backend", "Bolt", APPLIED)

    found = match_reply(
        reply("no-reply@hire.lever.co", "Your application to Bolt"),
        (other_ats, no_ats),
        None,
    )

    assert found == ReplyMatch(31, Confidence.LOW, MatchedBy.NAME)


def test_the_company_name_alone_is_low_confidence_and_ignores_the_legal_form() -> None:
    job = AppliedJob(40, "Backend", "Typeform S.L.", APPLIED)

    found = match_reply(
        reply("agency@talent.example", "A role at Typeform"), (job,), None
    )

    assert found == ReplyMatch(40, Confidence.LOW, MatchedBy.NAME)


def test_the_company_name_must_be_a_whole_word() -> None:
    job = AppliedJob(40, "Backend", "Bolt", APPLIED)

    found = match_reply(reply("x@talent.example", "Thunderbolt news"), (job,), None)

    assert found == ReplyMatch()


def test_the_company_name_is_found_in_the_sender_name_and_the_text() -> None:
    job = AppliedJob(40, "Backend", "Bolt", APPLIED)

    by_name = match_reply(reply("a@x.example", name="Bolt Talent"), (job,), None)
    by_text = match_reply(
        reply("a@x.example", text="We at Bolt liked it"), (job,), None
    )

    assert by_name == ReplyMatch(40, Confidence.LOW, MatchedBy.NAME)
    assert by_text == ReplyMatch(40, Confidence.LOW, MatchedBy.NAME)


def test_a_name_match_picks_the_job_whose_title_the_mail_mentions() -> None:
    jobs = (
        AppliedJob(40, "Backend", "Bolt", APPLIED),
        AppliedJob(41, "Data Engineer", "Bolt", APPLIED),
    )

    found = match_reply(
        reply("agency@talent.example", "Data Engineer role at Bolt"), jobs, None
    )

    assert found == ReplyMatch(41, Confidence.LOW, MatchedBy.NAME)


def test_a_job_without_a_company_name_is_never_matched_by_name() -> None:
    job = AppliedJob(42, "Backend", None, APPLIED)

    assert match_reply(reply("a@x.example", "Backend role"), (job,), None) == (
        ReplyMatch()
    )


def test_the_title_in_the_subject_tells_apart_applications_at_one_company() -> None:
    newer = AppliedJob(20, "Staff Engineer", "Acme", APPLIED, None, ("acme.com",))
    older = AppliedJob(
        21, "Senior Backend Engineer (Python)", "Acme", APPLIED, None, ("acme.com",)
    )

    found = match_reply(
        reply("hr@acme.com", "Your Senior  backend engineer application"),
        (newer, older),
        None,
    )

    assert found == ReplyMatch(21, Confidence.MEDIUM, MatchedBy.DOMAIN)


def test_without_a_title_the_newest_application_is_picked_with_low_confidence() -> None:
    newer = AppliedJob(20, "Staff Engineer", "Acme", APPLIED, None, ("acme.com",))
    older = AppliedJob(
        21, "Senior Backend Engineer", "Acme", APPLIED, None, ("acme.com",)
    )

    found = match_reply(reply("hr@acme.com", "Your application"), (newer, older), None)

    assert found == ReplyMatch(20, Confidence.LOW, MatchedBy.DOMAIN)


def test_two_titles_in_one_mail_do_not_tell_applications_apart() -> None:
    newer = AppliedJob(20, "Staff Engineer", "Acme", APPLIED, None, ("acme.com",))
    older = AppliedJob(
        21, "Senior Backend Engineer", "Acme", APPLIED, None, ("acme.com",)
    )

    found = match_reply(
        reply("hr@acme.com", text="Staff Engineer or Senior Backend Engineer?"),
        (newer, older),
        None,
    )

    assert found == ReplyMatch(20, Confidence.LOW, MatchedBy.DOMAIN)


def test_a_mail_that_is_not_about_any_application_matches_nothing() -> None:
    jobs = (AppliedJob(1, "Backend", "Acme", APPLIED, None, ("acme.com",)),)

    found = match_reply(
        reply("newsletter@startupjobs.example", "25 new roles"), jobs, None
    )

    assert found == ReplyMatch()
    assert found.job_number is None


def test_ats_platform_by_sender_domain() -> None:
    assert ats_platform("us.greenhouse-mail.io") is AtsPlatform.GREENHOUSE
    assert ats_platform("candidates.workablemail.com") is AtsPlatform.WORKABLE
    assert ats_platform("acme.com") is None


@pytest.mark.parametrize(
    ("subject", "text", "kind"),
    [
        ("", "Thank you for your application. Unfortunately…", ReplyType.REJECTION),
        ("", "We regret to inform you that…", ReplyType.REJECTION),
        (
            "",
            "We have decided to move forward with other candidates",
            ReplyType.REJECTION,
        ),
        ("Gracias por tu candidatura", "Lamentablemente…", ReplyType.REJECTION),
        (
            "",
            "Hemos decidido seguir adelante con otros candidatos",
            ReplyType.REJECTION,
        ),
        ("", "Could you share your availability?", ReplyType.INVITATION),
        (
            "",
            "Thanks for applying! Could you share your availability?",
            ReplyType.INVITATION,
        ),
        ("", "Book some time: https://calendly.com/x/intro", ReplyType.INVITATION),
        (
            "",
            "Gracias por tu candidatura. ¿Podemos agendar una llamada?",
            ReplyType.INVITATION,
        ),
        ("Prueba técnica", "Hola", ReplyType.ASSIGNMENT),
        ("", "Please complete this take-home coding challenge", ReplyType.ASSIGNMENT),
        ("", "You will receive a HackerRank invitation", ReplyType.ASSIGNMENT),
        ("", "Hemos recibido tu candidatura.", ReplyType.AUTO_CONFIRMATION),
        ("Thank you for applying to Acme", "", ReplyType.AUTO_CONFIRMATION),
        ("", "Your application has been received", ReplyType.AUTO_CONFIRMATION),
        ("Quick question", "What is your notice period?", ReplyType.OTHER),
        ("", "", ReplyType.OTHER),
    ],
)
def test_the_type_hint_follows_english_and_spanish_keywords(
    subject: str, text: str, kind: ReplyType
) -> None:
    assert suggest_type(subject, text) is kind


def test_a_rejection_that_thanks_for_applying_is_a_rejection() -> None:
    text = "Thanks for applying to Acme.\n\nUnfortunately, we are not moving forward."

    assert suggest_type("", text) is ReplyType.REJECTION


def test_the_quoted_text_is_ignored_by_the_type_hint() -> None:
    text = "Sorry, the link expired, here is a new one.\n> Thanks for applying for the role."

    assert suggest_type("Re: Next steps", text) is ReplyType.OTHER
    assert (
        suggest_type("", "> Unfortunately, no.\n  > Hola\nAll fine") is ReplyType.OTHER
    )


def test_the_type_hint_reads_the_subject_too() -> None:
    assert suggest_type("Unfortunately, not this time", "Hi") is ReplyType.REJECTION


def test_the_reply_type_is_parsed_and_an_unknown_one_lists_the_allowed() -> None:
    assert parse_reply_type(" rejection ") is ReplyType.REJECTION
    with pytest.raises(InvalidValue) as error:
        parse_reply_type("ghosted")
    assert error.value.field == "type"
    assert error.value.message == (
        "Тип відповіді — один з: auto_confirmation, rejection, invitation, "
        "assignment, other."
    )


def test_the_limit_is_between_1_and_50() -> None:
    assert (DEFAULT_REPLIES_LIMIT, MAX_REPLIES_LIMIT) == (10, 50)
    check_replies_limit(1)
    check_replies_limit(50)
    for limit in (0, 51, -1):
        with pytest.raises(InvalidValue) as error:
            check_replies_limit(limit)
        assert error.value.field == "limit"
        assert error.value.message == "limit — від 1 до 50."
