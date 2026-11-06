"""Тріаж без LLM: скор за рубрикою аналізу (40 / 20 / 15 / 10 / 10 / 5) із доказів у тексті вакансії,
профілю й підтверджених фактів; вердикт і причина. Чисті функції без IO."""

import hashlib
import json
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from enum import StrEnum

from domain.analysis.analysis import work_mode_flag
from domain.jobs.job import Job
from domain.profile.modes import WorkMode
from domain.profile.profile import Profile
from domain.sources.filtering import (
    FEED_SOURCE_PREFIX,
    HYBRID_STEMS,
    REMOTE_STEMS,
    Skip,
    stored_skip_reason,
)
from domain.sources.fold import fold, has_phrase, has_stem
from domain.triage.evidence import (
    Requirements,
    extract_requirements,
    find_domains,
    parse_salary_eur,
    seniority_from_title,
    terms_in_facts,
)
from domain.triage.triage import TriageVerdict

# Пороги вердикту: підбираються після `--report` (K-P).
ANALYSE_SCORE = 55
SKIP_SCORE = 40
# Версія правил тріажу: підняти, коли зміна калібрування має перерахувати збережений тріаж `rules`.
RULES_VERSION = 2
# Скільки розпізнаних вимог (must + nice) потрібно, щоб радити повний аналіз.
MIN_RECOGNISED = 3

MUST_POINTS = 40
# Обов'язкових вимог у тексті не розпізнано: нейтральна половина балів, а не нуль.
MUST_NEUTRAL_POINTS = 20
ROLE_POINTS = 12
# Назва не збігається з роллю, але має слово з `title_keywords` профілю й жодного з `title_exclude`.
ROLE_KEYWORD_POINTS = 8
LEVEL_POINTS = 8
# Рівень у назві не названо: половина балів за рівень.
LEVEL_UNKNOWN_POINTS = 4
FORMAT_POINTS = 15
# Формат не названо, але профіль пропускає невідомий формат.
FORMAT_UNKNOWN_POINTS = 8
DOMAIN_POINTS = 5
MAX_DOMAIN_POINTS = 10
NICE_POINTS = 10
SALARY_POINTS = 5
SALARY_UNSTATED_POINTS = 2
# Скільки невідповідних вимог названо в причині.
MAX_MISSING_LISTED = 3
# Роздільники полів у відбитку: службові символи, яких нема в тексті вакансій.
CONTEXT_SEPARATOR = "\x1e"
FIELD_SEPARATOR = "\x1f"


class Mismatch(StrEnum):
    """Жорстка невідповідність профілю; значення потрапляє в причину."""

    FORMAT = "формат чи локація"
    LEVEL = "рівень"
    EXCLUDED_WORD = "слово з виключень у назві"
    SALARY = "зарплата нижче мінімуму"
    STOP_WORD = "стоп-слово"


@dataclass(frozen=True, slots=True)
class Breakdown:
    """З чого складено скор: бали за складниками рубрики й лічильники вимог. Сума балів = скор."""

    must: int = 0
    role_level: int = 0
    format_location: int = 0
    domain: int = 0
    nice: int = 0
    salary: int = 0
    must_recognised: int = 0
    must_backed: int = 0
    nice_recognised: int = 0
    nice_backed: int = 0
    mismatches: tuple[Mismatch, ...] = ()


@dataclass(frozen=True, slots=True)
class AutoTriage:
    """Тріаж за правилами однієї вакансії. `breakdown` лише пояснює скор і в порівняння не входить."""

    score: int
    verdict: TriageVerdict
    reason: str
    breakdown: Breakdown = field(default_factory=Breakdown, compare=False)


def offered_modes(texts: Iterable[str]) -> frozenset[WorkMode]:
    """Формати, які вакансія пропонує за словами в тексті (EN / UK / RU): усі названі, а не один
    сильніший («віддалено, гібрид у Барселоні» — обидва). Нічого не сказано — порожня множина."""
    folded = " ".join(fold(text) for text in texts)
    stems = {WorkMode.REMOTE: REMOTE_STEMS, WorkMode.HYBRID: HYBRID_STEMS}
    return frozenset(
        mode
        for mode, words in stems.items()
        if any(has_stem(folded, stem) for stem in words)
    )


def verdict_for(score: int) -> TriageVerdict:
    """Вердикт лише за скором (без жорстких невідповідностей): для звіту проти аналізів."""
    if score >= ANALYSE_SCORE:
        return TriageVerdict.ANALYSE
    if score < SKIP_SCORE:
        return TriageVerdict.SKIP
    return TriageVerdict.MAYBE


def auto_triage(job: Job, profile: Profile, facts: Sequence[str]) -> AutoTriage:
    """Скор, вердикт і причина вакансії. `facts` — тексти підтверджених фактів користувача:
    вимога підкріплена, якщо її термін згадано в якомусь факті."""
    title, text = job.title or "", job.text or ""
    requirements = extract_requirements(text)
    backed_terms = set(terms_in_facts(facts))
    backed = [term for term in requirements.must if term in backed_terms]
    missing = [term for term in requirements.must if term not in backed_terms]
    nice_backed = [term for term in requirements.nice if term in backed_terms]

    mismatches = _mismatches(job, profile)
    breakdown = Breakdown(
        must=_must_points(len(backed), len(requirements.must)),
        role_level=_role_points(title, profile)
        + _level_points(title, profile, Mismatch.LEVEL in mismatches),
        format_location=_format_points(job, profile, Mismatch.FORMAT in mismatches),
        domain=min(
            len(find_domains(f"{title} {text}", profile.target.target_domains))
            * DOMAIN_POINTS,
            MAX_DOMAIN_POINTS,
        ),
        nice=_share(len(nice_backed), len(requirements.nice), NICE_POINTS),
        salary=_salary_points(text, profile, Mismatch.SALARY in mismatches),
        must_recognised=len(requirements.must),
        must_backed=len(backed),
        nice_recognised=len(requirements.nice),
        nice_backed=len(nice_backed),
        mismatches=tuple(mismatches),
    )
    score = (
        breakdown.must
        + breakdown.role_level
        + breakdown.format_location
        + breakdown.domain
        + breakdown.nice
        + breakdown.salary
    )
    recognised = len(requirements.must) + len(requirements.nice)
    if mismatches:
        verdict = TriageVerdict.SKIP
    elif recognised < MIN_RECOGNISED:
        # Замало вимог у тексті, щоб судити за скором: найбільше «невпевнено».
        verdict = TriageVerdict.MAYBE
    else:
        verdict = verdict_for(score)
    return AutoTriage(
        score,
        verdict,
        _reason(verdict, mismatches, len(backed), requirements, missing),
        breakdown,
    )


def context_digest(profile: Profile, facts: Sequence[str]) -> str:
    """Відбиток того, що від вакансії не залежить: профіль (ціль, локації, правила) і підтверджені факти."""
    state = {
        "target": asdict(profile.target),
        "locations": asdict(profile.locations),
        "rules": asdict(profile.rules),
        "facts": sorted(facts),
    }
    # Множини (формати, рівні) — відсортованими списками: порядок у них не визначений.
    encoded = json.dumps(
        state, default=sorted, sort_keys=True, ensure_ascii=False
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def inputs_hash(context: str, job: Job) -> str:
    """Відбиток усіх вхідних даних тріажу вакансії: `RULES_VERSION`, `context_digest`, назва, локація
    й текст. Те саме обчислює SQL у `PostgresTriage.auto_candidates`: зміни тут і там разом."""
    fields = FIELD_SEPARATOR.join(
        part for part in (job.title, job.location, job.text) if part is not None
    )
    joined = f"{RULES_VERSION}{CONTEXT_SEPARATOR}{context}{CONTEXT_SEPARATOR}{fields}"
    return hashlib.sha256(joined.encode()).hexdigest()


def _share(backed: int, total: int, points: int) -> int:
    return round(points * backed / total) if total else 0


def _must_points(backed: int, total: int) -> int:
    return _share(backed, total, MUST_POINTS) if total else MUST_NEUTRAL_POINTS


def _role_points(title: str, profile: Profile) -> int:
    """Усі слова однієї з ролей профілю є в назві; ролей у профілі нема — обмеження нема.
    Інакше частково: у назві є слово з `title_keywords` і нема жодного з `title_exclude`."""
    roles = profile.target.roles
    if not roles:
        return ROLE_POINTS
    folded = fold(title)
    for role in roles:
        words = fold(role).split()
        if words and all(has_phrase(folded, word) for word in words):
            return ROLE_POINTS
    rules = profile.rules
    keyword = any(has_phrase(folded, fold(word)) for word in rules.title_keywords)
    excluded = any(has_phrase(folded, fold(word)) for word in rules.title_exclude)
    return ROLE_KEYWORD_POINTS if keyword and not excluded else 0


def _level_points(title: str, profile: Profile, mismatch: bool) -> int:
    if mismatch:
        return 0
    if not profile.target.seniority:
        return LEVEL_POINTS
    return LEVEL_POINTS if seniority_from_title(title) else LEVEL_UNKNOWN_POINTS


def _format_points(job: Job, profile: Profile, mismatch: bool) -> int:
    if mismatch:
        return 0
    if offered_modes([job.location or "", job.text or ""]):
        return FORMAT_POINTS
    return FORMAT_UNKNOWN_POINTS if profile.locations.include_unknown_mode else 0


def _salary_points(text: str, profile: Profile, mismatch: bool) -> int:
    if mismatch:
        return 0
    return SALARY_POINTS if parse_salary_eur(text) else SALARY_UNSTATED_POINTS


def _mismatches(job: Job, profile: Profile) -> list[Mismatch]:
    """Жорсткі невідповідності профілю: формат чи локація, рівень, слово з виключень у назві, зарплата, стоп-слово."""
    found: list[Mismatch] = []
    skip = stored_skip_reason(job, profile)
    if _format_mismatch(job, profile, skip):
        found.append(Mismatch.FORMAT)
    title = job.title or ""
    level = seniority_from_title(title)
    if profile.target.seniority and level and level not in profile.target.seniority:
        found.append(Mismatch.LEVEL)
    if skip is Skip.EXCLUDED:
        found.append(Mismatch.EXCLUDED_WORD)
    salary = parse_salary_eur(job.text or "")
    minimum = profile.target.min_salary_eur
    if salary and minimum is not None and salary.high_eur < minimum:
        found.append(Mismatch.SALARY)
    folded = fold(f"{title} {job.text or ''}")
    if any(has_phrase(folded, fold(word)) for word in profile.rules.stop_words):
        found.append(Mismatch.STOP_WORD)
    return found


def _format_mismatch(job: Job, profile: Profile, skip: Skip | None) -> bool:
    """Невідповідність формату, лише якщо жоден з формату, що вакансія пропонує, профілю не підходить.
    Формат вирішує те саме правило, що й жорсткі фільтри аналізу (`work_mode_flag`); віддалена
    пропозиція проходить у будь-якому місці, а на місці, гібрид чи невідомий формат мусять ще й
    збігтися з місцем профілю (`skip` — `Skip.LOCATION`)."""
    modes = offered_modes([job.location or "", job.text or ""])
    if not modes:
        return skip is Skip.LOCATION and not _unknown_feed_location(job, profile)
    return not any(_acceptable(mode, profile, skip) for mode in modes)


def _unknown_feed_location(job: Job, profile: Profile) -> bool:
    """Стрічка не віддала локацію й текст не називає формату: невідомо, а не невідповідність
    (якщо профіль пропускає невідомий формат)."""
    return (
        job.source.startswith(FEED_SOURCE_PREFIX)
        and not job.location
        and profile.locations.include_unknown_mode
    )


def _acceptable(mode: WorkMode, profile: Profile, skip: Skip | None) -> bool:
    if work_mode_flag(mode, profile):
        return False
    return mode is WorkMode.REMOTE or skip is not Skip.LOCATION


def _reason(
    verdict: TriageVerdict,
    mismatches: list[Mismatch],
    backed: int,
    requirements: Requirements,
    missing: list[str],
) -> str:
    if mismatches:
        return f"Не підходить: {', '.join(m.value for m in mismatches)}."
    total = len(requirements.must)
    recognised = total + len(requirements.nice)
    counted = (
        f"підкріплено {backed} з {total} обов'язкових вимог"
        if total
        else "вимог не розпізнано"
    )
    if verdict is TriageVerdict.ANALYSE:
        return f"Підходить: {counted}."
    if verdict is TriageVerdict.SKIP:
        return f"Слабкий збіг: {counted}."
    gaps = f"; бракує {', '.join(missing[:MAX_MISSING_LISTED])}" if missing else ""
    if recognised < MIN_RECOGNISED:
        few = f"у тексті мало вимог (розпізнано {recognised})"
        return (
            f"Невпевнено: {few}; {counted}{gaps}." if total else f"Невпевнено: {few}."
        )
    return f"Невпевнено: {counted}{gaps}."
