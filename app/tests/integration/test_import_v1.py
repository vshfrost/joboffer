"""`python -m bootstrap.import_v1`: перенос усіх даних одного користувача з БД v1 у v2.

Дві справжні бази Postgres на одному сервері: v1 зі схемою 99a2007 (фікстура SQL) і v2 до head.
Імпорт запускається через CLI, результат читається прямим SQL і через репозиторії v2.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import anyio
import psycopg
import pytest
from anyio.from_thread import BlockingPortal
from psycopg.types.json import Jsonb
from sqlalchemy.exc import IntegrityError

from bootstrap.import_v1 import main
from domain.documents.document import DocumentKind
from domain.facts.fact import FactKind, NewFact
from domain.facts.ids import FactId
from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.jobs.job import NewJob
from domain.prep.kit import KitQuestionKind
from infrastructure.db.engine import create_engine
from infrastructure.db.migrate import upgrade
from infrastructure.db.unit_of_work import unit_of_work_factory
from tests.support.import_v1 import (
    FACT_TEXTS,
    NOT_IMPORTED,
    T0,
    T1,
    T2,
    TABLE_PAIRS,
    V1_DB,
    V2_DB,
    connect,
    count,
    create_database,
    create_v1_schema,
    drop_database,
    rows,
    seed_v1,
    seed_v2,
    snapshot,
    v2_user,
    wipe,
    with_database,
)

Conn = psycopg.Connection[dict[str, Any]]


@dataclass(frozen=True)
class World:
    v1: Conn
    v2: Conn
    user: UUID
    v2_url: str
    documents_dir: Path
    pdf_dir: Path

    def run(self, *args: str, source_db: str = V1_DB) -> int:
        return main(["--source-db", source_db, *args])

    def apply(self, *args: str) -> int:
        return self.run("--apply", *args)

    def job_id(self, number: int) -> UUID:
        found = rows(
            self.v2,
            "SELECT id FROM jobs WHERE user_id = %s AND job_number = %s",
            self.user,
            number,
        )
        return UUID(str(found[0]["id"]))

    def write_pdf(self, v1_id: int, body: bytes) -> None:
        self.pdf_dir.mkdir(exist_ok=True)
        (self.pdf_dir / f"{v1_id}.pdf").write_bytes(body)


@pytest.fixture(scope="module")
def databases(database_url: str) -> Iterator[tuple[str, str]]:
    """Дві окремі бази на сервері тесту: v1 зі схемою з фікстури, v2 до head."""
    admin = connect(database_url)
    create_database(admin, V1_DB)
    create_database(admin, V2_DB)
    v1_url = with_database(database_url, V1_DB)
    v2_url = with_database(database_url, V2_DB)
    with connect(v1_url) as v1:
        create_v1_schema(v1)

    async def migrate() -> None:
        engine = create_engine(v2_url.replace("postgresql://", "postgresql+psycopg://"))
        try:
            await upgrade(engine)
        finally:
            await engine.dispose()

    anyio.run(migrate)
    yield v1_url, v2_url
    drop_database(admin, V1_DB)
    drop_database(admin, V2_DB)
    admin.close()


@pytest.fixture
def world(
    databases: tuple[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[World]:
    v1_url, v2_url = databases
    documents_dir = tmp_path / "documents"
    monkeypatch.setenv(
        "JOBOFFER_DATABASE_URL",
        v2_url.replace("postgresql://", "postgresql+psycopg://"),
    )
    monkeypatch.setenv("JOBOFFER_DOCUMENTS_DIR", str(documents_dir))
    with connect(v1_url) as v1, connect(v2_url) as v2:
        wipe(v1, skip=("alembic_version",))
        wipe(v2, skip=("alembic_version",))
        seed_v1(v1)
        user = seed_v2(v2)
        yield World(v1, v2, user, v2_url, documents_dir, tmp_path / "v1-pdfs")


def v2_rows(world: World, table: str, order: str) -> list[dict[str, Any]]:
    return rows(
        world.v2,
        f"SELECT * FROM {table} WHERE user_id = %s ORDER BY {order}",  # noqa: S608
        world.user,
    )


# 1. Кількість рядків --------------------------------------------------------------------


# profiles і mail_inboxes тут не рахуються: у v2 вони вже існували, їхні значення — окремі тести.
@pytest.mark.parametrize(("v1_table", "v2_table"), sorted(TABLE_PAIRS.items()))
def test_every_table_gets_as_many_rows_as_v1_has(
    world: World, v1_table: str, v2_table: str
) -> None:
    expected = count(world.v1, v1_table)
    assert expected > 0

    assert world.apply() == 0

    assert count(world.v2, v2_table) == expected


# 2. Номери й лічильники ------------------------------------------------------------------

NUMBER_COLUMNS = [
    ("jobs", "job_number", {3, 5, 8}),
    ("facts", "fact_number", {2, 4, 7, 9}),
    ("photos", "photo_number", {6}),
    ("documents", "document_number", {10, 11, 15}),
    ("interview_kits", "kit_number", {4}),
    ("prep_topics", "topic_number", {12, 13}),
    ("prep_steps", "step_number", {20, 21, 25}),
    ("prep_questions", "question_number", {30, 31}),
]


@pytest.mark.parametrize(("table", "column", "v1_ids"), NUMBER_COLUMNS)
def test_number_in_v2_is_the_v1_id(
    world: World, table: str, column: str, v1_ids: set[int]
) -> None:
    world.apply()

    found = rows(world.v2, f"SELECT {column} AS n FROM {table}")  # noqa: S608
    assert {row["n"] for row in found} == v1_ids


@pytest.mark.parametrize(
    ("counter", "last"),
    [
        ("job_counters", 8),
        ("fact_counters", 9),
        ("photo_counters", 6),
        ("document_counters", 15),
        ("interview_kit_counters", 4),
        ("prep_topic_counters", 13),
        ("prep_step_counters", 25),
        ("prep_question_counters", 31),
    ],
)
def test_counter_holds_the_largest_imported_number(
    world: World, counter: str, last: int
) -> None:
    world.apply()

    found = rows(world.v2, f"SELECT last_number FROM {counter}")  # noqa: S608
    assert found == [{"last_number": last}]


def test_new_job_and_fact_after_the_import_get_the_next_number(
    world: World, portal: BlockingPortal
) -> None:
    world.apply()
    engine = create_engine(
        world.v2_url.replace("postgresql://", "postgresql+psycopg://")
    )

    async def add() -> tuple[int, int]:
        factory = unit_of_work_factory(engine)
        async with factory() as tx:
            job = await tx.jobs.add(
                UserId(world.user),
                JobId(uuid4()),
                NewJob(
                    text="A brand new posting",
                    url=None,
                    title=None,
                    company=None,
                    linkedin_id=None,
                    location=None,
                ),
                T2,
            )
            fact = await tx.facts.add(
                UserId(world.user),
                FactId(uuid4()),
                NewFact(FactKind.SKILL, "Rust"),
                T2,
            )
            await tx.commit()
        await engine.dispose()
        return job, fact.number

    assert portal.call(add) == (9, 10)


# 3. fact_ids -----------------------------------------------------------------------------


def v2_fact_texts(world: World) -> dict[int, str]:
    found = rows(
        world.v2, "SELECT fact_number, text FROM facts WHERE user_id = %s", world.user
    )
    return {row["fact_number"]: row["text"] for row in found}


def test_cv_claims_point_at_the_same_fact_texts_as_in_v1(world: World) -> None:
    world.apply()

    cv = rows(world.v2, "SELECT content FROM documents WHERE document_number = 10")[0][
        "content"
    ]
    facts = v2_fact_texts(world)
    assert [facts[n] for n in cv["headline"]["fact_ids"]] == [FACT_TEXTS[2]]
    assert [facts[n] for n in cv["summary"]["fact_ids"]] == [FACT_TEXTS[4]]
    bullet = cv["sections"][0]["entries"][0]["bullets"][0]
    assert [facts[n] for n in bullet["fact_ids"]] == [FACT_TEXTS[7]]


def test_cover_letter_points_at_the_same_fact_texts_as_in_v1(world: World) -> None:
    world.apply()

    letter = rows(world.v2, "SELECT content FROM documents WHERE document_number = 11")[
        0
    ]["content"]
    facts = v2_fact_texts(world)
    assert [facts[n] for n in letter["fact_ids"]] == [FACT_TEXTS[2], FACT_TEXTS[7]]


def test_interview_story_points_at_the_same_fact_texts_as_in_v1(world: World) -> None:
    world.apply()

    kit = rows(world.v2, "SELECT content FROM interview_kits")[0]["content"]
    facts = v2_fact_texts(world)
    story = kit["stories"][0]
    assert [facts[n] for n in story["fact_ids"]] == [FACT_TEXTS[2], FACT_TEXTS[7]]
    assert kit["questions"][0]["topic_id"] == 12


def test_fact_hashes_are_carried_over(world: World) -> None:
    world.apply()

    v1 = rows(world.v1, "SELECT id, text_hash FROM facts")
    v2 = rows(world.v2, "SELECT fact_number, text_hash FROM facts")
    assert {row["id"]: row["text_hash"] for row in v1} == {
        row["fact_number"]: row["text_hash"] for row in v2
    }


# 4. Читання через репозиторії v2 -----------------------------------------------------------


def test_imported_documents_and_kit_load_through_the_v2_repositories(
    world: World, portal: BlockingPortal
) -> None:
    world.apply()
    engine = create_engine(
        world.v2_url.replace("postgresql://", "postgresql+psycopg://")
    )

    async def load() -> tuple[Any, ...]:
        factory = unit_of_work_factory(engine)
        user = UserId(world.user)
        async with factory() as tx:
            cv = await tx.documents.get(user, 10)
            letter = await tx.documents.get(user, 11)
            newer = await tx.documents.get(user, 15)
            kit = await tx.interview_kits.latest(user, JobId(world.job_id(3)))
            topic = await tx.prep_topics.get(user, 12)
        await engine.dispose()
        return cv, letter, newer, kit, topic

    cv, letter, newer, kit, topic = portal.call(load)

    assert (cv.kind, cv.version, cv.job_number, cv.photo_number) == (
        DocumentKind.CV,
        1,
        3,
        6,
    )
    assert cv.lint is not None
    assert cv.lint.pages == 1
    assert (letter.kind, letter.version) == (DocumentKind.COVER_LETTER, 1)
    assert (newer.kind, newer.version) == (DocumentKind.CV, 2)
    assert kit.number == 4
    assert kit.kit.questions[0].kind is KitQuestionKind.TECHNICAL
    assert kit.kit.stories[0].fact_ids == (2, 7)
    assert topic.slug == "sql"


# 5. PDF ------------------------------------------------------------------------------------


def test_present_pdfs_are_copied_under_the_new_document_uuid(world: World) -> None:
    world.write_pdf(10, b"%PDF-1.7 ten")
    world.write_pdf(11, b"%PDF-1.7 eleven")

    assert world.apply("--pdf-dir", str(world.pdf_dir)) == 0

    ids = {
        row["document_number"]: row["id"]
        for row in rows(world.v2, "SELECT id, document_number FROM documents")
    }
    assert (world.documents_dir / f"{ids[10]}.pdf").read_bytes() == b"%PDF-1.7 ten"
    assert (world.documents_dir / f"{ids[11]}.pdf").read_bytes() == b"%PDF-1.7 eleven"


def test_missing_pdf_is_reported_and_the_import_still_succeeds(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    world.write_pdf(10, b"%PDF-1.7 ten")
    world.write_pdf(11, b"%PDF-1.7 eleven")
    world.write_pdf(99, b"%PDF-1.7 stranger")

    assert world.apply("--pdf-dir", str(world.pdf_dir)) == 0

    assert "Немає PDF для документів: 15" in capsys.readouterr().out
    assert count(world.v2, "documents") == 3
    assert len(list(world.documents_dir.iterdir())) == 2


# 6. Профіль ----------------------------------------------------------------------------------


def test_profile_takes_the_v1_values(world: World) -> None:
    world.apply()

    profile = rows(world.v2, "SELECT * FROM profiles WHERE user_id = %s", world.user)
    assert len(profile) == 1
    assert {
        key: profile[0][key]
        for key in (
            "roles",
            "work_modes",
            "relocation",
            "seniority",
            "min_salary_eur",
            "stop_words",
            "full_name",
            "email",
            "phone",
            "linkedin_url",
            "city",
            "github_url",
            "work_authorization",
            "title_keywords",
            "title_exclude",
            "include_unknown_mode",
            "target_domains",
            "updated_at",
        )
    } == {
        "roles": ["backend", "platform"],
        "work_modes": ["remote", "hybrid"],
        "relocation": True,
        "seniority": ["senior", "lead"],
        "min_salary_eur": 70000,
        "stop_words": ["crypto"],
        "full_name": "Богдан Прикладенко",
        "email": "taras@v1.example",
        "phone": "+34 600 000 000",
        "linkedin_url": "https://linkedin.com/in/taras",
        "city": "Валенсія",
        "github_url": "https://github.com/taras",
        "work_authorization": "EU citizen",
        "title_keywords": ["python"],
        "title_exclude": ["junior"],
        "include_unknown_mode": False,
        "target_domains": ["fintech"],
        "updated_at": T2,
    }
    assert profile[0]["analysis_inputs_changed_at"] is None


def test_search_locations_replace_the_v2_ones(world: World) -> None:
    world.apply()

    found = v2_rows(world, "profile_locations", "position")
    assert [
        (row["position"], row["place"], row["aliases"], row["work_modes"])
        for row in found
    ] == [
        (0, "Madrid", ["Мадрид"], ["hybrid", "onsite"]),
        (1, "Remote EU", [], ["remote"]),
    ]


# 7. Скринька -----------------------------------------------------------------------------------


def test_inbox_tag_is_replaced_by_the_v1_tag(world: World) -> None:
    world.apply()

    inbox = v2_rows(world, "mail_inboxes", "tag")
    assert [(row["tag"], row["created_at"], row["rotated_at"]) for row in inbox] == [
        ("v1tag7k2", T0, T1)
    ]


def test_retired_tags_are_carried_over(world: World) -> None:
    world.apply()

    found = v2_rows(world, "mail_retired_tags", "tag")
    assert [(row["tag"], row["retired_at"]) for row in found] == [
        ("oldtag1", T0),
        ("oldtag2", T1),
    ]


# 8. Листи, відповіді, послідовності -----------------------------------------------------------------


def test_replies_point_at_the_same_mail_and_the_mapped_job(world: World) -> None:
    world.apply()

    found = v2_rows(world, "job_replies", "id")
    assert [
        (row["id"], row["mail_id"], row["job_id"], row["type"], row["reviewed_at"])
        for row in found
    ] == [
        (7, 101, world.job_id(3), "invitation", T2),
        (9, 205, None, None, None),
    ]
    assert found[0]["matched_by"] == "thread"
    mail = v2_rows(world, "mail_messages", "id")
    assert [(row["id"], row["gmail_id"], row["category"]) for row in mail] == [
        (100, "g100", "linkedin_alert"),
        (101, "g101", "company"),
        (205, "g205", "company"),
    ]
    assert mail[0]["attachments"] == [{"name": "a.pdf"}]
    assert mail[0]["reference_ids"] == ["<root@mail>"]


def test_dropped_mail_keeps_its_ids_and_gets_empty_sender_and_subject(
    world: World,
) -> None:
    world.apply()

    found = v2_rows(world, "mail_dropped", "id")
    assert [
        (row["id"], row["gmail_id"], row["reason"], row["from_address"], row["subject"])
        for row in found
    ] == [(4, "d4", "daily_limit", "", ""), (11, "d11", "retired_tag", "", "")]


def test_new_rows_after_the_import_do_not_collide_with_imported_ids(
    world: World,
) -> None:
    world.apply()
    x = world.v2.execute

    mail_id = x(
        "INSERT INTO mail_messages (user_id, gmail_id, received_at, category, attachments) "
        "VALUES (%s, 'g-new', %s, 'other', '[]') RETURNING id",
        (world.user, T2),
    ).fetchone()
    reply_id = x(
        "INSERT INTO job_replies (user_id, mail_id, suggested_type) "
        "VALUES (%s, %s, 'other') RETURNING id",
        (world.user, mail_id["id"] if mail_id else 0),
    ).fetchone()
    dropped_id = x(
        "INSERT INTO mail_dropped (user_id, gmail_id, reason, received_at) "
        "VALUES (%s, 'd-new', 'daily_limit', %s) RETURNING id",
        (world.user, T2),
    ).fetchone()
    request_id = x(
        "INSERT INTO mail_sync_requests (user_id, requested_at) VALUES (%s, %s) "
        "RETURNING id",
        (world.user, T2),
    ).fetchone()

    assert mail_id is not None
    assert reply_id is not None
    assert dropped_id is not None
    assert request_id is not None
    assert (mail_id["id"], reply_id["id"], dropped_id["id"]) == (206, 10, 12)
    assert request_id["id"] == 1


# 9. Стан синку -----------------------------------------------------------------------------------------


def test_sync_state_rows_are_copied_by_mailbox(world: World) -> None:
    world.apply()

    found = rows(world.v2, "SELECT * FROM mail_sync_state")
    assert [
        (
            row["mailbox"],
            row["history_id"],
            row["synced_at"],
            row["last_error"],
            row["failed_at"],
        )
        for row in found
    ] == [("mailroom@example.com", "9876", T2, "stale error", T1)]


# 10. Підготовка ---------------------------------------------------------------------------------------


def test_prep_topics_and_their_job_links_are_preserved(world: World) -> None:
    world.apply()

    topics = v2_rows(world, "prep_topics", "topic_number")
    assert [
        (
            row["topic_number"],
            row["slug"],
            row["title"],
            row["kind"],
            row["summary"],
            row["deadline"],
            row["ready_at"],
        )
        for row in topics
    ] == [
        (12, "sql", "SQL", "tech", "Window functions", date(2026, 11, 15), None),
        (13, "star", "STAR stories", "behavioral", "", None, T2),
    ]
    links = rows(
        world.v2,
        "SELECT t.topic_number, p.job_id, p.gap FROM prep_topic_jobs p "
        "JOIN prep_topics t ON t.id = p.topic_id ORDER BY t.topic_number",
    )
    assert [(row["topic_number"], row["job_id"], row["gap"]) for row in links] == [
        (12, world.job_id(3), "Window functions"),
        (13, world.job_id(3), "Stories with numbers"),
    ]


def test_prep_steps_keep_progress_and_notes(world: World) -> None:
    world.apply()

    steps = rows(
        world.v2,
        "SELECT s.step_number, s.position, s.kind, s.title, s.done_at, s.note, "
        "s.resources, s.minutes, t.topic_number FROM prep_steps s "
        "JOIN prep_topics t ON t.id = s.topic_id WHERE s.user_id = %s ORDER BY s.step_number",
        world.user,
    )
    assert [
        (
            row["step_number"],
            row["topic_number"],
            row["position"],
            row["kind"],
            row["title"],
            row["done_at"],
            row["note"],
            row["minutes"],
        )
        for row in steps
    ] == [
        (20, 12, 1, "learn", "Read docs", T2, "зробив", 30),
        (21, 12, 2, "practice", "Write queries", None, "", 45),
        (25, 13, 1, "check", "Tell a story", None, "", 20),
    ]
    assert steps[0]["resources"] == [
        {"title": "PG docs", "url": "https://www.postgresql.org/docs/"}
    ]


def test_prep_questions_keep_box_and_due_date_and_answers_keep_history(
    world: World,
) -> None:
    world.apply()

    questions = rows(
        world.v2,
        "SELECT question_number, question, answer_points, box, due_on FROM prep_questions "
        "WHERE user_id = %s ORDER BY question_number",
        world.user,
    )
    assert [
        (row["question_number"], row["answer_points"], row["box"], row["due_on"])
        for row in questions
    ] == [
        (30, ["OVER clause", "partition"], 3, date(2026, 11, 2)),
        (31, ["situation", "lesson"], 1, date(2026, 10, 31)),
    ]
    answers = rows(
        world.v2,
        "SELECT q.question_number, a.grade, a.answer, a.feedback, a.box, a.answered_at "
        "FROM prep_answers a JOIN prep_questions q ON q.id = a.question_id "
        "ORDER BY a.answered_at",
    )
    assert [
        (
            row["question_number"],
            row["grade"],
            row["answer"],
            row["feedback"],
            row["box"],
            row["answered_at"],
        )
        for row in answers
    ] == [
        (30, 2, "не знаю", "повтори", 1, T0),
        (30, 4, "OVER (...)", "добре", 3, T1),
        (31, 5, "історія", "супер", 1, T2),
    ]


# Решта вакансій і даних -----------------------------------------------------------------------------


def test_jobs_keep_all_v1_fields_including_dismissed_and_needs_text(
    world: World,
) -> None:
    world.apply()

    found = {row["job_number"]: row for row in v2_rows(world, "jobs", "job_number")}
    assert (found[3]["url"], found[3]["location"], found[3]["opened_at"]) == (
        "https://acme.example/jobs/3",
        "Madrid",
        T1,
    )
    assert found[3]["created_at"] == T0
    assert (
        found[3]["text_hash"]
        == rows(world.v1, "SELECT text_hash FROM jobs WHERE id = 3")[0]["text_hash"]
    )
    assert (found[5]["text"], found[5]["text_hash"], found[5]["linkedin_id"]) == (
        None,
        None,
        "4001",
    )
    assert (found[8]["dismissed_at"], found[8]["dismiss_reason"]) == (
        T2,
        "не мій рівень",
    )


def test_triage_analysis_application_and_photo_follow_the_mapped_job(
    world: World,
) -> None:
    world.apply()
    job = world.job_id(3)

    triage = rows(world.v2, "SELECT * FROM job_triage")
    assert [(row["job_id"], row["score"], row["verdict"]) for row in triage] == [
        (job, 82, "analyse")
    ]
    analysis = rows(world.v2, "SELECT * FROM job_analyses")
    assert [(row["job_id"], row["score"], row["details"]) for row in analysis] == [
        (job, 77, {"strengths": ["Python"], "gaps": ["Kafka"], "notes": 1})
    ]
    application = rows(world.v2, "SELECT * FROM applications")
    assert [
        (row["job_id"], row["status"], row["company_domains"], row["ats"])
        for row in application
    ] == [(job, "interview", ["acme.example"], "lever")]
    document = rows(
        world.v2, "SELECT job_id, photo_id FROM documents WHERE document_number = 10"
    )[0]
    photo = rows(world.v2, "SELECT id, data FROM photos")[0]
    assert (document["job_id"], document["photo_id"]) == (job, photo["id"])
    assert bytes(photo["data"]) == b"\xff\xd8\xff\xe0-jpeg-bytes"


def test_sources_original_cv_and_facts_are_copied(world: World) -> None:
    world.apply()

    company = v2_rows(world, "source_companies", "slug")
    assert [(r["platform"], r["slug"], r["name"], r["enabled"]) for r in company] == [
        ("greenhouse", "acme", "Acme", True)
    ]
    feed = v2_rows(world, "source_feeds", "query")
    assert [(r["source"], r["query"], r["enabled"]) for r in feed] == [
        ("dou", "python", False)
    ]
    cv = v2_rows(world, "original_cvs", "updated_at")
    assert [(r["file_name"], r["text"]) for r in cv] == [
        ("cv.pdf", "Taras CV full text")
    ]
    facts = v2_rows(world, "facts", "fact_number")
    assert [
        (r["fact_number"], r["kind"], r["text"], r["confirmed"]) for r in facts
    ] == [
        (2, "experience", FACT_TEXTS[2], True),
        (4, "skill", FACT_TEXTS[4], True),
        (7, "achievement", FACT_TEXTS[7], True),
        (9, "language", FACT_TEXTS[9], False),
    ]


@pytest.mark.parametrize("table", NOT_IMPORTED)
def test_runtime_tables_of_v1_are_not_imported(world: World, table: str) -> None:
    before = count(world.v2, table)

    assert world.apply() == 0

    assert count(world.v2, "jobs") == 3
    assert count(world.v2, table) == before


# 11. Пробний прогін --------------------------------------------------------------------------------


def test_dry_run_reports_counts_and_missing_pdfs(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    world.write_pdf(10, b"%PDF-1.7 ten")

    assert world.run("--pdf-dir", str(world.pdf_dir)) == 0

    out = capsys.readouterr().out
    assert "нічого не записано" in out
    for line in ("jobs: 3", "facts: 4", "documents: 3", "mail_messages: 3"):
        assert line in out
    assert "Немає PDF для документів: 11, 15" in out


def test_dry_run_writes_nothing(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    world.write_pdf(10, b"%PDF-1.7 ten")
    before = snapshot(world.v2)

    assert world.run("--pdf-dir", str(world.pdf_dir)) == 0

    assert "jobs: 3" in capsys.readouterr().out
    assert snapshot(world.v2) == before
    assert not world.documents_dir.exists()
    profile = rows(world.v2, "SELECT full_name FROM profiles")
    assert profile == [{"full_name": "Старий профіль"}]
    assert v2_rows(world, "mail_inboxes", "tag")[0]["tag"] == "v2oldtag"
    next_mail = world.v2.execute(
        "INSERT INTO mail_messages (user_id, gmail_id, received_at, category, attachments) "
        "VALUES (%s, 'g-new', %s, 'other', '[]') RETURNING id",
        (world.user, T2),
    ).fetchone()
    assert next_mail == {"id": 1}


# 12. Відмови без запису --------------------------------------------------------------------------------


def refuses(world: World, capsys: pytest.CaptureFixture[str], text: str) -> None:
    before = snapshot(world.v2)

    assert world.apply() == 1

    assert text in capsys.readouterr().err
    assert snapshot(world.v2) == before
    assert rows(world.v2, "SELECT full_name FROM profiles") == [
        {"full_name": "Старий профіль"}
    ]
    assert not world.documents_dir.exists()


def test_refuses_when_v2_has_no_users(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    world.v2.execute("TRUNCATE users CASCADE")

    assert world.apply() == 1

    assert "У v2 має бути рівно один користувач, зараз: 0" in capsys.readouterr().err
    assert count(world.v2, "jobs") == 0


def test_refuses_when_v2_has_several_users(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    v2_user(world.v2, "katya@example.com")

    refuses(world, capsys, "У v2 має бути рівно один користувач, зараз: 2")


def test_refuses_when_v1_has_several_users(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    world.v1.execute("INSERT INTO users (id, created_at) VALUES (2, %s)", (T0,))

    refuses(world, capsys, "У v1 має бути рівно один користувач, зараз: 2")


def _add_job(world: World) -> None:
    world.v2.execute(
        "INSERT INTO jobs (id, user_id, job_number, text, text_hash, created_at) "
        "VALUES (%s, %s, 1, 'x', 'h', %s)",
        (uuid4(), world.user, T0),
    )


def _add_fact(world: World) -> None:
    world.v2.execute(
        "INSERT INTO facts (id, user_id, fact_number, kind, text, text_hash, created_at, "
        "updated_at) VALUES (%s, %s, 1, 'skill', 'x', 'h', %s, %s)",
        (uuid4(), world.user, T0, T0),
    )


def _add_document(world: World) -> None:
    _add_job(world)
    job = rows(world.v2, "SELECT id FROM jobs")[0]["id"]
    world.v2.execute(
        "INSERT INTO documents (id, user_id, document_number, job_id, kind, version, "
        "content, created_at) VALUES (%s, %s, 1, %s, 'cl', 1, %s, %s)",
        (uuid4(), world.user, job, Jsonb({"paragraphs": [], "fact_ids": []}), T0),
    )


@pytest.mark.parametrize(
    ("existing", "table"),
    [(_add_job, "jobs"), (_add_fact, "facts"), (_add_document, "documents")],
)
def test_refuses_when_the_v2_user_already_has_domain_data(
    world: World,
    capsys: pytest.CaptureFixture[str],
    existing: Callable[[World], None],
    table: str,
) -> None:
    existing(world)

    refuses(world, capsys, f"У v2-користувача вже є дані: {table}")


def test_second_run_after_a_successful_import_is_refused(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    assert world.apply() == 0
    capsys.readouterr()
    before = snapshot(world.v2)

    assert world.apply() == 1

    assert "вже є дані" in capsys.readouterr().err
    assert snapshot(world.v2) == before


# 13. Збій посеред імпорту --------------------------------------------------------------------------------


def test_row_that_v2_rejects_rolls_the_whole_import_back(world: World) -> None:
    # У v1 нема перевірки розміру фото, у v2 вона є: падає після вакансій і фактів.
    world.v1.execute("UPDATE photos SET width = 0")
    before = snapshot(world.v2)

    with pytest.raises(IntegrityError):
        world.apply()

    assert snapshot(world.v2) == before
    assert rows(world.v2, "SELECT full_name FROM profiles") == [
        {"full_name": "Старий профіль"}
    ]
    assert v2_rows(world, "mail_inboxes", "tag")[0]["tag"] == "v2oldtag"


def test_file_that_cannot_be_written_rolls_the_whole_import_back(
    world: World, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("file", encoding="utf-8")
    monkeypatch.setenv("JOBOFFER_DOCUMENTS_DIR", str(blocker / "documents"))
    world.write_pdf(10, b"%PDF-1.7 ten")
    before = snapshot(world.v2)

    with pytest.raises(OSError, match="Not a directory"):
        world.apply("--pdf-dir", str(world.pdf_dir))

    assert snapshot(world.v2) == before


def test_files_written_before_a_failed_commit_are_removed(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Другий PDF не читається (це тека): перший уже записаний і має бути прибраний.
    world.write_pdf(10, b"%PDF-1.7 ten")
    (world.pdf_dir / "11.pdf").mkdir()
    before = snapshot(world.v2)

    with pytest.raises(OSError, match="Is a directory"):
        world.apply("--pdf-dir", str(world.pdf_dir))

    assert snapshot(world.v2) == before
    assert not world.documents_dir.exists() or not list(world.documents_dir.iterdir())
