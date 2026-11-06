"""Розбір листів-алертів LinkedIn: знеособлені справжні дайджести (Madrid, Barcelona, Spain — по 6
вакансій) і синтетичні варіанти структури, яких справжніх зразків ще нема. Лист — недовірені дані."""

import pytest

from domain.jobs.linkedin import AlertJob, AlertParse, parse_job_alert
from tests.support import linkedin_alerts

ALERTS = {
    "spain": linkedin_alerts.SPAIN,
    "madrid": linkedin_alerts.MADRID,
    "barcelona": linkedin_alerts.BARCELONA,
}


def alert_text(name: str) -> str:
    return ALERTS[name]


def test_real_alert_gives_every_job_with_title_company_location_and_id() -> None:
    parsed = parse_job_alert(alert_text("spain"))

    assert parsed.unparsed == 0
    assert parsed.error == ""
    assert [(j.linkedin_id, j.title, j.company, j.location) for j in parsed.jobs] == [
        (
            "4442068661",
            "Senior Software Engineer, Back-end (Fraud)",
            "Affirm",
            "Spain",
        ),
        (
            "4477515440",
            "Senior PHP/Laravel Developer with Infrastructure & DevOps Experience",
            "Jobgether",
            "Spain",
        ),
        (
            "4478800417",
            "Senior Backend Engineer – Payments & Ledger Systems",
            "MaxIT Consulting - Max Corporate Group",
            "Madrid, Community of Madrid, Spain",
        ),
        ("4478867393", "Senior Python Developer", "Jobgether", "Spain"),
        ("4479368859", "Backend Engineer (Python)", "Gather Health", "Spain"),
        (
            "4467600540",
            "Senior Software Engineer (Privacy) (x/f/m) - Tech Foundations",
            "Alan",
            "Spain",
        ),
    ]


@pytest.mark.parametrize(
    ("name", "count"), [("spain", 6), ("madrid", 6), ("barcelona", 6)]
)
def test_every_real_alert_is_parsed_whole(name: str, count: int) -> None:
    parsed = parse_job_alert(alert_text(name))

    assert (len(parsed.jobs), parsed.unparsed) == (count, 0)
    assert all(job.title and job.company and job.location for job in parsed.jobs)
    assert len({job.linkedin_id for job in parsed.jobs}) == count


def test_madrid_alert_starts_with_the_first_job_of_the_mail() -> None:
    jobs = parse_job_alert(alert_text("madrid")).jobs

    assert jobs[:1] == (
        AlertJob(
            "4479505470",
            "Senior API Engineer",
            "Ebury",
            "Madrid, Community of Madrid, Spain",
        ),
    )


def test_the_same_job_can_come_in_two_alerts() -> None:
    spain = {job.linkedin_id for job in parse_job_alert(alert_text("spain")).jobs}
    madrid = {job.linkedin_id for job in parse_job_alert(alert_text("madrid")).jobs}

    assert spain & madrid == {"4442068661"}


def test_job_link_is_canonical_without_tracking() -> None:
    job = AlertJob("4442068661", "Title", "Company", "Spain")

    assert job.url == "https://www.linkedin.com/jobs/view/4442068661"


def block(*lines: str) -> str:
    return "\n".join(lines)


SEPARATOR = "-" * 40
LINK = "Переглянути вакансію: https://www.linkedin.com/comm/jobs/view/{id}?trackingId=x"


def digest(*blocks: str, header: str = "Нові вакансії для вас:\nОсь добірка.") -> str:
    return "\n\n".join([header, *[f"{b}\n\n{SEPARATOR}" for b in blocks]])


def test_job_in_one_paragraph_with_notes_before_the_link() -> None:
    text = digest(
        block(
            "Senior Python Developer",
            "Jobgether",
            "Spain",
            "Подати заявку за допомогою резюме і профілю",
            LINK.format(id="4478867393"),
        )
    )

    assert parse_job_alert(text) == AlertParse(
        (AlertJob("4478867393", "Senior Python Developer", "Jobgether", "Spain"),)
    )


def test_job_whose_notes_and_link_are_in_the_next_paragraph() -> None:
    text = digest(
        block("Senior API Engineer", "Ebury", "Madrid")
        + "\n\n"
        + block("1 колишній співробітник компанії", LINK.format(id="4479505470"))
    )

    assert parse_job_alert(text).jobs == (
        AlertJob("4479505470", "Senior API Engineer", "Ebury", "Madrid"),
    )


def test_first_three_lines_of_a_block_are_title_company_and_location() -> None:
    header = "Рядок 1\nРядок 2\nРядок 3"
    one = block("Title A", "Company A", "City A", LINK.format(id="4400000001"))
    two = (
        block("Title B", "Company B", "City B")
        + "\n\n"
        + block(LINK.format(id="4400000002"))
    )

    assert [j.title for j in parse_job_alert(digest(one, two, header=header)).jobs] == [
        "Title A",
        "Title B",
    ]


def test_blank_looking_lines_with_spaces_still_separate_paragraphs() -> None:
    text = (
        "Intro\n   \n"
        "Title\nCompany\nCity\nПодати заявку\n"
        + LINK.format(id="4400000013")
        + f"\n\n{SEPARATOR}\n  \n          \n"
        "Next\nCompany 2\nCity 2\n" + LINK.format(id="4400000014")
    )

    assert [j.title for j in parse_job_alert(text).jobs] == ["Title", "Next"]


def test_extra_spaces_are_collapsed_and_fields_over_300_chars_are_truncated() -> None:
    long = "x" * 400
    text = digest(
        block(
            "  Backend   Engineer ", long, "  Valencia ", LINK.format(id="4400000003")
        )
    )

    jobs = parse_job_alert(text).jobs

    assert [(j.title, j.company, j.location) for j in jobs] == [
        ("Backend Engineer", "x" * 300, "Valencia")
    ]


def test_repeated_id_in_one_mail_is_one_job() -> None:
    one = block("Title", "Company", "City", LINK.format(id="4400000004"))

    assert len(parse_job_alert(digest(one, one)).jobs) == 1


def test_titles_are_kept_as_text_not_markup() -> None:
    one = block(
        "<b>Dev</b> <script>x</script>", "A & B", "City", LINK.format(id="4400000005")
    )

    jobs = parse_job_alert(digest(one)).jobs

    assert [(j.title, j.company) for j in jobs] == [
        ("<b>Dev</b> <script>x</script>", "A & B")
    ]


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Привіт! Тут нема жодної вакансії.",
        "Footer only\n\nhttps://www.linkedin.com/jobs/search-results/",
    ],
)
def test_mail_without_job_links_is_an_unknown_template(text: str) -> None:
    parsed = parse_job_alert(text)

    assert parsed == AlertParse()
    assert parsed.error == "linkedin_alert: вакансій не знайдено (невідомий шаблон)"


def test_blocks_that_do_not_fit_the_layout_are_counted_not_fatal() -> None:
    good = block("Good Title", "Good Co", "Valencia", LINK.format(id="4400000006"))
    bare = block(LINK.format(id="4400000007"))
    two_links = block(
        "Title",
        "Company",
        "City",
        LINK.format(id="4400000008"),
        LINK.format(id="4400000009"),
    )
    link_as_title = block(LINK.format(id="4400000010"), "Company", "City", "Note")

    parsed = parse_job_alert(digest(good, bare, two_links, link_as_title))

    assert [j.linkedin_id for j in parsed.jobs] == ["4400000006"]
    assert parsed.unparsed == 3
    assert parsed.error == "linkedin_alert: не розібрано блоків вакансій — 3"


def test_parse_is_independent_of_the_language_of_the_notes() -> None:
    english = block(
        "Backend Engineer",
        "Acme",
        "Madrid, Spain",
        "Easy Apply",
        "View job: https://www.linkedin.com/comm/jobs/view/4400000011?trk=x",
    )
    spanish = block(
        "Ingeniero Backend",
        "Acme",
        "Valencia, España",
        "Solicitud sencilla",
        "Ver empleo: https://www.linkedin.com/comm/jobs/view/4400000012?trk=x",
    )

    assert [j.title for j in parse_job_alert(digest(english, spanish)).jobs] == [
        "Backend Engineer",
        "Ingeniero Backend",
    ]


def test_digest_header_in_the_job_paragraph_is_not_the_title() -> None:
    parsed = parse_job_alert(linkedin_alerts.HEADER_FIRST)

    assert parsed == AlertParse(
        (
            AlertJob(
                "4484270937",
                "Software Developer (Python / AWS)",
                "3MT GALICIA GLOBAL SERVICES, S. L.",
                "Valencia",
            ),
        )
    )


def test_digest_header_before_a_job_with_a_note_keeps_the_note_out_of_the_fields() -> (
    None
):
    text = "Сповіщення про вакансії за запитом python в Madrid\n" + block(
        "Senior Python Developer",
        "Jobgether",
        "Spain",
        "Подати заявку за допомогою резюме і профілю",
        LINK.format(id="4478867393"),
    )

    assert parse_job_alert(text).jobs == (
        AlertJob("4478867393", "Senior Python Developer", "Jobgether", "Spain"),
    )
