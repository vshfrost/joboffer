"""Посилання LinkedIn на вакансію (id, канонічний вигляд) і листи-алерти LinkedIn: дайджест
вакансій розбирається у вакансії без опису. Лист — недовірені дані третіх сторін: посади й
компанії зберігаються як текст, опису в листі нема, лише посилання."""

import re
from dataclasses import dataclass

# Посилання на вакансію в будь-якій формі: /jobs/view/<id>, /comm/jobs/view/<id>,
# /jobs/view/<slug>-<id>, з трекінгом, будь-який піддомен країни.
_JOB_LINK = re.compile(
    r"https?://(?:[\w-]+\.)?linkedin\.com/(?:comm/)?jobs/view/(?:[^/?#\s]*?-)?(\d{6,})(?![\w-])\S*",
    re.IGNORECASE,
)

# Джерело вакансій, створених із листів-алертів (`jobs.source`).
ALERT_SOURCE = "linkedin_alert"
# Роздільник блоків у дайджесті: рядок із самих дефісів.
_SEPARATOR = re.compile(r"-{5,}")
# Посада, компанія й локація — перші три рядки блоку вакансії; далі йдуть примітки LinkedIn
# («Подати заявку …») і посилання.
_HEAD_LINES = 3
MAX_FIELD_LENGTH = 300


def linkedin_job_id(url: str) -> str | None:
    """LinkedIn id вакансії з посилання `jobs/view/<id>` у будь-якій формі; інакше None."""
    found = _JOB_LINK.search(url)
    return None if found is None else found.group(1)


def linkedin_job_url(job_id: str) -> str:
    """Канонічне посилання вакансії: без /comm/, slug-а й трекінгу."""
    return f"https://www.linkedin.com/jobs/view/{job_id}"


@dataclass(frozen=True, slots=True)
class AlertJob:
    """Вакансія з листа-алерту; опису нема."""

    linkedin_id: str
    title: str
    company: str | None
    location: str | None

    @property
    def url(self) -> str:
        return linkedin_job_url(self.linkedin_id)


@dataclass(frozen=True, slots=True)
class AlertParse:
    """Вакансії листа (без повторів id, у порядку листа) і скільки блоків із посиланням на
    вакансію не вдалося розібрати (невідомий шаблон)."""

    jobs: tuple[AlertJob, ...] = ()
    unparsed: int = 0

    @property
    def error(self) -> str:
        """Позначка для листа; порожньо — усе розібрано й вакансії знайдено."""
        if self.unparsed:
            return f"linkedin_alert: не розібрано блоків вакансій — {self.unparsed}"
        if not self.jobs:
            return "linkedin_alert: вакансій не знайдено (невідомий шаблон)"
        return ""


def parse_job_alert(text: str) -> AlertParse:
    """Вакансії з тексту листа-алерту; розбір за структурою, тож не залежить від мови листа.

    Вакансії відділяють рядки з дефісів; блок — абзаци (розділені порожніми рядками) між
    роздільниками, а в ньому рівно одне посилання на вакансію. Якщо текст листа починається
    одразу з абзацу вакансії, його перший рядок — заголовок дайджесту, а не посада. Посада, компанія й локація —
    перші три рядки абзацу з вакансією: це абзац із посиланням, якщо в ньому щонайменше 4 рядки,
    інакше (посилання стоїть в абзаці приміток) — попередній абзац того ж блоку."""
    jobs: dict[str, AlertJob] = {}
    unparsed = 0
    for position, block in enumerate(_blocks(text)):
        links = [
            line for paragraph in block for line in paragraph if _JOB_LINK.search(line)
        ]
        if not links:
            continue
        job = _job(block, first=position == 0) if len(links) == 1 else None
        if job is None:
            unparsed += 1
        else:
            jobs.setdefault(job.linkedin_id, job)
    return AlertParse(tuple(jobs.values()), unparsed)


def _blocks(text: str) -> list[list[list[str]]]:
    """Блоки між роздільниками: список абзаців, абзац — список непорожніх рядків."""
    blocks: list[list[list[str]]] = [[]]
    paragraph: list[str] = []
    for raw in [*text.splitlines(), ""]:
        line = raw.strip()
        if line:
            paragraph.append(line)
        elif paragraph:
            if len(paragraph) == 1 and _SEPARATOR.fullmatch(paragraph[0]):
                blocks.append([])
            else:
                blocks[-1].append(paragraph)
            paragraph = []
    return blocks


def _job(block: list[list[str]], *, first: bool) -> AlertJob | None:
    index = next(
        i
        for i, paragraph in enumerate(block)
        if any(_JOB_LINK.search(line) for line in paragraph)
    )
    link_paragraph = block[index]
    if first and index == 0:
        # Текст листа починається з абзацу вакансії: перший рядок — заголовок дайджесту
        # («Сповіщення про вакансії за запитом …») без порожнього рядка перед вакансією.
        link_paragraph = link_paragraph[1:]
    if len(link_paragraph) > _HEAD_LINES:
        head = link_paragraph
    elif index > 0 and len(block[index - 1]) >= _HEAD_LINES:
        head = block[index - 1]
    else:
        return None
    link = next(line for line in link_paragraph if _JOB_LINK.search(line))
    job_id = linkedin_job_id(link)
    title, company, location = head[:_HEAD_LINES]
    if job_id is None or _JOB_LINK.search(title):
        return None
    return AlertJob(
        linkedin_id=job_id,
        title=_field(title),
        company=_field(company) or None,
        location=_field(location) or None,
    )


def _field(value: str) -> str:
    """Пробіли зведено до одного, довжина не більша за MAX_FIELD_LENGTH."""
    return " ".join(value.split())[:MAX_FIELD_LENGTH]
