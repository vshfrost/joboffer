"""Перенос даних одного користувача з БД v1 у БД v2 (одноразовий, B12).

Правило номерів: номер у v2 = `id` у v1 (а лічильники v2 = найбільший перенесений номер), тож
`fact_ids` у JSON документів і пакетів та `topic_id` у питаннях пакета лишаються правдивими без
переписування; JSON, хеші тексту й часові мітки переносяться як є. Внутрішні ключі v2 — нові UUID
(мапа v1 id → UUID потрібна для зовнішніх ключів). Бази різні, тож рядки читаються з v1 і
вставляються у v2 через ORM-таблиці адаптера: схема v2 — єдине джерело назв колонок.

Транзакція v2 відкрита на всі `copy()`; ідентифікаційні послідовності (bigint-ключі пошти) не
відкочуються, тому їх посуває лише `commit()`.
"""

from collections.abc import AsyncIterator, Iterable, Mapping, Sequence
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, insert, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from application.ports.ids import IdGenerator
from application.ports.v1_import import (
    Copied,
    ImportedDocument,
    ImportRefused,
    V1Transfer,
)
from domain.documents.ids import DocumentId
from infrastructure.db.analysis.tables import AnalysisRow
from infrastructure.db.applications.tables import ApplicationRow
from infrastructure.db.documents.tables import DocumentCounterRow, DocumentRow
from infrastructure.db.facts.tables import FactCounterRow, FactRow, OriginalCvRow
from infrastructure.db.jobs.tables import JobCounterRow, JobRow
from infrastructure.db.mail.tables import (
    JobReplyRow,
    MailDroppedRow,
    MailInboxRow,
    MailMessageRow,
    MailRetiredTagRow,
    MailSyncStateRow,
)
from infrastructure.db.photos.tables import PhotoCounterRow, PhotoRow
from infrastructure.db.prep.tables import (
    InterviewKitCounterRow,
    InterviewKitRow,
    PrepAnswerRow,
    PrepQuestionCounterRow,
    PrepQuestionRow,
    PrepStepCounterRow,
    PrepStepRow,
    PrepTopicCounterRow,
    PrepTopicJobRow,
    PrepTopicRow,
)
from infrastructure.db.profile.tables import ProfileLocationRow, ProfileRow
from infrastructure.db.sources.tables import SourceCompanyRow, SourceFeedRow
from infrastructure.db.triage.tables import TriageRow

type Values = dict[str, Any]

# Таблиці з даними користувача, які мають бути порожні (профіль, скринька й онбординг — ні).
# Спершу похідні, потім вакансії: повідомлення називає найпершу причину.
_MUST_BE_EMPTY: tuple[tuple[str, Any], ...] = (
    ("documents", DocumentRow),
    ("interview_kits", InterviewKitRow),
    ("applications", ApplicationRow),
    ("facts", FactRow),
    ("original_cvs", OriginalCvRow),
    ("photos", PhotoRow),
    ("prep_topics", PrepTopicRow),
    ("source_companies", SourceCompanyRow),
    ("source_feeds", SourceFeedRow),
    ("job_replies", JobReplyRow),
    ("mail_messages", MailMessageRow),
    ("mail_dropped", MailDroppedRow),
    ("mail_retired_tags", MailRetiredTagRow),
    ("jobs", JobRow),
)

_PROFILE = (
    "roles",
    "work_modes",
    "include_unknown_mode",
    "relocation",
    "target_domains",
    "seniority",
    "min_salary_eur",
    "stop_words",
    "title_keywords",
    "title_exclude",
    "full_name",
    "email",
    "phone",
    "linkedin_url",
    "city",
    "github_url",
    "work_authorization",
    "updated_at",
)
_LOCATION = ("position", "place", "aliases", "work_modes")
_JOB = (
    "source",
    "url",
    "title",
    "company",
    "text",
    "text_hash",
    "linkedin_id",
    "location",
    "created_at",
    "opened_at",
    "dismissed_at",
    "dismiss_reason",
)
_TRIAGE = ("score", "verdict", "reason", "triaged_at")
_ANALYSIS = ("score", "work_mode", "filters_passed", "flags", "details", "updated_at")
_FACT = ("kind", "text", "text_hash", "confirmed", "created_at", "updated_at")
_ORIGINAL_CV = ("file_name", "text", "updated_at")
_PHOTO = ("label", "data", "width", "height", "created_at")
_DOCUMENT = ("kind", "version", "content", "lint", "created_at")
_APPLICATION = (
    "status",
    "applied_on",
    "channel",
    "ats",
    "company_domains",
    "company_emails",
    "status_changed_at",
    "created_at",
    "updated_at",
)
_KIT = ("version", "content", "created_at")
_TOPIC = ("slug", "title", "kind", "summary", "deadline", "created_at", "ready_at")
_STEP = (
    "position",
    "kind",
    "title",
    "details",
    "resources",
    "minutes",
    "done_at",
    "note",
)
_QUESTION = (
    "question",
    "question_hash",
    "answer_points",
    "box",
    "due_on",
    "created_at",
)
_ANSWER = ("grade", "answer", "feedback", "box", "answered_at")
_COMPANY = ("platform", "slug", "name", "enabled", "created_at")
_FEED = ("source", "query", "enabled", "created_at")
_INBOX = ("tag", "created_at", "rotated_at")
_RETIRED = ("tag", "retired_at")
_MESSAGE = (
    "id",
    "gmail_id",
    "message_id",
    "in_reply_to",
    "reference_ids",
    "from_address",
    "from_name",
    "to_addresses",
    "subject",
    "sent_at",
    "received_at",
    "category",
    "sender_auth",
    "untrusted_text",
    "attachments",
    "parse_error",
    "created_at",
    "alerts_processed_at",
)
_REPLY = (
    "id",
    "mail_id",
    "confidence",
    "matched_by",
    "suggested_type",
    "type",
    "reviewed_at",
    "created_at",
)
_DROPPED = ("id", "gmail_id", "reason", "received_at", "created_at")
_SYNC_STATE = ("mailbox", "history_id", "synced_at", "last_error", "failed_at")

# Таблиці з bigint-ключем, який v1 віддав явно: послідовність мусить піти далі за найбільший.
_IDENTITY_TABLES = ("mail_messages", "job_replies", "mail_dropped")


def _carry(row: Mapping[str, Any], columns: Iterable[str]) -> Values:
    return {column: row[column] for column in columns}


class PostgresV1Import:
    def __init__(self, v1: AsyncEngine, v2: AsyncEngine, ids: IdGenerator) -> None:
        self._v1 = v1
        self._v2 = v2
        self._ids = ids

    @asynccontextmanager
    async def begin(self) -> AsyncIterator[V1Transfer]:
        # Закриття з'єднання v2 без `commit()` відкочує транзакцію.
        async with self._v1.connect() as source, self._v2.connect() as target:
            yield _Transfer(source, target, self._ids)


class _Transfer:
    def __init__(
        self, source: AsyncConnection, target: AsyncConnection, ids: IdGenerator
    ) -> None:
        self._source = source
        self._target = target
        self._ids = ids
        self._user = UUID(int=1)
        self._v1_user = 0
        self._counts: list[tuple[str, int]] = []
        self._jobs: dict[int, UUID] = {}
        self._photos: dict[int, UUID] = {}
        self._topics: dict[int, UUID] = {}
        self._questions: dict[int, UUID] = {}
        self._documents: list[ImportedDocument] = []

    async def commit(self) -> None:
        for table in _IDENTITY_TABLES:
            if any(name == table and count for name, count in self._counts):
                await self._target.execute(
                    text(
                        f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "  # noqa: S608
                        f"(SELECT max(id) FROM {table}))"
                    )
                )
        await self._target.commit()

    async def copy(self) -> Copied:
        self._user = await self._only_user(self._target, "v2")
        self._v1_user = await self._only_user(self._source, "v1")
        await self._require_empty()
        await self._copy_profile()
        await self._copy_jobs()
        await self._copy_facts()
        await self._copy_documents()
        await self._copy_applications()
        await self._copy_prep()
        await self._copy_sources()
        await self._copy_mail()
        return Copied(tuple(self._counts), tuple(self._documents))

    # Перевірки ------------------------------------------------------------------------------

    async def _only_user(self, conn: AsyncConnection, label: str) -> Any:
        found = (await conn.execute(text("SELECT id FROM users"))).scalars().all()
        if len(found) != 1:
            raise ImportRefused(
                f"У {label} має бути рівно один користувач, зараз: {len(found)}"
            )
        return found[0]

    async def _require_empty(self) -> None:
        filled = []
        for label, row in _MUST_BE_EMPTY:
            found = await self._target.scalar(
                select(func.count()).select_from(row).where(row.user_id == self._user)
            )
            if found:
                filled.append(label)
        if filled:
            raise ImportRefused(
                f"У v2-користувача вже є дані: {', '.join(filled)} "
                "(імпорт можливий лише в порожній обліковий запис)"
            )

    # Читання й запис ----------------------------------------------------------------------------

    async def _read(self, sql: str) -> list[Values]:
        result = await self._source.execute(text(sql), {"u": self._v1_user})
        return [dict(row) for row in result.mappings()]

    async def _write(self, name: str, table: Any, rows: Sequence[Values]) -> None:
        self._counts.append((name, len(rows)))
        if rows:
            await self._target.execute(insert(table), list(rows))

    async def _counter(self, counter: Any, numbers: Iterable[int]) -> None:
        last = max(numbers, default=0)
        if last:
            await self._target.execute(
                pg_insert(counter)
                .values(user_id=self._user, last_number=last)
                .on_conflict_do_update(
                    index_elements=[counter.user_id],
                    set_={"last_number": func.greatest(counter.last_number, last)},
                )
            )

    def _new(self) -> UUID:
        return self._ids.new()

    # Таблиці ---------------------------------------------------------------------------------------

    async def _copy_profile(self) -> None:
        preferences = await self._read("SELECT * FROM preferences WHERE user_id = :u")
        self._counts.append(("profiles", len(preferences)))
        if preferences:
            # Профіль v2 перезаписується цілком; позначка змін входів аналізу скидається:
            # аналізи v1 лишаються актуальними.
            values = _carry(preferences[0], _PROFILE) | {
                "analysis_inputs_changed_at": None
            }
            await self._target.execute(
                pg_insert(ProfileRow)
                .values(user_id=self._user, **values)
                .on_conflict_do_update(index_elements=[ProfileRow.user_id], set_=values)
            )
        locations = await self._read(
            "SELECT * FROM search_locations WHERE user_id = :u ORDER BY position"
        )
        await self._target.execute(
            delete(ProfileLocationRow).where(ProfileLocationRow.user_id == self._user)
        )
        await self._write(
            "profile_locations",
            ProfileLocationRow,
            [_carry(row, _LOCATION) | {"user_id": self._user} for row in locations],
        )

    async def _copy_jobs(self) -> None:
        jobs = await self._read("SELECT * FROM jobs WHERE user_id = :u ORDER BY id")
        self._jobs = {row["id"]: self._new() for row in jobs}
        await self._write(
            "jobs",
            JobRow,
            [
                _carry(row, _JOB)
                | {
                    "id": self._jobs[row["id"]],
                    "user_id": self._user,
                    "job_number": row["id"],
                }
                for row in jobs
            ],
        )
        await self._counter(JobCounterRow, self._jobs)
        triage = await self._read(
            "SELECT * FROM job_triage WHERE user_id = :u ORDER BY job_id"
        )
        await self._write(
            "job_triage",
            TriageRow,
            [
                _carry(row, _TRIAGE) | self._owned(row["job_id"], self._jobs)
                for row in triage
            ],
        )
        analyses = await self._read(
            "SELECT * FROM job_analyses WHERE user_id = :u ORDER BY job_id"
        )
        await self._write(
            "job_analyses",
            AnalysisRow,
            [
                _carry(row, _ANALYSIS) | self._owned(row["job_id"], self._jobs)
                for row in analyses
            ],
        )

    def _owned(self, v1_job: int, jobs: Mapping[int, UUID]) -> Values:
        """Ключі рядка, що належить вакансії (тріаж, аналіз): новий UUID, власник, вакансія v2."""
        return {"id": self._new(), "user_id": self._user, "job_id": jobs[v1_job]}

    async def _copy_facts(self) -> None:
        facts = await self._read("SELECT * FROM facts WHERE user_id = :u ORDER BY id")
        await self._write(
            "facts",
            FactRow,
            [
                _carry(row, _FACT)
                | {"id": self._new(), "user_id": self._user, "fact_number": row["id"]}
                for row in facts
            ],
        )
        await self._counter(FactCounterRow, (row["id"] for row in facts))
        originals = await self._read("SELECT * FROM original_cvs WHERE user_id = :u")
        await self._write(
            "original_cvs",
            OriginalCvRow,
            [_carry(row, _ORIGINAL_CV) | {"user_id": self._user} for row in originals],
        )

    async def _copy_documents(self) -> None:
        photos = await self._read("SELECT * FROM photos WHERE user_id = :u ORDER BY id")
        self._photos = {row["id"]: self._new() for row in photos}
        await self._write(
            "photos",
            PhotoRow,
            [
                _carry(row, _PHOTO)
                | {
                    "id": self._photos[row["id"]],
                    "user_id": self._user,
                    "photo_number": row["id"],
                }
                for row in photos
            ],
        )
        await self._counter(PhotoCounterRow, self._photos)
        documents = await self._read(
            "SELECT * FROM documents WHERE user_id = :u ORDER BY id"
        )
        ids = {row["id"]: self._new() for row in documents}
        self._documents = [
            ImportedDocument(v1_id, DocumentId(document_id))
            for v1_id, document_id in ids.items()
        ]
        await self._write(
            "documents",
            DocumentRow,
            [
                _carry(row, _DOCUMENT)
                | {
                    "id": ids[row["id"]],
                    "user_id": self._user,
                    "document_number": row["id"],
                    "job_id": self._jobs[row["job_id"]],
                    "photo_id": None
                    if row["photo_id"] is None
                    else self._photos[row["photo_id"]],
                }
                for row in documents
            ],
        )
        await self._counter(DocumentCounterRow, ids)

    async def _copy_applications(self) -> None:
        applications = await self._read(
            "SELECT * FROM applications WHERE user_id = :u ORDER BY job_id"
        )
        await self._write(
            "applications",
            ApplicationRow,
            [
                _carry(row, _APPLICATION)
                | {"user_id": self._user, "job_id": self._jobs[row["job_id"]]}
                for row in applications
            ],
        )
        kits = await self._read(
            "SELECT * FROM interview_kits WHERE user_id = :u ORDER BY id"
        )
        await self._write(
            "interview_kits",
            InterviewKitRow,
            [
                _carry(row, _KIT)
                | {
                    "id": self._new(),
                    "user_id": self._user,
                    "kit_number": row["id"],
                    "job_id": self._jobs[row["job_id"]],
                }
                for row in kits
            ],
        )
        await self._counter(InterviewKitCounterRow, (row["id"] for row in kits))

    async def _copy_prep(self) -> None:
        topics = await self._read(
            "SELECT * FROM prep_topics WHERE user_id = :u ORDER BY id"
        )
        self._topics = {row["id"]: self._new() for row in topics}
        await self._write(
            "prep_topics",
            PrepTopicRow,
            [
                _carry(row, _TOPIC)
                | {
                    "id": self._topics[row["id"]],
                    "user_id": self._user,
                    "topic_number": row["id"],
                }
                for row in topics
            ],
        )
        await self._counter(PrepTopicCounterRow, self._topics)
        links = await self._read(
            "SELECT l.* FROM prep_topic_jobs l JOIN prep_topics t ON t.id = l.topic_id "
            "WHERE t.user_id = :u ORDER BY l.topic_id, l.job_id"
        )
        await self._write(
            "prep_topic_jobs",
            PrepTopicJobRow,
            [
                {
                    "topic_id": self._topics[row["topic_id"]],
                    "job_id": self._jobs[row["job_id"]],
                    "gap": row["gap"],
                }
                for row in links
            ],
        )
        steps = await self._read(
            "SELECT s.* FROM prep_steps s JOIN prep_topics t ON t.id = s.topic_id "
            "WHERE t.user_id = :u ORDER BY s.id"
        )
        await self._write(
            "prep_steps",
            PrepStepRow,
            [
                _carry(row, _STEP)
                | {
                    "id": self._new(),
                    "user_id": self._user,
                    "step_number": row["id"],
                    "topic_id": self._topics[row["topic_id"]],
                }
                for row in steps
            ],
        )
        await self._counter(PrepStepCounterRow, (row["id"] for row in steps))
        questions = await self._read(
            "SELECT q.* FROM prep_questions q JOIN prep_topics t ON t.id = q.topic_id "
            "WHERE t.user_id = :u ORDER BY q.id"
        )
        self._questions = {row["id"]: self._new() for row in questions}
        await self._write(
            "prep_questions",
            PrepQuestionRow,
            [
                _carry(row, _QUESTION)
                | {
                    "id": self._questions[row["id"]],
                    "user_id": self._user,
                    "question_number": row["id"],
                    "topic_id": self._topics[row["topic_id"]],
                }
                for row in questions
            ],
        )
        await self._counter(PrepQuestionCounterRow, self._questions)
        attempts = await self._read(
            "SELECT a.* FROM prep_attempts a JOIN prep_questions q ON q.id = a.question_id "
            "JOIN prep_topics t ON t.id = q.topic_id WHERE t.user_id = :u ORDER BY a.id"
        )
        await self._write(
            "prep_answers",
            PrepAnswerRow,
            [
                _carry(row, _ANSWER)
                | {
                    "id": self._new(),
                    "question_id": self._questions[row["question_id"]],
                }
                for row in attempts
            ],
        )

    async def _copy_sources(self) -> None:
        companies = await self._read(
            "SELECT * FROM watchlist_companies WHERE user_id = :u ORDER BY id"
        )
        await self._write(
            "source_companies",
            SourceCompanyRow,
            [
                _carry(row, _COMPANY) | {"id": self._new(), "user_id": self._user}
                for row in companies
            ],
        )
        feeds = await self._read(
            "SELECT * FROM rss_feeds WHERE user_id = :u ORDER BY id"
        )
        await self._write(
            "source_feeds",
            SourceFeedRow,
            [
                _carry(row, _FEED) | {"id": self._new(), "user_id": self._user}
                for row in feeds
            ],
        )

    async def _copy_mail(self) -> None:
        inboxes = await self._read("SELECT * FROM mail_inboxes WHERE user_id = :u")
        self._counts.append(("mail_inboxes", len(inboxes)))
        if inboxes:
            # Тег v1 заміщує тег v2: фільтри Gmail власника v1 лишаються робочими.
            values = _carry(inboxes[0], _INBOX)
            await self._target.execute(
                pg_insert(MailInboxRow)
                .values(user_id=self._user, **values)
                .on_conflict_do_update(
                    index_elements=[MailInboxRow.user_id], set_=values
                )
            )
        retired = await self._read(
            "SELECT * FROM mail_retired_tags WHERE user_id = :u ORDER BY tag"
        )
        self._counts.append(("mail_retired_tags", len(retired)))
        if retired:
            await self._target.execute(
                pg_insert(MailRetiredTagRow)
                .values(
                    [_carry(row, _RETIRED) | {"user_id": self._user} for row in retired]
                )
                .on_conflict_do_nothing()
            )
        messages = await self._read(
            "SELECT * FROM mail_messages WHERE user_id = :u ORDER BY id"
        )
        await self._write(
            "mail_messages",
            MailMessageRow,
            [_carry(row, _MESSAGE) | {"user_id": self._user} for row in messages],
        )
        replies = await self._read(
            "SELECT * FROM job_replies WHERE user_id = :u ORDER BY id"
        )
        await self._write(
            "job_replies",
            JobReplyRow,
            [
                _carry(row, _REPLY)
                | {
                    "user_id": self._user,
                    "job_id": None
                    if row["job_id"] is None
                    else self._jobs[row["job_id"]],
                }
                for row in replies
            ],
        )
        dropped = await self._read(
            "SELECT * FROM mail_dropped WHERE user_id = :u ORDER BY id"
        )
        await self._write(
            "mail_dropped",
            MailDroppedRow,
            [
                _carry(row, _DROPPED)
                | {"user_id": self._user, "from_address": "", "subject": ""}
                for row in dropped
            ],
        )
        states = await self._read("SELECT * FROM mail_sync_state ORDER BY mailbox")
        self._counts.append(("mail_sync_state", len(states)))
        if states:
            upsert = pg_insert(MailSyncStateRow).values(
                [_carry(row, _SYNC_STATE) for row in states]
            )
            await self._target.execute(
                upsert.on_conflict_do_update(
                    index_elements=[MailSyncStateRow.mailbox],
                    set_={
                        column: getattr(upsert.excluded, column)
                        for column in _SYNC_STATE[1:]
                    },
                )
            )
