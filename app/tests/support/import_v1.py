"""Дані для тестів імпорту v1 → v2: схема v1 з фікстури, заповнення обох баз і читання результату.

Синхронний psycopg: бази тут лише готуються й перевіряються, сам імпорт іде через CLI.
Номери в v1 навмисно не підряд (3, 5, 8, …): так видно, що номер у v2 — це v1 id, а не порядок.
"""

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from domain.shared.fingerprint import text_fingerprint

V1_SCHEMA = Path(__file__).resolve().parents[1] / "fixtures" / "v1_schema_99a2007.sql"
V1_DB = "import_v1_src"
V2_DB = "import_v2_dst"

T0 = datetime(2026, 9, 1, 10, 0, tzinfo=UTC)
T1 = datetime(2026, 9, 2, 11, 30, tzinfo=UTC)
T2 = datetime(2026, 9, 3, 12, 45, tzinfo=UTC)

FACT_TEXTS = {
    2: "Led a team of 5 engineers at Acme",
    4: "Python, PostgreSQL, FastAPI",
    7: "Cut API latency by 40 percent",
    9: "English C1, Spanish B2",
}
# Лист у v2 має 150–250 слів: коротший репозиторій не прочитає.
LETTER = ["Dear Acme,", "I led a team of engineers. " * 30]
# Пакет до інтерв'ю: читач у v2 вимагає 5-20 питань, 3-6 історій, 3-8 питань до компанії.
KIT = {
    "questions": [
        {"kind": "technical", "question": "Explain MVCC?", "topic_id": 12},
        *[
            {"kind": "behavioral", "question": f"Behavioral {n}?", "topic_id": None}
            for n in range(1, 5)
        ],
    ],
    "stories": [
        {
            "title": f"Story {n}",
            "situation": "S",
            "task": "T",
            "action": "A",
            "result": "R",
            "fact_ids": [2, 7],
        }
        for n in range(1, 4)
    ],
    "company_questions": [f"Ask {n}?" for n in range(1, 4)],
}
FACT_KINDS = {2: "experience", 4: "skill", 7: "achievement", 9: "language"}

# Таблиця v1 → таблиця v2, що її імпорт наповнює (рядків у v1 стільки ж, скільки має стати у v2).
TABLE_PAIRS = {
    "search_locations": "profile_locations",
    "jobs": "jobs",
    "job_triage": "job_triage",
    "job_analyses": "job_analyses",
    "facts": "facts",
    "original_cvs": "original_cvs",
    "photos": "photos",
    "documents": "documents",
    "applications": "applications",
    "interview_kits": "interview_kits",
    "prep_topics": "prep_topics",
    "prep_topic_jobs": "prep_topic_jobs",
    "prep_steps": "prep_steps",
    "prep_questions": "prep_questions",
    "prep_attempts": "prep_answers",
    "watchlist_companies": "source_companies",
    "rss_feeds": "source_feeds",
    "mail_retired_tags": "mail_retired_tags",
    "mail_messages": "mail_messages",
    "job_replies": "job_replies",
    "mail_dropped": "mail_dropped",
    "mail_sync_state": "mail_sync_state",
}

# Таблиці v2, яких імпорт не чіпає (у v1 для них є дані: запуски, запити, OAuth).
NOT_IMPORTED = (
    "oauth_clients",
    "oauth_grants",
    "source_company_runs",
    "source_feed_runs",
    "mail_sync_requests",
    "source_refresh_requests",
)


def libpq(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://")


def with_database(url: str, database: str) -> str:
    return libpq(url).rsplit("/", 1)[0] + "/" + database


def connect(url: str) -> psycopg.Connection[dict[str, Any]]:
    return psycopg.connect(libpq(url), autocommit=True, row_factory=dict_row)


def rows(
    conn: psycopg.Connection[dict[str, Any]], sql: str, *params: object
) -> list[dict[str, Any]]:
    return conn.execute(sql, params).fetchall()


def count(conn: psycopg.Connection[dict[str, Any]], table: str) -> int:
    found = conn.execute(f"SELECT count(*) AS n FROM {table}").fetchone()  # noqa: S608
    assert found is not None
    return int(found["n"])


def table_names(conn: psycopg.Connection[dict[str, Any]]) -> list[str]:
    found = rows(
        conn,
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1",
    )
    return [row["tablename"] for row in found]


def snapshot(conn: psycopg.Connection[dict[str, Any]]) -> dict[str, int]:
    """Кількість рядків у кожній таблиці (крім alembic_version): «нічого не записано»."""
    return {
        name: count(conn, name)
        for name in table_names(conn)
        if name != "alembic_version"
    }


def create_database(admin: psycopg.Connection[dict[str, Any]], name: str) -> None:
    admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    admin.execute(f'CREATE DATABASE "{name}"')


def drop_database(admin: psycopg.Connection[dict[str, Any]], name: str) -> None:
    admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def create_v1_schema(conn: psycopg.Connection[dict[str, Any]]) -> None:
    conn.execute(V1_SCHEMA.read_text(encoding="utf-8"))


def wipe(conn: psycopg.Connection[dict[str, Any]], *, skip: tuple[str, ...]) -> None:
    names = [name for name in table_names(conn) if name not in skip]
    conn.execute(f"TRUNCATE {', '.join(names)} RESTART IDENTITY CASCADE")


def v2_user(conn: psycopg.Connection[dict[str, Any]], email: str) -> UUID:
    user_id = uuid4()
    conn.execute(
        "INSERT INTO users (id, email, display_name, version, created_at) "
        "VALUES (%s, %s, %s, 1, %s)",
        (user_id, email, "Богдан", T0),
    )
    return user_id


def seed_v2(conn: psycopg.Connection[dict[str, Any]]) -> UUID:
    """Один користувач v2 з уже налаштованим профілем, місцем пошуку, скринькою й підказкою
    онбордингу — це «порожній» стан, у який імпортують."""
    user = v2_user(conn, "taras@example.com")
    conn.execute(
        "INSERT INTO profiles (user_id, roles, full_name, email, city, updated_at) "
        "VALUES (%s, %s, 'Старий профіль', 'old@v2.example', 'Київ', %s)",
        (user, ["old role"], T0),
    )
    conn.execute(
        "INSERT INTO profile_locations (user_id, position, place, aliases, work_modes) "
        "VALUES (%s, 0, 'Старе місто', '{}', %s)",
        (user, ["remote"]),
    )
    conn.execute(
        "INSERT INTO mail_inboxes (user_id, tag, created_at) VALUES (%s, 'v2oldtag', %s)",
        (user, T0),
    )
    conn.execute(
        "INSERT INTO onboarding_tips (user_id, tip_key, seen_at) VALUES (%s, 'welcome', %s)",
        (user, T0),
    )
    return user


def _cv(*, heading: list[int], summary: list[int], bullets: list[int]) -> Jsonb:
    return Jsonb(
        {
            "headline": {"text": "Senior Python engineer", "fact_ids": heading},
            "summary": {"text": "Builds reliable backends", "fact_ids": summary},
            "sections": [
                {
                    "name": "Experience",
                    "entries": [
                        {
                            "heading": {"text": "Acme, Tech lead", "fact_ids": heading},
                            "bullets": [
                                {"text": "Cut latency", "fact_ids": bullets},
                            ],
                            "meta": {"text": "2020-2024", "fact_ids": heading},
                        }
                    ],
                },
                {
                    "name": "Skills",
                    "entries": [
                        {
                            "heading": {"text": "Python", "fact_ids": summary},
                            "bullets": [],
                        }
                    ],
                },
            ],
        }
    )


def seed_v1(conn: psycopg.Connection[dict[str, Any]]) -> None:
    """Повний набір даних одного користувача v1 (id 1) + рядки таблиць, що не переносяться."""
    x = conn.execute
    x("INSERT INTO users (id, created_at) VALUES (1, %s)", (T0,))
    x(
        "INSERT INTO preferences (user_id, roles, work_modes, relocation, seniority, "
        "min_salary_eur, stop_words, updated_at, full_name, email, phone, linkedin_url, "
        "city, github_url, work_authorization, title_keywords, title_exclude, "
        "include_unknown_mode, target_domains) VALUES (1, %s, %s, true, %s, 70000, %s, %s, "
        "'Богдан Прикладенко', 'taras@v1.example', '+34 600 000 000', "
        "'https://linkedin.com/in/taras', 'Валенсія', 'https://github.com/taras', "
        "'EU citizen', %s, %s, false, %s)",
        (
            ["backend", "platform"],
            ["remote", "hybrid"],
            ["senior", "lead"],
            ["crypto"],
            T2,
            ["python"],
            ["junior"],
            ["fintech"],
        ),
    )
    x(
        "INSERT INTO search_locations (id, user_id, position, place, aliases, work_modes) "
        "VALUES (1, 1, 0, 'Madrid', %s, %s), (2, 1, 1, 'Remote EU', '{}', %s)",
        (["Мадрид"], ["hybrid", "onsite"], ["remote"]),
    )
    # Вакансії: звичайна (відкрита), «потрібен текст» з LinkedIn, прибрана.
    x(
        "INSERT INTO jobs (id, user_id, source, url, title, company, text, text_hash, "
        "created_at, linkedin_id, opened_at, location) VALUES "
        "(3, 1, 'manual', 'https://acme.example/jobs/3', 'Backend engineer', 'Acme', "
        "'Python backend role at Acme', %s, %s, NULL, %s, 'Madrid')",
        (text_fingerprint("Python backend role at Acme"), T0, T1),
    )
    x(
        "INSERT INTO jobs (id, user_id, source, url, title, company, text, text_hash, "
        "created_at, linkedin_id) VALUES (5, 1, 'linkedin_alert', "
        "'https://www.linkedin.com/jobs/view/4001', 'Platform engineer', 'Globex', "
        "NULL, NULL, %s, '4001')",
        (T1,),
    )
    x(
        "INSERT INTO jobs (id, user_id, source, url, title, company, text, text_hash, "
        "created_at, dismissed_at, dismiss_reason) VALUES (8, 1, 'greenhouse', NULL, "
        "'Junior dev', 'Initech', 'Junior developer wanted', %s, %s, %s, 'не мій рівень')",
        (text_fingerprint("Junior developer wanted"), T1, T2),
    )
    x(
        "INSERT INTO job_triage (job_id, user_id, score, verdict, reason, triaged_at) "
        "VALUES (3, 1, 82, 'analyse', 'Strong stack match', %s)",
        (T1,),
    )
    x(
        "INSERT INTO job_analyses (job_id, user_id, score, work_mode, filters_passed, "
        "flags, details, updated_at) VALUES (3, 1, 77, 'hybrid', true, %s, %s, %s)",
        (
            ["salary_unknown"],
            Jsonb({"strengths": ["Python"], "gaps": ["Kafka"], "notes": 1}),
            T2,
        ),
    )
    for number, body in FACT_TEXTS.items():
        x(
            "INSERT INTO facts (id, user_id, kind, text, text_hash, confirmed, created_at, "
            "updated_at) VALUES (%s, 1, %s, %s, %s, %s, %s, %s)",
            (
                number,
                FACT_KINDS[number],
                body,
                text_fingerprint(body),
                number != 9,
                T0,
                T1,
            ),
        )
    x(
        "INSERT INTO original_cvs (user_id, file_name, text, updated_at) "
        "VALUES (1, 'cv.pdf', 'Taras CV full text', %s)",
        (T1,),
    )
    x(
        "INSERT INTO photos (id, user_id, label, data, width, height, created_at) "
        "VALUES (6, 1, 'Основне', %s, 400, 500, %s)",
        (b"\xff\xd8\xff\xe0-jpeg-bytes", T1),
    )
    lint = {
        "pages": 1,
        "issues": [{"code": "pages", "message": "Забагато сторінок"}],
        "keywords": {"covered": ["python"], "missing": ["kafka"]},
    }
    x(
        "INSERT INTO documents (id, user_id, job_id, kind, version, content, created_at, "
        "lint, photo_id) VALUES (10, 1, 3, 'cv', 1, %s, %s, %s, 6)",
        (_cv(heading=[2], summary=[4], bullets=[7]), T1, Jsonb(lint)),
    )
    x(
        "INSERT INTO documents (id, user_id, job_id, kind, version, content, created_at) "
        "VALUES (11, 1, 3, 'cl', 1, %s, %s)",
        (
            Jsonb({"paragraphs": LETTER, "fact_ids": [2, 7]}),
            T1,
        ),
    )
    x(
        "INSERT INTO documents (id, user_id, job_id, kind, version, content, created_at) "
        "VALUES (15, 1, 3, 'cv', 2, %s, %s)",
        (_cv(heading=[2], summary=[4, 9], bullets=[7]), T2),
    )
    x(
        "INSERT INTO applications (job_id, user_id, status, applied_on, channel, ats, "
        "company_domains, company_emails, status_changed_at, created_at, updated_at) "
        "VALUES (3, 1, 'interview', %s, 'email', 'lever', %s, %s, %s, %s, %s)",
        (
            date(2026, 9, 2),
            ["acme.example"],
            ["hr@acme.example"],
            T2,
            T1,
            T2,
        ),
    )
    x(
        "INSERT INTO interview_kits (id, user_id, job_id, version, content, created_at) "
        "VALUES (4, 1, 3, 1, %s, %s)",
        (
            Jsonb(KIT),
            T2,
        ),
    )
    # Підготовка.
    x(
        "INSERT INTO prep_topics (id, user_id, slug, title, kind, summary, deadline, "
        "created_at, updated_at, ready_at) VALUES "
        "(12, 1, 'sql', 'SQL', 'tech', 'Window functions', %s, %s, %s, NULL), "
        "(13, 1, 'star', 'STAR stories', 'behavioral', '', NULL, %s, %s, %s)",
        (date(2026, 11, 15), T0, T2, T0, T2, T2),
    )
    x(
        "INSERT INTO prep_topic_jobs (topic_id, job_id, gap) VALUES "
        "(12, 3, 'Window functions'), (13, 3, 'Stories with numbers')",
    )
    x(
        "INSERT INTO prep_steps (id, topic_id, position, kind, title, details, resources, "
        "minutes, done_at, note) VALUES "
        "(20, 12, 1, 'learn', 'Read docs', 'Chapter 3', %s, 30, %s, 'зробив'), "
        "(21, 12, 2, 'practice', 'Write queries', '', %s, 45, NULL, ''), "
        "(25, 13, 1, 'check', 'Tell a story', '', %s, 20, NULL, '')",
        (
            Jsonb([{"title": "PG docs", "url": "https://www.postgresql.org/docs/"}]),
            T2,
            Jsonb([]),
            Jsonb([]),
        ),
    )
    x(
        "INSERT INTO prep_questions (id, topic_id, question, question_hash, answer_points, "
        "box, due_on, created_at) VALUES "
        "(30, 12, 'What is a window function?', %s, %s, 3, %s, %s), "
        "(31, 13, 'Tell about a failure', %s, %s, 1, %s, %s)",
        (
            text_fingerprint("What is a window function?"),
            ["OVER clause", "partition"],
            date(2026, 11, 2),
            T1,
            text_fingerprint("Tell about a failure"),
            ["situation", "lesson"],
            date(2026, 10, 31),
            T1,
        ),
    )
    x(
        "INSERT INTO prep_attempts (id, question_id, grade, answer, feedback, box, "
        "answered_at) VALUES (1, 30, 2, 'не знаю', 'повтори', 1, %s), "
        "(2, 30, 4, 'OVER (...)', 'добре', 3, %s), (3, 31, 5, 'історія', 'супер', 1, %s)",
        (T0, T1, T2),
    )
    # Джерела.
    x(
        "INSERT INTO watchlist_companies (id, user_id, platform, slug, name, enabled, "
        "created_at) VALUES (1, 1, 'greenhouse', 'acme', 'Acme', true, %s)",
        (T0,),
    )
    x(
        "INSERT INTO rss_feeds (id, user_id, source, query, enabled, created_at) "
        "VALUES (1, 1, 'dou', 'python', false, %s)",
        (T0,),
    )
    # Пошта.
    x(
        "INSERT INTO mail_inboxes (user_id, tag, created_at, rotated_at) "
        "VALUES (1, 'v1tag7k2', %s, %s)",
        (T0, T1),
    )
    x(
        "INSERT INTO mail_retired_tags (tag, user_id, retired_at) VALUES "
        "('oldtag1', 1, %s), ('oldtag2', 1, %s)",
        (T0, T1),
    )
    for mail_id, gmail_id, category in (
        (100, "g100", "linkedin_alert"),
        (101, "g101", "company"),
        (205, "g205", "company"),
    ):
        x(
            "INSERT INTO mail_messages (id, user_id, gmail_id, message_id, in_reply_to, "
            "reference_ids, from_address, from_name, to_addresses, subject, sent_at, "
            "received_at, category, untrusted_text, attachments, parse_error, created_at, "
            "sender_auth, alerts_processed_at) VALUES (%s, 1, %s, %s, '', %s, %s, 'HR', "
            "%s, %s, %s, %s, %s, 'body text', %s, '', %s, 'verified', NULL)",
            (
                mail_id,
                gmail_id,
                f"<{gmail_id}@mail>",
                ["<root@mail>"],
                "hr@acme.example",
                ["taras+v1tag7k2@example.com"],
                f"Subject {mail_id}",
                T1,
                T2,
                category,
                Jsonb([{"name": "a.pdf"}]),
                T2,
            ),
        )
    x(
        "INSERT INTO job_replies (id, user_id, mail_id, job_id, confidence, matched_by, "
        "suggested_type, type, reviewed_at, created_at) VALUES "
        "(7, 1, 101, 3, 'high', 'thread', 'invitation', 'invitation', %s, %s), "
        "(9, 1, 205, NULL, NULL, NULL, 'other', NULL, NULL, %s)",
        (T2, T2, T2),
    )
    x(
        "INSERT INTO mail_dropped (id, user_id, gmail_id, reason, received_at, created_at) "
        "VALUES (4, 1, 'd4', 'daily_limit', %s, %s), (11, 1, 'd11', 'retired_tag', %s, %s)",
        (T1, T1, T2, T2),
    )
    x(
        "INSERT INTO mail_sync_state (mailbox, history_id, synced_at, last_error, failed_at) "
        "VALUES ('mailroom@example.com', '9876', %s, 'stale error', %s)",
        (T2, T1),
    )
    # Те, що не переноситься.
    x(
        "INSERT INTO oauth_clients (client_id, data) VALUES ('c1', %s)",
        (Jsonb({"redirect_uris": []}),),
    )
    x(
        "INSERT INTO oauth_grants (key_hash, kind, user_id, data, expires_at) "
        "VALUES ('h1', 'code', 1, %s, 1)",
        (Jsonb({}),),
    )
    x(
        "INSERT INTO source_runs (user_id, source, ran_at) VALUES (1, 'dou', %s)",
        (T2,),
    )
    x(
        "INSERT INTO mail_sync_requests (id, user_id, requested_at) VALUES (50, 1, %s)",
        (T2,),
    )
    x(
        "INSERT INTO source_refresh_requests (id, user_id, requested_at) VALUES (60, 1, %s)",
        (T2,),
    )
