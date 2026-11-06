"""Use cases документів під вакансію. REST і MCP викликають саме їх — правила в одному місці.

Claude отримує бриф (текст вакансії, аналіз, профіль, підтверджені факти, правила), пише CV чи
cover letter і перевіряє його (`check_*`: нічого не зберігається). Збереження повторює ті самі
перевірки й пише документ лише коли всі пройдено: сервер перевіряє довжини, що кожен рядок стоїть
на підтверджених фактах цього користувача, гігієну тексту й ATS-lint PDF. Нова версія замінює
попередню того ж виду для тієї ж вакансії. Вакансія скрізь — за номером у межах користувача.
"""

from collections.abc import Callable
from dataclasses import dataclass

from application.analysis.use_cases import analysis_data
from application.contracts.actor import Actor
from application.contracts.documents import (
    CeilingData,
    CheckData,
    CoverLetterBriefData,
    CoverLetterData,
    CvBriefData,
    CvData,
    DocumentData,
    GateData,
    JobDocumentData,
    KeywordCoverageData,
    LintData,
    LintIssueData,
    PdfFileData,
    PruneData,
)
from application.contracts.photos import PhotoLibraryData
from application.documents.parsing import (
    cover_letter_data,
    cv_data,
    cv_raw_fields,
    parse_cover_letter,
    parse_cv,
)
from application.facts.use_cases import fact_data
from application.jobs.use_cases import job_data
from application.photos.use_cases import photo_data
from application.ports.clock import Clock
from application.ports.documents import DocumentOutput, DocumentUnitOfWork
from application.ports.ids import IdGenerator
from application.ports.prompts import PromptKey, Prompts
from application.profile.use_cases import profile_data
from domain.documents.document import (
    CoverLetter,
    Cv,
    Document,
    DocumentKind,
)
from domain.documents.gate import CvGate, cv_ceiling, cv_gate
from domain.documents.ids import DocumentId
from domain.documents.layout import cover_letter_layout, cv_layout, pdf_file_name
from domain.documents.lint import (
    KeywordCoverage,
    LintCode,
    LintIssue,
    LintReport,
    cv_text_issues,
    keyword_coverage,
    letter_text_issues,
    lint,
)
from domain.facts.library import confirmed, require_confirmed
from domain.identity.ids import UserId
from domain.jobs.job import Job
from domain.photos.ids import PhotoId
from domain.photos.photo import StoredPhoto, suggested_photo
from domain.profile.contacts import Contacts
from domain.shared.errors import InvalidValue, NotFound


@dataclass(frozen=True, slots=True)
class _Ready:
    """Документ, що пройшов усі перевірки: його вміст, PDF і ATS-звіт для збереження."""

    content: Cv | CoverLetter
    pdf: bytes
    report: LintReport
    photo_id: PhotoId | None


@dataclass(frozen=True, slots=True)
class _Checked:
    """Підсумок перевірок. `ready` є лише коли зауважень нема; `invalid` — помилка розбору, фактів
    чи фото в первісному вигляді (збереження віддає її як є)."""

    issues: tuple[LintIssue, ...]
    keywords: KeywordCoverage | None
    invalid: InvalidValue | None = None
    ready: _Ready | None = None
    # Гейт є лише в CV: лист слів вакансії не вичерпує.
    gate: CvGate | None = None


class DocumentUseCases:
    def __init__(
        self,
        unit_of_work: Callable[[], DocumentUnitOfWork],
        clock: Clock,
        ids: IdGenerator,
        prompts: Prompts,
        output: DocumentOutput,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock
        self._ids = ids
        self._prompts = prompts
        self._output = output

    async def prepare_cv(self, actor: Actor, job_number: int) -> CvBriefData:
        """Бриф для CV. `NotFound` — вакансії нема чи вона чужа; `InvalidValue` — вакансія без
        тексту (з листа-алерту)."""
        user = actor.user_id
        async with self._unit_of_work() as uow:
            job = _writable(await uow.jobs.get(user, job_number), job_number)
            documents = await uow.documents.list_for_job(user, job.id)
            analysis = await uow.analyses.get(user, job.id)
            facts = confirmed(await uow.facts.all(user))
            profile = await uow.profiles.get(user)
            photos = await uow.photos.all(user)
        suggested = suggested_photo(photos)
        ceiling = (
            None
            if analysis is None
            else cv_ceiling(
                analysis.analysis.keywords,
                analysis.analysis.keyword_facts,
                {fact.number for fact in facts},
            )
        )
        return CvBriefData(
            job=job_data(job, None),
            analysis=None if analysis is None else analysis_data(analysis, None),
            profile=profile_data(profile),
            confirmed_facts=tuple(fact_data(fact) for fact in facts),
            rules=self._prompts.get(PromptKey.DOCUMENTS_CV_RULES),
            previous=_latest(documents, DocumentKind.CV),
            photos=PhotoLibraryData(
                photos=tuple(photo_data(photo) for photo in photos),
                suggested_photo_number=None if suggested is None else suggested.number,
            ),
            ceiling=None
            if ceiling is None
            else CeilingData(
                percent=ceiling.percent,
                unbacked=ceiling.unbacked,
                reaches_target=ceiling.reaches_target,
            ),
        )

    async def prepare_cover_letter(
        self, actor: Actor, job_number: int
    ) -> CoverLetterBriefData:
        """Бриф для листа. Те саме, що для CV, плюс останнє CV вакансії (якщо є — лист без CV
        можливий). `NotFound` / `InvalidValue` — як у `prepare_cv`."""
        user = actor.user_id
        async with self._unit_of_work() as uow:
            job = _writable(await uow.jobs.get(user, job_number), job_number)
            documents = await uow.documents.list_for_job(user, job.id)
            analysis = await uow.analyses.get(user, job.id)
            facts = confirmed(await uow.facts.all(user))
            profile = await uow.profiles.get(user)
        return CoverLetterBriefData(
            job=job_data(job, None),
            analysis=None if analysis is None else analysis_data(analysis, None),
            profile=profile_data(profile),
            confirmed_facts=tuple(fact_data(fact) for fact in facts),
            rules=self._prompts.get(PromptKey.DOCUMENTS_COVER_LETTER_RULES),
            cv=_latest(documents, DocumentKind.CV),
            previous=_latest(documents, DocumentKind.COVER_LETTER),
        )

    async def check_cv(
        self,
        actor: Actor,
        job_number: int,
        data: CvData,
        photo_number: int | None = None,
    ) -> CheckData:
        """Ті самі перевірки, що в `save_cv`, але нічого не зберігається і файлу нема. Спершу текст
        без рендеру; PDF рендериться (у пам'яті) лише коли текст чистий. Проблеми документа — у
        результаті; `NotFound` / `InvalidValue` — вакансії нема, чужа чи без тексту."""
        return await self._check_only(actor, job_number, data, photo_number)

    async def check_cover_letter(
        self, actor: Actor, job_number: int, data: CoverLetterData
    ) -> CheckData:
        """Те саме для листа."""
        return await self._check_only(actor, job_number, data, None)

    async def save_cv(
        self,
        actor: Actor,
        job_number: int,
        data: CvData,
        photo_number: int | None = None,
    ) -> DocumentData:
        """Перевіряє CV (як `check_cv`) й зберігає його з фото в шапці (`photo_number`; None — без
        фото); попередні CV цієї вакансії зникають разом з PDF. `InvalidValue` — некоректний
        документ, факти, фото чи зауваження перевірок (нічого не збережено і не видалено);
        `NotFound` — вакансії нема чи вона чужа."""
        return await self._save(actor, job_number, data, photo_number)

    async def save_cover_letter(
        self, actor: Actor, job_number: int, data: CoverLetterData
    ) -> DocumentData:
        """Те саме для листа: єдиний лист вакансії; CV для нього не обов'язкове. Помилки — як
        у `save_cv`."""
        return await self._save(actor, job_number, data, None)

    async def list_documents(
        self, actor: Actor, job_number: int
    ) -> tuple[DocumentData, ...]:
        """Усі версії CV і листів вакансії, новіші першими. Вакансії нема чи вона чужа — порожньо."""
        user = actor.user_id
        async with self._unit_of_work() as uow:
            job = await uow.jobs.get(user, job_number)
            if job is None:
                return ()
            documents = await uow.documents.list_for_job(user, job.id)
        return tuple(_data(document) for document in documents)

    async def list_job_documents(
        self, actor: Actor, job_number: int
    ) -> tuple[JobDocumentData, ...]:
        """Версії CV і листів вакансії для вебу, новіші першими. `NotFound` — вакансії нема чи вона чужа."""
        user = actor.user_id
        async with self._unit_of_work() as uow:
            job = await uow.jobs.get(user, job_number)
            if job is None:
                raise NotFound(f"Вакансію {job_number} не знайдено.")
            documents = await uow.documents.list_for_job(user, job.id)
            full_name = (await uow.profiles.get(user)).contacts.full_name
        present = [await self._output.files.exists(item.id) for item in documents]
        return tuple(
            JobDocumentData(
                document_number=document.number,
                job_number=document.job_number,
                kind=document.kind,
                version=document.version,
                created_at=document.created_at,
                file_name=pdf_file_name(full_name, document.kind),
                pdf_available=available,
                lint=None if document.lint is None else _lint_data(document.lint),
                photo_number=document.photo_number,
            )
            for document, available in zip(documents, present, strict=True)
        )

    async def get_pdf(self, actor: Actor, document_number: int) -> PdfFileData:
        """PDF версії документа. `NotFound` — документа нема чи він чужий, або нема файлу
        (інша версія замість нього не підставляється)."""
        user = actor.user_id
        async with self._unit_of_work() as uow:
            document = await uow.documents.get(user, document_number)
            profile = await uow.profiles.get(user)
        if document is None:
            raise NotFound(f"Документ {document_number} не знайдено.")
        data = await self._output.files.read(document.id)
        if data is None:
            raise NotFound(f"PDF документа {document_number} не знайдено.")
        return PdfFileData(
            data=data,
            file_name=pdf_file_name(profile.contacts.full_name, document.kind),
        )

    async def prune_superseded(self, apply: bool = False) -> PruneData:
        """Одноразова чистка: у кожного (користувач, вакансія, вид) лишає найновіший документ, решту
        (рядки, одноразові посилання, PDF) видаляє. `apply=False` лише рахує."""
        async with self._unit_of_work() as uow:
            old = await uow.documents.superseded()
            present = [await self._output.files.exists(item) for item in old]
            if apply:
                await uow.documents.delete(old)
                await uow.commit()
        if apply:
            for item in old:
                await self._output.files.delete(item)
        return PruneData(documents=len(old), files=sum(present), applied=apply)

    async def _check_only(
        self,
        actor: Actor,
        job_number: int,
        raw: CvData | CoverLetterData,
        photo_number: int | None,
    ) -> CheckData:
        user = actor.user_id
        async with self._unit_of_work() as uow:
            job = _writable(await uow.jobs.get(user, job_number), job_number)
            checked = await self._check(uow, user, job, raw, photo_number)
        return CheckData(
            passed=not checked.issues,
            issues=tuple(
                LintIssueData(code=issue.code, message=issue.message)
                for issue in checked.issues
            ),
            keywords=_keywords_data(checked.keywords),
            gate=_gate_data(checked.gate),
        )

    async def _save(
        self,
        actor: Actor,
        job_number: int,
        raw: CvData | CoverLetterData,
        photo_number: int | None,
    ) -> DocumentData:
        user = actor.user_id
        async with self._unit_of_work() as uow:
            job = _writable(await uow.jobs.get(user, job_number), job_number)
            checked = await self._check(uow, user, job, raw, photo_number)
            if checked.invalid is not None:
                raise checked.invalid
            ready = checked.ready
            if ready is None:
                raise InvalidValue("document", _rejection(checked.issues))
            # Запис файлу — до commit: не вдався — документа в базі нема, старі лишаються.
            saved = await uow.documents.add(
                user,
                DocumentId(self._ids.new()),
                job.id,
                ready.content,
                self._clock.now(),
                lint=ready.report,
                photo_id=ready.photo_id,
            )
            await self._output.files.write(saved.id, ready.pdf)
            replaced = await uow.documents.delete_for_job(
                user, job.id, saved.kind, saved.id
            )
            await uow.commit()
        # Файли попередніх версій — після commit: до нього рядки ще можна відкотити.
        for old in replaced:
            await self._output.files.delete(old)
        return _data(saved)

    async def _validated(
        self,
        uow: DocumentUnitOfWork,
        user: UserId,
        raw: CvData | CoverLetterData,
        photo_number: int | None,
    ) -> tuple[Cv | CoverLetter, Contacts, StoredPhoto | None]:
        """Розбір, факти, ім'я в профілі й фото. `InvalidValue` — перше, що не так."""
        content = parse_cv(raw) if isinstance(raw, CvData) else parse_cover_letter(raw)
        require_confirmed(await uow.facts.all(user), content.fact_ids)
        contacts = (await uow.profiles.get(user)).contacts
        if not contacts.full_name:
            raise InvalidValue(
                "contacts",
                "У профілі нема імені для шапки документа: "
                "заповни контакти (update_profile).",
            )
        if photo_number is None:
            return content, contacts, None
        photo = await uow.photos.get(user, photo_number)
        if photo is None:
            raise InvalidValue(
                "photo_id", f"Фото {photo_number} не знайдено в профілі."
            )
        return content, contacts, photo

    async def _check(
        self,
        uow: DocumentUnitOfWork,
        user: UserId,
        job: Job,
        raw: CvData | CoverLetterData,
        photo_number: int | None,
    ) -> _Checked:
        """Усі перевірки документа в одному місці — для `check_*` і `save_*`. Спершу текст без
        рендеру (розбір, факти, ім'я, фото, гігієна); PDF рендериться, лише коли текст чистий, і
        тоді йде ATS-lint."""
        hygiene = (
            cv_text_issues(*cv_raw_fields(raw))
            if isinstance(raw, CvData)
            else letter_text_issues(raw.text)
        )
        try:
            content, contacts, photo = await self._validated(
                uow, user, raw, photo_number
            )
        except InvalidValue as error:
            issue = LintIssue(LintCode.INVALID_VALUE, error.message)
            return _Checked((issue, *hygiene), None, invalid=error)
        analysis = await uow.analyses.get(user, job.id)
        keywords = () if analysis is None else analysis.analysis.keywords
        if isinstance(content, Cv):
            layout = cv_layout(content, contacts)
        else:
            layout = cover_letter_layout(content, contacts)
        coverage = keyword_coverage(keywords, layout.lines)
        gate = None
        if isinstance(content, Cv):
            live = {fact.number for fact in confirmed(await uow.facts.all(user))}
            gate = cv_gate(
                coverage,
                None if analysis is None else analysis.analysis.keyword_facts,
                live,
            )
        if hygiene:
            return _Checked(hygiene, coverage, gate=gate)
        if isinstance(content, Cv):
            pdf = await self._output.renderer.render_cv(
                content, contacts, None if photo is None else photo.data
            )
        else:
            pdf = await self._output.renderer.render_cover_letter(content, contacts)
        report = lint(layout, await self._output.inspector.inspect(pdf), keywords)
        if report.issues:
            return _Checked(report.issues, coverage, gate=gate)
        return _Checked(
            (),
            coverage,
            ready=_Ready(content, pdf, report, None if photo is None else photo.id),
            gate=gate,
        )


def _rejection(issues: tuple[LintIssue, ...]) -> str:
    listed = " ".join(f"[{issue.code.value}] {issue.message}" for issue in issues)
    return f"Документ не збережено — виправ і перевір знову (check_*): {listed}"


def _keywords_data(keywords: KeywordCoverage | None) -> KeywordCoverageData | None:
    return (
        None
        if keywords is None
        else KeywordCoverageData(
            covered=keywords.covered, missing=keywords.missing, percent=keywords.percent
        )
    )


def _gate_data(gate: CvGate | None) -> GateData | None:
    return (
        None
        if gate is None
        else GateData(
            status=gate.status,
            evidence_percent=gate.evidence_percent,
            evidence_missing=gate.evidence_missing,
            coverage_percent=gate.coverage_percent,
        )
    )


def _writable(job: Job | None, number: int) -> Job:
    """Вакансія, під яку можна писати документ: своя й з текстом."""
    if job is None:
        raise NotFound(f"Вакансію {number} не знайдено.")
    if job.needs_text:
        raise InvalidValue(
            "job_id",
            f"У вакансії {number} нема тексту опису "
            "(вона з листа-алерту): спершу додай текст.",
        )
    return job


def _latest(documents: list[Document], kind: DocumentKind) -> DocumentData | None:
    """Остання версія виду (список — новіші першими)."""
    return next((_data(item) for item in documents if item.kind is kind), None)


def _data(document: Document) -> DocumentData:
    content = document.content
    return DocumentData(
        document_number=document.number,
        job_number=document.job_number,
        kind=document.kind,
        version=document.version,
        content=cv_data(content)
        if isinstance(content, Cv)
        else cover_letter_data(content),
        created_at=document.created_at,
        lint=None if document.lint is None else _lint_data(document.lint),
        photo_number=document.photo_number,
    )


def _lint_data(report: LintReport) -> LintData:
    keywords = report.keywords
    return LintData(
        passed=report.passed,
        pages=report.pages,
        issues=tuple(
            LintIssueData(code=issue.code, message=issue.message)
            for issue in report.issues
        ),
        keywords=_keywords_data(keywords),
    )
