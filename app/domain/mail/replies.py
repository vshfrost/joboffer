"""Відповіді компаній на подачі: лист категорії company зіставляється з поданими вакансіями
того самого користувача, евристика підказує тип листа. Остаточно тип і вакансію підтверджує
користувач разом з агентом (review_reply); сам статус змінюється лише на replied, лише за
впевненого збігу і лише для листа від підтвердженого відправника. Текст листа — недовірені
дані. Вакансія скрізь — за номером у межах користувача."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from domain.applications.application import TRANSITIONS, ApplicationStatus, AtsPlatform
from domain.mail.forwarded import ForwardedMail
from domain.mail.inbox import MailSummary
from domain.mail.sender_auth import SenderAuth
from domain.shared.errors import InvalidValue

DEFAULT_REPLIES_LIMIT = 10
MAX_REPLIES_LIMIT = 50
# Стільки тексту листа віддається агенту: відповідь коротка, решта — цитати й підписи.
REPLY_TEXT_LIMIT = 4000

# Відправники ATS: листи від імені компанії, домен — платформи.
ATS_SENDER_DOMAINS = {
    "greenhouse.io": AtsPlatform.GREENHOUSE,
    "greenhouse-mail.io": AtsPlatform.GREENHOUSE,
    "lever.co": AtsPlatform.LEVER,
    "ashbyhq.com": AtsPlatform.ASHBY,
    "workable.com": AtsPlatform.WORKABLE,
    "workablemail.com": AtsPlatform.WORKABLE,
    "smartrecruiters.com": AtsPlatform.SMARTRECRUITERS,
}
# Юридичні форми в кінці назви компанії: у листах їх зазвичай нема.
LEGAL_SUFFIX = re.compile(
    r"[\s,]+(?:inc|ltd|llc|gmbh|ag|plc|s\.?l\.?u?|s\.?a\.?|b\.?v\.?|oy|ab|as|se)\.?$",
    re.IGNORECASE,
)
BRACKETS = re.compile(r"\s*[(\[][^)\]]*[)\]]")


class ReplyType(StrEnum):
    AUTO_CONFIRMATION = "auto_confirmation"
    REJECTION = "rejection"
    INVITATION = "invitation"
    ASSIGNMENT = "assignment"
    OTHER = "other"


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class MatchedBy(StrEnum):
    """Чим лист зіставився з вакансією: тред, адреса чи домен компанії, ATS-відправник з
    назвою компанії або лише назва компанії в листі."""

    THREAD = "thread"
    EMAIL = "email"
    DOMAIN = "domain"
    ATS = "ats"
    NAME = "name"


# Куди веде статус підтверджений тип; None — не змінює.
REVIEW_STATUS: dict[ReplyType, ApplicationStatus | None] = {
    ReplyType.AUTO_CONFIRMATION: None,
    ReplyType.REJECTION: ApplicationStatus.REJECTED,
    ReplyType.INVITATION: ApplicationStatus.INTERVIEW,
    ReplyType.ASSIGNMENT: ApplicationStatus.INTERVIEW,
    ReplyType.OTHER: ApplicationStatus.REPLIED,
}

# Підказки типу за текстом EN / ES — у порядку перевірки: відмова часто дякує за подачу, а
# запрошення — починається з «thanks for applying».
TYPE_PATTERNS: tuple[tuple[ReplyType, re.Pattern[str]], ...] = tuple(
    (reply_type, re.compile("|".join(patterns), re.IGNORECASE))
    for reply_type, patterns in (
        (
            ReplyType.REJECTION,
            (
                r"\bunfortunately\b",
                r"\bregret to inform\b",
                r"\bnot (?:be )?moving forward\b",
                r"\bdecided (?:not to|to move forward with other|to pursue other)",
                r"\bnot (?:to )?(?:proceed|continue) with your\b",
                r"\bposition has (?:now )?been filled\b",
                r"\bno longer (?:under consideration|being considered)\b",
                r"\blamentablemente\b",
                r"\bdesafortunadamente\b",
                r"\bsentimos (?:comunicarte|informarte)\b",
                r"\bno (?:vamos a|podemos) (?:continuar|seguir|avanzar)\b",
                r"\bseguir (?:adelante )?con otr[oa]s candidat",
                r"\bno has? sido seleccionad[oa]\b",
            ),
        ),
        (
            ReplyType.ASSIGNMENT,
            (
                r"\btake[- ]home\b",
                r"\bcoding (?:challenge|exercise|test|assignment)\b",
                r"\btechnical (?:test|assessment|challenge|exercise|assignment)\b",
                r"\bhome assignment\b",
                r"\b(?:hackerrank|codility|codesignal|testgorilla)\b",
                r"\bprueba técnica\b",
                r"\b(?:ejercicio|reto) técnico\b",
            ),
        ),
        (
            ReplyType.INVITATION,
            (
                r"\bschedule (?:a|an|some) (?:call|chat|interview|meeting|time)\b",
                r"\b(?:share|send|let us know|provide) (?:me |us )?your availability\b",
                r"\binvite you (?:to|for)\b",
                r"\bbook (?:a|some) time\b",
                r"\b(?:calendly\.com|cal\.com|goodtime\.io)\b",
                r"\bnext step (?:is|would be)\b",
                r"\bentrevista con\b",
                r"\bagendar\b",
                r"\b(?:tu|su) disponibilidad\b",
                r"\bte invitamos\b",
                r"\bsiguiente paso (?:es|será|sería)\b",
            ),
        ),
        (
            ReplyType.AUTO_CONFIRMATION,
            (
                r"\bthanks? (?:you )?for (?:applying|your application)\b",
                r"\b(?:we(?:'ve| have)|has been) received (?:your|the) application\b",
                r"\bapplication (?:has been |was )?(?:received|submitted)\b",
                r"\bgracias por (?:tu|su) (?:candidatura|solicitud|aplicación)\b",
                r"\bgracias por (?:postularte|aplicar|inscribirte)\b",
                r"\bhemos recibido (?:tu|su) (?:candidatura|solicitud|cv)\b",
            ),
        ),
    )
)


@dataclass(frozen=True, slots=True)
class ReplyMail:
    """Лист компанії, як його бачить зіставлення: заголовки треду, відправник, тема, текст."""

    id: int
    received_at: datetime
    message_id: str = ""
    in_reply_to: str = ""
    references: tuple[str, ...] = ()
    from_address: str = ""
    from_name: str = ""
    subject: str = ""
    text: str = ""
    sender_auth: SenderAuth = SenderAuth.UNKNOWN

    @property
    def thread_ids(self) -> tuple[str, ...]:
        """Message-ID попередніх листів треду."""
        return tuple(filter(None, (self.in_reply_to, *self.references)))


@dataclass(frozen=True, slots=True)
class AppliedJob:
    """Вакансія, на яку користувач подався, — кандидат для зіставлення."""

    job_number: int
    title: str | None
    company: str | None
    status: ApplicationStatus
    ats: AtsPlatform | None = None
    company_domains: tuple[str, ...] = ()
    company_emails: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReplyMatch:
    """Знайдена вакансія; job_number None — лист ні з чим не зіставився."""

    job_number: int | None = None
    confidence: Confidence | None = None
    matched_by: MatchedBy | None = None

    @property
    def confident(self) -> bool:
        return self.confidence in {Confidence.HIGH, Confidence.MEDIUM}


@dataclass(frozen=True, slots=True)
class ReplyJob:
    job_number: int
    title: str | None
    company: str | None
    status: ApplicationStatus | None


@dataclass(frozen=True, slots=True)
class Reply:
    """Лист компанії з його зіставленням і розбором."""

    id: int
    mail: MailSummary
    text: str
    job: ReplyJob | None
    confidence: Confidence | None
    matched_by: MatchedBy | None
    suggested_type: ReplyType
    type: ReplyType | None = None
    reviewed_at: datetime | None = None
    # Ручне пересилання власником (domain.mail.forwarded): відправник і тема з блоку.
    forwarded: ForwardedMail | None = None


def match_reply(
    mail: ReplyMail, applied: Sequence[AppliedJob], thread_job: int | None
) -> ReplyMatch:
    """Вакансія для листа серед подач того самого користувача. Сильніша ознака перемагає:
    тред → адреса → домен компанії → ATS-відправник з назвою компанії → лише назва. Кілька
    подач з однією ознакою розрізняє посада в темі чи тексті."""
    if thread_job is not None and any(job.job_number == thread_job for job in applied):
        return ReplyMatch(thread_job, Confidence.HIGH, MatchedBy.THREAD)
    sender = mail.from_address
    domain = sender.rpartition("@")[2]
    platform = ats_platform(domain)
    for matched_by, found in (
        (MatchedBy.EMAIL, [job for job in applied if sender in job.company_emails]),
        (
            MatchedBy.DOMAIN,
            [
                job
                for job in applied
                if any(_within(domain, own) for own in job.company_domains)
            ],
        ),
        (
            MatchedBy.ATS,
            [
                job
                for job in applied
                if platform is not None
                and job.ats == platform
                and _mentions(mail, job.company)
            ],
        ),
        (MatchedBy.NAME, [job for job in applied if _mentions(mail, job.company)]),
    ):
        if found:
            return _pick(mail, found, matched_by)
    return ReplyMatch()


def ats_platform(domain: str) -> AtsPlatform | None:
    return next(
        (
            platform
            for own, platform in ATS_SENDER_DOMAINS.items()
            if _within(domain, own)
        ),
        None,
    )


def suggest_type(subject: str, text: str) -> ReplyType:
    """Тип за ключовими словами теми й тексту (EN / ES); процитований лист («> …») не враховується."""
    own = (line for line in text.splitlines() if not line.lstrip().startswith(">"))
    content = "\n".join((subject, *own))
    return next(
        (kind for kind, pattern in TYPE_PATTERNS if pattern.search(content)),
        ReplyType.OTHER,
    )


def auto_status(
    match: ReplyMatch, suggested: ReplyType, sender_auth: SenderAuth
) -> ApplicationStatus | None:
    """Сам статус — лише replied, лише за впевненого збігу, не для автопідтвердження і лише
    для листа від підтвердженого відправника (verified)."""
    if (
        sender_auth is SenderAuth.VERIFIED
        and match.confident
        and suggested is not ReplyType.AUTO_CONFIRMATION
    ):
        return ApplicationStatus.REPLIED
    return None


def parse_reply_type(value: str) -> ReplyType:
    try:
        return ReplyType(value.strip())
    except ValueError as exc:
        allowed = ", ".join(kind.value for kind in ReplyType)
        raise InvalidValue("type", f"Тип відповіді — один з: {allowed}.") from exc


def review_target(
    kind: ReplyType, current: ApplicationStatus
) -> ApplicationStatus | None:
    """Куди розбір цього типу веде подачу зі статусу `current`; None — статус лишається (тип
    статус не рухає, або перехід був би назад чи з закритої подачі)."""
    target = REVIEW_STATUS[kind]
    if target is not None and target in TRANSITIONS[current]:
        return target
    return None


def check_replies_limit(limit: int) -> None:
    if not 1 <= limit <= MAX_REPLIES_LIMIT:
        raise InvalidValue("limit", f"limit — від 1 до {MAX_REPLIES_LIMIT}.")


def _pick(
    mail: ReplyMail, found: list[AppliedJob], matched_by: MatchedBy
) -> ReplyMatch:
    """Одна подача — впевнено (лише назва компанії — ніколи); кілька — посада в листі
    вибирає одну (середня впевненість), інакше найсвіжіша подача з низькою."""
    if matched_by is MatchedBy.NAME:
        titled = [job for job in found if _mentions_title(mail, job.title)]
        return ReplyMatch((titled or found)[0].job_number, Confidence.LOW, matched_by)
    if len(found) == 1:
        return ReplyMatch(found[0].job_number, Confidence.HIGH, matched_by)
    titled = [job for job in found if _mentions_title(mail, job.title)]
    if len(titled) == 1:
        return ReplyMatch(titled[0].job_number, Confidence.MEDIUM, matched_by)
    return ReplyMatch(found[0].job_number, Confidence.LOW, matched_by)


def _within(domain: str, own: str) -> bool:
    return domain == own or domain.endswith(f".{own}")


def _mentions(mail: ReplyMail, company: str | None) -> bool:
    """Назва компанії (без юридичної форми) окремим словом в імені відправника, темі чи тексті."""
    name = LEGAL_SUFFIX.sub("", " ".join((company or "").split()))
    if not name:
        return False
    return _contains(f"{mail.from_name}\n{mail.subject}\n{mail.text}", name)


def _mentions_title(mail: ReplyMail, title: str | None) -> bool:
    """Посада (без уточнень у дужках) у темі чи тексті."""
    name = BRACKETS.sub("", " ".join((title or "").split()))
    return bool(name) and _contains(f"{mail.subject}\n{mail.text}", name)


def _contains(haystack: str, phrase: str) -> bool:
    words = r"\s+".join(re.escape(word) for word in phrase.split())
    pattern = rf"(?<!\w){words}(?!\w)"
    return re.search(pattern, haystack, re.IGNORECASE) is not None
