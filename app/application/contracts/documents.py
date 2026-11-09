"""Команди й результати контексту documents: примітиви (значення будує use case)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from application.contracts.analysis import AnalysisData
from application.contracts.facts import FactData
from application.contracts.jobs import JobData
from application.contracts.photos import PhotoLibraryData
from application.contracts.profile import ProfileData
from domain.documents.document import DocumentKind
from domain.documents.gate import GateStatus
from domain.documents.lint import LintCode
from domain.documents.must_have import MustHaveStatus


@dataclass(frozen=True, slots=True, kw_only=True)
class ClaimData:
    """Рядок документа і факти, на яких він стоїть. Сирі значення з будь-якого транспорту;
    пробіли чистяться, межі перевіряє домен."""

    text: str
    fact_ids: Sequence[int] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class CvEntryData:
    heading: ClaimData
    bullets: Sequence[ClaimData] = ()
    meta: ClaimData | None = None
    subtitle: ClaimData | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class CvSectionData:
    name: str
    entries: Sequence[CvEntryData] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class CvData:
    headline: ClaimData
    summary: ClaimData
    sections: Sequence[CvSectionData] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class CoverLetterData:
    """Текст листа: абзаци — за порожнім рядком, одинарний перенос усередині абзацу лишається
    межею рядка (підпис «Best regards,\\nName»)."""

    text: str
    fact_ids: Sequence[int] = ()


@dataclass(frozen=True, slots=True, kw_only=True)
class LintIssueData:
    code: LintCode
    message: str


@dataclass(frozen=True, slots=True, kw_only=True)
class KeywordCoverageData:
    """Ключові слова аналізу: що є в тексті PDF, чого нема, і відсоток."""

    covered: tuple[str, ...]
    missing: tuple[str, ...]
    percent: int


@dataclass(frozen=True, slots=True, kw_only=True)
class LintData:
    """ATS-звіт на момент збереження версії. `passed` = нема issues; покриття ключових слів
    (`keywords`, None — вакансію не аналізовано) на нього не впливає."""

    passed: bool
    pages: int
    issues: tuple[LintIssueData, ...]
    keywords: KeywordCoverageData | None


@dataclass(frozen=True, slots=True, kw_only=True)
class GateData:
    """Гейт CV: `evidence_percent` — скільки слів із фактом є в CV (треба 100, слова без — у
    `evidence_missing`), `coverage_percent` — покриття очищеного списку (треба 90). `no_data` —
    у аналізу нема карти фактів чи слів: «пройдено» казати не можна."""

    status: GateStatus
    evidence_percent: int | None
    evidence_missing: tuple[str, ...]
    coverage_percent: int | None


@dataclass(frozen=True, slots=True, kw_only=True)
class MustHaveFactsData:
    """Вхід check_cv: що агент каже про пункт must-have — `item` (текст пункту з аналізу), факти під
    ним і `kind`: `fact` (факти закривають вимогу) чи `analogue` (схожий досвід замість неї)."""

    item: str
    fact_ids: Sequence[int]
    kind: str


@dataclass(frozen=True, slots=True, kw_only=True)
class MustHaveItemData:
    """Пункт must-have аналізу: `covered` / `analogue` (fact_ids — факти запису, на які спирається
    рядок CV) чи `missing` (reason — чому)."""

    item: str
    status: MustHaveStatus
    fact_ids: tuple[int, ...]
    reason: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class MustHaveCoverageData:
    """Покриття must-have аналізу: кожен його пункт по порядку; `unknown` — пункти з входу, яких
    в аналізі нема (не помилка)."""

    items: tuple[MustHaveItemData, ...]
    unknown: tuple[str, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class CheckData:
    """Результат check_cv / check_cover_letter: нічого не збережено. `passed` = нема issues —
    save_* прийме той самий документ. `keywords` — покриття по тексту документа (None — вакансію
    не аналізовано чи документ не розібрано)."""

    passed: bool
    issues: tuple[LintIssueData, ...]
    keywords: KeywordCoverageData | None
    gate: GateData | None = None
    # Лише в CV й лише коли вакансію проаналізовано, а CV розібрано; інакше None.
    must_have_coverage: MustHaveCoverageData | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class PruneData:
    """Підсумок чистки старих версій: скільки документів (рядків) зайві й скільки їхніх PDF є на
    диску; `applied` — чи вже видалено."""

    documents: int
    files: int
    applied: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class PdfFileData:
    """PDF версії і назва файлу для рекрутера (за іменем з профілю)."""

    data: bytes
    file_name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class DocumentData:
    """Збережена версія. `document_number` — номер документа на користувача."""

    document_number: int
    job_number: int
    kind: DocumentKind
    version: int
    content: CvData | CoverLetterData
    created_at: datetime
    # None — версія без ATS-звіту.
    lint: LintData | None = None
    # Номер фото в шапці CV; None — без фото.
    photo_number: int | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class JobDocumentData:
    """Версія документа вакансії для вебу: без вмісту, з назвою файлу й наявністю PDF на диску."""

    document_number: int
    job_number: int
    kind: DocumentKind
    version: int
    created_at: datetime
    file_name: str
    pdf_available: bool
    lint: LintData | None
    # Номер фото в шапці CV; None — без фото (листи фото не мають).
    photo_number: int | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class CeilingData:
    """Стеля покриття слів вакансії для CV: `percent` — частка слів із фактом під ними (треба 90),
    `unbacked` — слова без підтвердженого факту, `reaches_target` — чи стеля сягає 90."""

    percent: int
    unbacked: tuple[str, ...]
    reaches_target: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class CvBriefData:
    """Усе, що потрібно Claude для CV під одну вакансію."""

    job: JobData
    analysis: AnalysisData | None
    profile: ProfileData
    confirmed_facts: tuple[FactData, ...]
    rules: str
    previous: DocumentData | None
    # Фото, які запропонувати перед `save_cv`, і те, що пропонувати першим.
    photos: PhotoLibraryData
    # None: аналіз старий (без карти фактів) чи без слів.
    ceiling: CeilingData | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class CoverLetterBriefData:
    """Усе, що потрібно Claude для листа під одну вакансію; CV для нього не обов'язкове."""

    job: JobData
    analysis: AnalysisData | None
    profile: ProfileData
    confirmed_facts: tuple[FactData, ...]
    rules: str
    cv: DocumentData | None
    previous: DocumentData | None


@dataclass(frozen=True, slots=True, kw_only=True)
class DownloadLinkData:
    """Одноразове посилання на PDF: `token` показується лише тут, далі існує тільки його дайджест."""

    token: str
    file_name: str
    expires_at: datetime
