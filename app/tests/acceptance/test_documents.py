"""Кроки для features/documents_*.feature: use cases документів, вакансій, фактів, профілю й аналізу + in-memory адаптери
і фейки виходу (рендер, перевірка PDF, файли) через портал.

Усі значення в кроках — у лапках, тож кроки — регулярні вирази з іменованими групами. «Припустимо я зберіг …» і
«Якщо я зберігаю …» — один і той самий крок; у «Припустимо» додатково перевіряється, що дія вдалася. Вакансія — за
номером на користувача (`job_id`), документ — за номером на користувача (`document_id`), факт — за номером (`fact_id`);
внутрішні UUID у сценаріях не фігурують. Документи пишуться «на фактах "1; 2"» — усі рядки CV цитують ці факти.
"""

import functools
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from anyio.from_thread import BlockingPortal
from pytest_bdd import given as bdd_given
from pytest_bdd import parsers, scenarios
from pytest_bdd import then as bdd_then
from pytest_bdd import when as bdd_when

from application.analysis.use_cases import AnalysisUseCases
from application.contracts.actor import Actor, Channel, Scope
from application.contracts.analysis import AnalysisInput
from application.contracts.documents import (
    CheckData,
    ClaimData,
    CoverLetterBriefData,
    CoverLetterData,
    CvBriefData,
    CvData,
    CvEntryData,
    CvSectionData,
    DocumentData,
    JobDocumentData,
    PdfFileData,
    PruneData,
)
from application.contracts.jobs import JobInput
from application.contracts.profile import ContactsData
from application.documents.parsing import parse_cover_letter, parse_cv
from application.documents.use_cases import DocumentUseCases
from application.jobs.use_cases import JobUseCases
from application.ports.prompts import PromptKey
from application.profile.use_cases import ProfileUseCases
from domain.documents.document import DocumentKind
from domain.documents.ids import DocumentId
from domain.facts.fact import NewFact
from domain.facts.ids import FactId
from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.jobs.job import NewJob
from domain.profile.profile import Profile
from domain.shared.errors import DomainError
from tests.support.analysis import InMemoryAnalysisUnitOfWork
from tests.support.clock import FakeClock
from tests.support.documents import DocumentStore, InMemoryDocumentUnitOfWork
from tests.support.facts import InMemoryFactUnitOfWork
from tests.support.facts import Store as FactStore
from tests.support.ids import SequentialIds
from tests.support.jobs import InMemoryJobUnitOfWork, Store
from tests.support.pdf import Shop, with_hidden_text, with_pages
from tests.support.profile import InMemoryProfileUnitOfWork

scenarios(
    "features/documents_brief.feature",
    "features/documents_save.feature",
    "features/documents_letter.feature",
    "features/documents_versions.feature",
    "features/documents_pdf.feature",
    "features/documents_users.feature",
    "features/documents_check.feature",
    "features/documents_replace.feature",
    "features/documents_prune.feature",
)

Step = Callable[..., Any]

CV_RULES = "CV rules."
LETTER_RULES = "Cover letter rules."
RUBRIC = "Rubric for {candidate}{domain_examples}."
KINDS = {"cv": DocumentKind.CV, "cl": DocumentKind.COVER_LETTER}


class FakePrompts:
    def get(self, key: PromptKey) -> str:
        return {
            PromptKey.DOCUMENTS_CV_RULES: CV_RULES,
            PromptKey.DOCUMENTS_COVER_LETTER_RULES: LETTER_RULES,
            PromptKey.ANALYSIS_RUBRIC: RUBRIC,
        }[key]


def rx(pattern: str) -> Any:
    return parsers.re(pattern)


def succeeded(step: Step) -> Step:
    """Крок-передумова: дія має вдатися, інакше сценарій не про те."""

    @functools.wraps(step)
    def wrapper(*args: Any, **kwargs: Any) -> None:
        step(*args, **kwargs)
        world: World = kwargs["world"]
        assert world.error is None, world.error

    return wrapper


def setup(pattern: str) -> Callable[[Step], Step]:
    """Передумова, що читається і після «Припустимо», і після «Якщо» (через «І»)."""

    def decorate(step: Step) -> Step:
        bdd_given(rx(pattern), stacklevel=2)(step)
        bdd_when(rx(pattern), stacklevel=2)(step)
        return step

    return decorate


def action(pattern: str) -> Callable[[Step], Step]:
    """Один текст — і «Припустимо я зробив …», і «Якщо я роблю …»."""

    def decorate(step: Step) -> Step:
        bdd_given(rx(pattern), stacklevel=2)(succeeded(step))
        bdd_when(rx(pattern), stacklevel=2)(step)
        return step

    return decorate


def words(text: str) -> list[str]:
    """Елементи через «;»: порожній рядок — порожній список."""
    return [] if text.strip() == "" else [part.strip() for part in text.split(";")]


def numbers(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in words(text))


class World:
    def __init__(
        self, portal: BlockingPortal, clock: FakeClock, ids: SequentialIds
    ) -> None:
        self.portal = portal
        self.clock = clock
        self.ids = ids
        self.jobs_store = Store.empty()
        self.facts_store = FactStore.empty()
        self.docs_store = DocumentStore.empty()
        self.profiles: dict[UserId, Profile] = {}
        self.pdf = Shop()
        prompts = FakePrompts()
        self.documents = DocumentUseCases(
            lambda: InMemoryDocumentUnitOfWork(
                self.jobs_store, self.docs_store, self.facts_store, self.profiles
            ),
            clock,
            ids,
            prompts,
            self.pdf.output(),
        )
        self.jobs = JobUseCases(
            lambda: InMemoryJobUnitOfWork(self.jobs_store), clock, ids
        )
        self.analysis = AnalysisUseCases(
            lambda: InMemoryAnalysisUnitOfWork(
                self.jobs_store, self.facts_store, self.profiles, {}
            ),
            clock,
            ids,
            prompts,
        )
        self.profile = ProfileUseCases(
            lambda: InMemoryProfileUnitOfWork(self.profiles, {}, {}), clock
        )
        self.actors: dict[str, Actor] = {}
        self.contacts: dict[str, dict[str, str]] = {}
        self.current = ""
        self.error: DomainError | None = None
        # Збій інфраструктури (рендер, диск): не помилка домену, а виняток адаптера.
        self.crash: Exception | None = None
        self.saved: DocumentData | None = None
        self.cv_brief: CvBriefData | None = None
        self.letter_brief: CoverLetterBriefData | None = None
        self.listed: tuple[DocumentData, ...] | None = None
        self.web_list: tuple[JobDocumentData, ...] | None = None
        self.pdf_file: PdfFileData | None = None
        self.checked: CheckData | None = None
        self.pruned: PruneData | None = None

    # --- користувачі й результат останньої дії ---------------------------------------------

    def become(self, name: str) -> None:
        if name not in self.actors:
            self.actors[name] = Actor(
                user_id=UserId(self.ids.new()),
                channel=Channel.WEB,
                client_id="web",
                grant_id=None,
                scopes=frozenset(Scope),
                correlation_id="test",
            )
            self.contacts[name] = {}
        self.current = name
        self.reset_outcome()

    @property
    def actor(self) -> Actor:
        return self.actors[self.current]

    def reset_outcome(self) -> None:
        self.error = None
        self.crash = None
        self.saved = None
        self.cv_brief = None
        self.letter_brief = None
        self.listed = None
        self.web_list = None
        self.pdf_file = None
        self.checked = None
        self.pruned = None

    def attempt(self, call: Callable[[], Any]) -> Any:
        """Виконує дію; помилка домену запамʼятовується для кроків «Тоді»."""
        self.reset_outcome()
        try:
            return self.portal.call(call)
        except DomainError as error:
            self.error = error
            return None
        except (RuntimeError, OSError) as failure:
            self.crash = failure
            return None

    # --- передумови ------------------------------------------------------------------------

    def add_job(self, title: str, text: str | None) -> None:
        if text is None:
            self.seed_alert(title)
            return
        data = JobInput(text=text, title=title, company="Acme")
        self.attempt(lambda: self.jobs.add_job(self.actor, data))
        assert self.error is None, self.error

    def seed_alert(self, title: str) -> None:
        """Вакансія з листа-алерту без тексту: її створить B10, тут — передумова."""

        async def seed() -> None:
            async with InMemoryJobUnitOfWork(self.jobs_store) as uow:
                await uow.jobs.add(
                    self.actor.user_id,
                    JobId(self.ids.new()),
                    NewJob(text=None, title=title),
                    self.clock.now(),
                )
                await uow.commit()

        self.portal.call(seed)

    def add_fact(self, kind: str, text: str, confirmed: bool) -> None:
        async def add() -> None:
            async with InMemoryFactUnitOfWork(self.facts_store) as uow:
                added = await uow.facts.add(
                    self.actor.user_id,
                    FactId(self.ids.new()),
                    NewFact.parse(kind=kind, text=text),
                    self.clock.now(),
                )
                if confirmed:
                    await uow.facts.confirm(
                        self.actor.user_id, [added.number], self.clock.now()
                    )
                await uow.commit()

        self.portal.call(add)

    def set_contacts(self, **fields: str) -> None:
        state = self.contacts[self.current]
        state.update(fields)
        data = ContactsData(**state)
        self.attempt(lambda: self.profile.save_section(self.actor, data))

    def analyse(self, number: int, keywords: list[str]) -> None:
        data = AnalysisInput(score=70, summary="Підсумок.", keywords=keywords)
        self.attempt(lambda: self.analysis.save_analysis(self.actor, number, data))

    # --- документи -------------------------------------------------------------------------

    def save_cv(self, job: int, data: CvData) -> None:
        self.clock.advance(timedelta(minutes=1))
        self.saved = self.attempt(lambda: self.documents.save_cv(self.actor, job, data))

    def save_letter(self, job: int, data: CoverLetterData) -> None:
        self.clock.advance(timedelta(minutes=1))
        self.saved = self.attempt(
            lambda: self.documents.save_cover_letter(self.actor, job, data)
        )

    def check_cv(self, job: int, data: CvData) -> None:
        self.checked = self.attempt(
            lambda: self.documents.check_cv(self.actor, job, data)
        )

    def check_letter(self, job: int, data: CoverLetterData) -> None:
        self.checked = self.attempt(
            lambda: self.documents.check_cover_letter(self.actor, job, data)
        )

    def seed_versions(self, job: int, kind: DocumentKind, count: int) -> None:
        """Старі версії, які лишилися від часів, коли збереження їх не замінювало: рядки й файли
        створюються напряму, повз збереження."""
        content = (
            parse_cv(cv_data((1,)))
            if kind is DocumentKind.CV
            else parse_cover_letter(
                CoverLetterData(text=letter_text(160), fact_ids=(1,))
            )
        )

        async def seed() -> None:
            async with InMemoryDocumentUnitOfWork(
                self.jobs_store, self.docs_store, self.facts_store, self.profiles
            ) as uow:
                found = await uow.jobs.get(self.actor.user_id, job)
                assert found is not None
                for _ in range(count):
                    added = await uow.documents.add(
                        self.actor.user_id,
                        DocumentId(self.ids.new()),
                        found.id,
                        content,
                        self.clock.now(),
                    )
                    self.pdf.files[added.id] = b"%PDF-seeded"
                await uow.commit()

        self.portal.call(seed)

    def documents_of(self, job: int) -> tuple[DocumentData, ...]:
        return self.portal.call(self.documents.list_documents, self.actor, job)


def claim(text: str, facts: tuple[int, ...]) -> ClaimData:
    return ClaimData(text=text, fact_ids=facts)


def cv_data(
    facts: tuple[int, ...],
    *,
    summary: str = "Payments backend engineer",
    section: str = "Experience",
    sections: bool = True,
    bullets: int = 1,
    label: str = "Engineer · Acme",
    unfounded: bool = False,
    bullet: str | None = None,
) -> CvData:
    """CV з однією секцією: усі рядки цитують `facts` (`unfounded` — рядок без фактів, `bullet` —
    єдиний пункт із цим текстом)."""
    texts = [f"Built service {i}" for i in range(bullets)]
    entry = CvEntryData(
        heading=claim(label, facts),
        bullets=[claim(text, facts) for text in ([bullet] if bullet else texts)],
    )
    return CvData(
        headline=claim("Senior Backend Engineer", () if unfounded else facts),
        summary=claim(summary, facts),
        sections=[CvSectionData(name=section, entries=[entry])] if sections else [],
    )


def unescape(text: str) -> str:
    """У .feature невидимий символ, перенос і табуляцію пишуть послідовністю."""
    return text.replace("\\u200b", "\u200b").replace("\\n", "\n").replace("\\t", "\t")


def letter_text(total: int, signoff: str = "Best regards,\nAlex") -> str:
    """Лист із `total` слів: вітання (2), підпис і слова-наповнювач."""
    filler = total - 2 - len(signoff.split())
    return "Dear team,\n\n" + " ".join(["word"] * max(filler, 0)) + "\n\n" + signoff


@pytest.fixture
def world(portal: BlockingPortal, clock: FakeClock, ids: SequentialIds) -> World:
    return World(portal, clock, ids)


# --- хто я, час, передумови -----------------------------------------------------------------


@bdd_given(rx(r'^я — користувач "(?P<name>[^"]*)"$'))
@bdd_given(rx(r'^я стаю користувачем "(?P<name>[^"]*)"$'))
@bdd_when(rx(r'^я стаю користувачем "(?P<name>[^"]*)"$'))
def become_user(world: World, name: str) -> None:
    world.become(name)


@setup(r'^є вакансія "(?P<title>[^"]*)" з текстом "(?P<text>[^"]*)"$')
def job_with_text(world: World, title: str, text: str) -> None:
    world.add_job(title, text)


@setup(r'^є вакансія "(?P<title>[^"]*)" з листа-алерту без тексту$')
def alert_job(world: World, title: str) -> None:
    world.add_job(title, None)


@setup(
    r'^у мене є (?P<state>підтверджений|непідтверджений) факт (?P<kind>\w+) "(?P<text>[^"]*)"$'
)
def fact(world: World, state: str, kind: str, text: str) -> None:
    world.add_fact(kind, text, confirmed=state == "підтверджений")


@action(r'^я (?:задаю|задав) ім\'я "(?P<value>[^"]*)"$')
def set_name(world: World, value: str) -> None:
    world.set_contacts(full_name=value)


@action(r'^я (?:задаю|задав) місто "(?P<value>[^"]*)"$')
def set_city(world: World, value: str) -> None:
    world.set_contacts(city=value)


@action(r"^я (?:прибираю|прибрав) ім'я з профілю$")
def clear_name(world: World) -> None:
    world.set_contacts(full_name="")


@action(
    r'^вакансію (?P<job>\d+) проаналізовано з ключовими словами "(?P<keywords>[^"]*)"$'
)
def analysed(world: World, job: str, keywords: str) -> None:
    world.analyse(int(job), words(keywords))


@setup(r"^PDF матиме (?P<pages>\d+) сторін\w+$")
def pdf_pages(world: World, pages: str) -> None:
    world.pdf.tweak = with_pages(int(pages))


@setup(r'^у PDF буде прихований текст "(?P<text>[^"]*)"$')
def pdf_hidden(world: World, text: str) -> None:
    world.pdf.tweak = with_hidden_text(text)


@setup(r"^рендер PDF ламається$")
def render_breaks(world: World) -> None:
    world.pdf.fail_render = True


@setup(r"^запис файлу PDF ламається$")
def write_breaks(world: World) -> None:
    world.pdf.fail_write = True


@setup(r"^рендер і запис знову працюють$")
def everything_works(world: World) -> None:
    world.pdf.fail_render = False
    world.pdf.fail_write = False


@setup(r"^PDF знову має одну сторінку$")
def pdf_normal(world: World) -> None:
    world.pdf.tweak = lambda layer: layer


@setup(r"^файл PDF документа (?P<number>\d+) зник$")
def file_gone(world: World, number: str) -> None:
    """Зникає файл версії саме цього користувача."""
    document = world.docs_store.documents[(world.actor.user_id, int(number))]
    world.pdf.files.pop(document.id)


# --- збереження CV --------------------------------------------------------------------------


@action(
    r'^я (?:зберігаю|зберіг) CV для вакансії (?P<job>\d+) на фактах "(?P<facts>[^"]*)"$'
)
def save_cv(world: World, job: str, facts: str) -> None:
    world.save_cv(int(job), cv_data(numbers(facts)))


@action(
    r'^я (?:зберігаю|зберіг) CV для вакансії (?P<job>\d+) з підсумком "(?P<summary>[^"]*)" на фактах "(?P<facts>[^"]*)"$'
)
def save_cv_summary(world: World, job: str, summary: str, facts: str) -> None:
    # «\u200b» у сценарії — невидимий символ, який у .feature не напишеш видимим.
    world.save_cv(int(job), cv_data(numbers(facts), summary=unescape(summary)))


@bdd_when(
    rx(
        r'^я зберігаю CV для вакансії (?P<job>\d+) з пунктом "(?P<bullet>[^"]*)" на фактах "(?P<facts>[^"]*)"$'
    )
)
def save_cv_bullet(world: World, job: str, bullet: str, facts: str) -> None:
    world.save_cv(int(job), cv_data(numbers(facts), bullet=unescape(bullet)))


@bdd_when(
    rx(
        r'^я зберігаю CV для вакансії (?P<job>\d+) з підсумком із (?P<length>\d+) символ\w* на фактах "(?P<facts>[^"]*)"$'
    )
)
def save_cv_long_summary(world: World, job: str, length: str, facts: str) -> None:
    world.save_cv(int(job), cv_data(numbers(facts), summary="x" * int(length)))


@bdd_when(
    rx(
        r'^я зберігаю CV для вакансії (?P<job>\d+) із секцією "(?P<section>[^"]*)" на фактах "(?P<facts>[^"]*)"$'
    )
)
def save_cv_section(world: World, job: str, section: str, facts: str) -> None:
    world.save_cv(int(job), cv_data(numbers(facts), section=section))


@bdd_when(
    rx(
        r'^я зберігаю CV для вакансії (?P<job>\d+) без секцій на фактах "(?P<facts>[^"]*)"$'
    )
)
def save_cv_no_sections(world: World, job: str, facts: str) -> None:
    world.save_cv(int(job), cv_data(numbers(facts), sections=False))


@bdd_when(
    rx(
        r'^я зберігаю CV для вакансії (?P<job>\d+) із заголовком без фактів, решта на фактах "(?P<facts>[^"]*)"$'
    )
)
def save_cv_unfounded(world: World, job: str, facts: str) -> None:
    world.save_cv(int(job), cv_data(numbers(facts), unfounded=True))


@bdd_when(
    rx(
        r'^я зберігаю CV для вакансії (?P<job>\d+) з (?P<count>\d+) пунктами в записі на фактах "(?P<facts>[^"]*)"$'
    )
)
def save_cv_bullets(world: World, job: str, count: str, facts: str) -> None:
    world.save_cv(int(job), cv_data(numbers(facts), bullets=int(count)))


@bdd_when(
    rx(
        r'^я зберігаю CV для вакансії (?P<job>\d+) із групою скілів "(?P<label>[^"]*)" на фактах "(?P<facts>[^"]*)"$'
    )
)
def save_cv_skill_label(world: World, job: str, label: str, facts: str) -> None:
    world.save_cv(int(job), cv_data(numbers(facts), section="Skills", label=label))


# --- перевірка без збереження ---------------------------------------------------------------


@bdd_when(
    rx(r'^я перевіряю CV для вакансії (?P<job>\d+) на фактах "(?P<facts>[^"]*)"$')
)
def check_cv(world: World, job: str, facts: str) -> None:
    world.check_cv(int(job), cv_data(numbers(facts)))


@bdd_when(
    rx(
        r'^я перевіряю CV для вакансії (?P<job>\d+) з підсумком "(?P<summary>[^"]*)" на фактах "(?P<facts>[^"]*)"$'
    )
)
def check_cv_summary(world: World, job: str, summary: str, facts: str) -> None:
    world.check_cv(int(job), cv_data(numbers(facts), summary=unescape(summary)))


@bdd_when(
    rx(
        r'^я перевіряю CV для вакансії (?P<job>\d+) з пунктом "(?P<bullet>[^"]*)" на фактах "(?P<facts>[^"]*)"$'
    )
)
def check_cv_bullet(world: World, job: str, bullet: str, facts: str) -> None:
    world.check_cv(int(job), cv_data(numbers(facts), bullet=unescape(bullet)))


@bdd_when(
    rx(
        r'^я перевіряю лист для вакансії (?P<job>\d+) із (?P<words>\d+) слів на фактах "(?P<facts>[^"]*)"$'
    )
)
def check_letter(world: World, job: str, words: str, facts: str) -> None:
    text = letter_text(int(words))
    world.check_letter(int(job), CoverLetterData(text=text, fact_ids=numbers(facts)))


@bdd_when(
    rx(
        r'^я перевіряю лист для вакансії (?P<job>\d+) із (?P<words>\d+) слів і підписом "(?P<signoff>[^"]*)" на фактах "(?P<facts>[^"]*)"$'
    )
)
def check_letter_signed(
    world: World, job: str, words: str, signoff: str, facts: str
) -> None:
    text = letter_text(int(words), unescape(signoff))
    world.check_letter(int(job), CoverLetterData(text=text, fact_ids=numbers(facts)))


def checked_of(world: World) -> CheckData:
    assert world.error is None, world.error
    assert world.checked is not None, "перевірки не було"
    return world.checked


@bdd_then("перевірка пройдена")
def check_passed(world: World) -> None:
    checked = checked_of(world)
    assert checked.issues == ()
    assert checked.passed is True


@bdd_then(rx(r"^перевірка не пройдена: (?P<count>\d+) зауваж\w+$"))
def check_failed(world: World, count: str) -> None:
    checked = checked_of(world)
    assert checked.passed is False
    assert len(checked.issues) == int(count), checked.issues


@bdd_then(
    rx(r'^у перевірці є зауваження "(?P<code>[^"]*)" з текстом "(?P<message>[^"]*)"$')
)
def check_issue(world: World, code: str, message: str) -> None:
    found = [(issue.code.value, issue.message) for issue in checked_of(world).issues]
    assert (code, message) in found, found


@bdd_then(
    rx(
        r'^у перевірці є зауваження "(?P<code>[^"]*)" з текстом, що містить "(?P<part>[^"]*)"$'
    )
)
def check_issue_part(world: World, code: str, part: str) -> None:
    found = [
        issue.message for issue in checked_of(world).issues if issue.code.value == code
    ]
    assert any(part in message for message in found), found


@bdd_then(
    rx(
        r'^покриття ключових слів у перевірці: знайдено "(?P<covered>[^"]*)", не знайдено "(?P<missing>[^"]*)", (?P<percent>\d+)%$'
    )
)
def check_keywords(world: World, covered: str, missing: str, percent: str) -> None:
    keywords = checked_of(world).keywords
    assert keywords is not None
    assert (list(keywords.covered), list(keywords.missing), keywords.percent) == (
        words(covered),
        words(missing),
        int(percent),
    )


@bdd_then("покриття ключових слів у перевірці не рахувалося")
def check_no_keywords(world: World) -> None:
    assert checked_of(world).keywords is None


# --- збереження листа -----------------------------------------------------------------------


@action(
    r'^я (?:зберігаю|зберіг) лист для вакансії (?P<job>\d+) із (?P<words>\d+) слів на фактах "(?P<facts>[^"]*)"$'
)
def save_letter(world: World, job: str, words: str, facts: str) -> None:
    text = letter_text(int(words))
    world.save_letter(int(job), CoverLetterData(text=text, fact_ids=numbers(facts)))


@bdd_when(
    rx(
        r'^я зберігаю лист для вакансії (?P<job>\d+) із (?P<words>\d+) слів і підписом "(?P<signoff>[^"]*)" на фактах "(?P<facts>[^"]*)"$'
    )
)
def save_letter_signed(
    world: World, job: str, words: str, signoff: str, facts: str
) -> None:
    text = letter_text(int(words), unescape(signoff))
    world.save_letter(int(job), CoverLetterData(text=text, fact_ids=numbers(facts)))


@bdd_when(
    rx(
        r"^я зберігаю лист для вакансії (?P<job>\d+) із (?P<words>\d+) слів на (?P<count>\d+) фактах$"
    )
)
def save_letter_many_facts(world: World, job: str, words: str, count: str) -> None:
    text = letter_text(int(words))
    facts = tuple(range(1, int(count) + 1))
    world.save_letter(int(job), CoverLetterData(text=text, fact_ids=facts))


@bdd_when(
    rx(r"^я зберігаю лист для вакансії (?P<job>\d+) із (?P<words>\d+) слів без фактів$")
)
def save_letter_no_facts(world: World, job: str, words: str) -> None:
    world.save_letter(int(job), CoverLetterData(text=letter_text(int(words))))


@setup(r"^є (?P<count>\d+) підтверджених фактів$")
def many_facts(world: World, count: str) -> None:
    for number in range(int(count)):
        world.add_fact("skill", f"Навичка {number}", confirmed=True)


# --- бриф ----------------------------------------------------------------------------------


@bdd_when(rx(r"^я готую бриф CV для вакансії (?P<job>\d+)$"))
def prepare_cv(world: World, job: str) -> None:
    world.cv_brief = world.attempt(
        lambda: world.documents.prepare_cv(world.actor, int(job))
    )


@bdd_when(rx(r"^я готую бриф листа для вакансії (?P<job>\d+)$"))
def prepare_letter(world: World, job: str) -> None:
    world.letter_brief = world.attempt(
        lambda: world.documents.prepare_cover_letter(world.actor, int(job))
    )


def brief_of(world: World) -> CvBriefData | CoverLetterBriefData:
    assert world.error is None, world.error
    brief = world.cv_brief or world.letter_brief
    assert brief is not None, "бриф не готували"
    return brief


@bdd_then(rx(r'^у брифі вакансія "(?P<title>[^"]*)" з текстом "(?P<text>[^"]*)"$'))
def brief_job(world: World, title: str, text: str) -> None:
    job = brief_of(world).job
    assert (job.title, job.text) == (title, text)


@bdd_then("у брифі аналізу нема")
def brief_no_analysis(world: World) -> None:
    assert brief_of(world).analysis is None


@bdd_then(rx(r'^аналіз у брифі має ключові слова "(?P<keywords>[^"]*)"$'))
def brief_analysis(world: World, keywords: str) -> None:
    analysis = brief_of(world).analysis
    assert analysis is not None
    assert list(analysis.keywords) == words(keywords)


@bdd_then(rx(r'^факти в брифі за порядком: "(?P<texts>[^"]*)"$'))
def brief_facts(world: World, texts: str) -> None:
    assert [fact.text for fact in brief_of(world).confirmed_facts] == words(texts)


@bdd_then("фактів у брифі нема")
def brief_no_facts(world: World) -> None:
    assert brief_of(world).confirmed_facts == ()


@bdd_then(rx(r'^профіль у брифі має ім\'я "(?P<name>[^"]*)"$'))
def brief_profile(world: World, name: str) -> None:
    assert brief_of(world).profile.contacts.full_name == name


@bdd_then("правила брифу з каталогу промптів")
def brief_rules(world: World) -> None:
    expected = CV_RULES if world.cv_brief is not None else LETTER_RULES
    assert brief_of(world).rules == expected


@bdd_then("попередньої версії в брифі нема")
def brief_no_previous(world: World) -> None:
    assert brief_of(world).previous is None


@bdd_then(
    rx(
        r'^попередня версія в брифі: вид "(?P<kind>cv|cl)", версія (?P<version>\d+), документ (?P<number>\d+)$'
    )
)
def brief_previous(world: World, kind: str, version: str, number: str) -> None:
    previous = brief_of(world).previous
    assert previous is not None
    assert (previous.kind, previous.version, previous.document_number) == (
        KINDS[kind],
        int(version),
        int(number),
    )


@bdd_then("CV у брифі листа нема")
def letter_brief_no_cv(world: World) -> None:
    assert world.letter_brief is not None
    assert world.error is None
    assert world.letter_brief.cv is None


@bdd_then(rx(r"^CV у брифі листа: версія (?P<version>\d+), документ (?P<number>\d+)$"))
def letter_brief_cv(world: World, version: str, number: str) -> None:
    assert world.letter_brief is not None
    assert world.error is None
    cv = world.letter_brief.cv
    assert cv is not None
    assert (cv.kind, cv.version, cv.document_number) == (
        DocumentKind.CV,
        int(version),
        int(number),
    )


# --- результат збереження -------------------------------------------------------------------


@bdd_then(
    rx(
        r"^збережено документ (?P<number>\d+): вид \"(?P<kind>cv|cl)\", версія (?P<version>\d+), вакансія (?P<job>\d+)$"
    )
)
def saved_document(
    world: World, number: str, kind: str, version: str, job: str
) -> None:
    assert world.error is None, world.error
    saved = world.saved
    assert saved is not None, "нічого не збережено"
    assert (
        saved.document_number,
        saved.kind,
        saved.version,
        saved.job_number,
    ) == (int(number), KINDS[kind], int(version), int(job))


@bdd_then(rx(r'^збережений CV має підсумок "(?P<summary>[^"]*)"$'))
def saved_cv_summary(world: World, summary: str) -> None:
    assert world.saved is not None
    assert isinstance(world.saved.content, CvData)
    assert world.saved.content.summary.text == summary


@bdd_then(rx(r"^збережений лист має (?P<paragraphs>\d+) абзаци?$"))
def saved_letter_paragraphs(world: World, paragraphs: str) -> None:
    assert world.saved is not None
    assert isinstance(world.saved.content, CoverLetterData)
    assert len(world.saved.content.text.split("\n\n")) == int(paragraphs)


@bdd_then(rx(r'^збережений лист закінчується рядками "(?P<tail>[^"]*)"$'))
def saved_letter_tail(world: World, tail: str) -> None:
    assert world.saved is not None
    assert isinstance(world.saved.content, CoverLetterData)
    assert world.saved.content.text.endswith(tail.replace("\\n", "\n"))


@bdd_then(rx(r'^збережений документ цитує факти "(?P<facts>[^"]*)"$'))
def saved_facts(world: World, facts: str) -> None:
    assert world.saved is not None
    content = world.saved.content
    assert isinstance(content, CvData | CoverLetterData)
    found = (
        content.headline.fact_ids if isinstance(content, CvData) else content.fact_ids
    )
    assert tuple(found) == numbers(facts)


@bdd_then(rx(r"^нічого не збережено для вакансії (?P<job>\d+)$"))
def nothing_saved(world: World, job: str) -> None:
    assert world.documents_of(int(job)) == ()
    assert world.pdf.files == {}


# --- список -------------------------------------------------------------------------------


@bdd_when(rx(r"^я переглядаю документи вакансії (?P<job>\d+)$"))
def list_documents(world: World, job: str) -> None:
    world.listed = world.attempt(
        lambda: world.documents.list_documents(world.actor, int(job))
    )


@bdd_then(rx(r'^документи вакансії за порядком: "(?P<items>[^"]*)"$'))
def listed_order(world: World, items: str) -> None:
    assert world.error is None, world.error
    assert world.listed is not None
    found = [
        f"{'cv' if item.kind is DocumentKind.CV else 'cl'} v{item.version} #{item.document_number}"
        for item in world.listed
    ]
    assert found == words(items)


@bdd_then("документів у вакансії нема")
def listed_empty(world: World) -> None:
    assert world.error is None, world.error
    assert world.listed == ()


@bdd_then(
    rx(r"^версії документів у списку мають свій вміст: \"(?P<summaries>[^\"]*)\"$")
)
def listed_contents(world: World, summaries: str) -> None:
    assert world.listed is not None
    found = [
        item.content.summary.text
        for item in world.listed
        if isinstance(item.content, CvData)
    ]
    assert found == words(summaries)


# --- PDF і ATS-звіт -------------------------------------------------------------------------


@bdd_then(rx(r'^PDF відрендерено з іменем "(?P<name>[^"]*)" у шапці$'))
def pdf_rendered(world: World, name: str) -> None:
    assert world.pdf.rendered, "рендеру не було"
    contacts = world.pdf.rendered[-1][2]
    assert contacts.full_name == name


@bdd_then(rx(r"^PDF не рендерився$"))
def pdf_not_rendered(world: World) -> None:
    assert world.pdf.rendered == []


@bdd_then(rx(r"^PDF рендерився$"))
def pdf_rendered_in_memory(world: World) -> None:
    assert world.pdf.rendered, "рендеру не було"


@bdd_then(rx(r"^файлів PDF збережено: (?P<count>\d+)$"))
def pdf_files(world: World, count: str) -> None:
    assert len(world.pdf.files) == int(count)


def lint_of(world: World) -> Any:
    assert world.error is None, world.error
    assert world.saved is not None, "нічого не збережено"
    return world.saved.lint


@bdd_then("звіт ATS пройдено")
def lint_passed(world: World) -> None:
    lint = lint_of(world)
    assert lint is not None
    assert lint.passed is True
    assert lint.issues == ()


@bdd_then(rx(r"^звіт ATS не пройдено: (?P<count>\d+) зауваж\w+$"))
def lint_failed(world: World, count: str) -> None:
    lint = lint_of(world)
    assert lint is not None
    assert lint.passed is False
    assert len(lint.issues) == int(count)


@bdd_then(rx(r"^у звіті ATS (?P<pages>\d+) сторін\w+$"))
def lint_pages(world: World, pages: str) -> None:
    assert lint_of(world).pages == int(pages)


@bdd_then(
    rx(r'^у звіті ATS є зауваження "(?P<code>[^"]*)" з текстом "(?P<message>[^"]*)"$')
)
def lint_issue(world: World, code: str, message: str) -> None:
    found = [(issue.code.value, issue.message) for issue in lint_of(world).issues]
    assert (code, message) in found, found


@bdd_then(
    rx(
        r'^у звіті ATS є зауваження "(?P<code>[^"]*)" про символ (?P<char>U\+[0-9A-F]+)$'
    )
)
def lint_invisible(world: World, code: str, char: str) -> None:
    found = [issue for issue in lint_of(world).issues if issue.code.value == code]
    assert found
    assert char in found[0].message, found


@bdd_then(
    rx(
        r'^покриття ключових слів: знайдено "(?P<covered>[^"]*)", не знайдено "(?P<missing>[^"]*)", (?P<percent>\d+)%$'
    )
)
def lint_keywords(world: World, covered: str, missing: str, percent: str) -> None:
    keywords = lint_of(world).keywords
    assert keywords is not None
    assert (list(keywords.covered), list(keywords.missing), keywords.percent) == (
        words(covered),
        words(missing),
        int(percent),
    )


@bdd_then("покриття ключових слів не рахувалося")
def lint_no_keywords(world: World) -> None:
    assert lint_of(world).keywords is None


# --- видача PDF і список для вебу -----------------------------------------------------------


@bdd_when(rx(r"^я відкриваю PDF документа (?P<number>\d+)$"))
def open_pdf(world: World, number: str) -> None:
    world.pdf_file = world.attempt(
        lambda: world.documents.get_pdf(world.actor, int(number))
    )


@bdd_then(rx(r'^PDF має назву файлу "(?P<name>[^"]*)"$'))
def pdf_name(world: World, name: str) -> None:
    assert world.error is None, world.error
    assert world.pdf_file is not None
    assert world.pdf_file.file_name == name


@bdd_then(rx(r'^у відкритому PDF є рядок "(?P<line>[^"]*)"$'))
def pdf_has_line(world: World, line: str) -> None:
    assert world.pdf_file is not None
    assert line in world.pdf.layouts[world.pdf_file.data].lines


@bdd_then(rx(r'^у відкритому PDF нема рядка "(?P<line>[^"]*)"$'))
def pdf_lacks_line(world: World, line: str) -> None:
    assert world.pdf_file is not None
    assert line not in world.pdf.layouts[world.pdf_file.data].lines


@bdd_when(rx(r"^я переглядаю документи вакансії (?P<job>\d+) для вебу$"))
def web_list(world: World, job: str) -> None:
    world.web_list = world.attempt(
        lambda: world.documents.list_job_documents(world.actor, int(job))
    )


@bdd_then(rx(r'^для вебу версії за порядком: "(?P<items>[^"]*)"$'))
def web_order(world: World, items: str) -> None:
    assert world.error is None, world.error
    assert world.web_list is not None
    found = [
        f"{'cv' if item.kind is DocumentKind.CV else 'cl'} v{item.version} {item.file_name}"
        for item in world.web_list
    ]
    assert found == words(items)


@bdd_then(rx(r"^для вебу файл версії (?P<number>\d+) (?P<state>є|зник)$"))
def web_file(world: World, number: str, state: str) -> None:
    assert world.web_list is not None
    item = next(i for i in world.web_list if i.document_number == int(number))
    assert item.pdf_available is (state == "є")


@bdd_then(
    rx(r"^для вебу версія (?P<number>\d+) має звіт зі сторінками (?P<pages>\d+)$")
)
def web_lint_pages(world: World, number: str, pages: str) -> None:
    assert world.web_list is not None
    item = next(i for i in world.web_list if i.document_number == int(number))
    assert item.lint is not None
    assert item.lint.pages == int(pages)


@bdd_then("для вебу документів нема")
def web_empty(world: World) -> None:
    assert world.error is None, world.error
    assert world.web_list == ()


# --- помилки -------------------------------------------------------------------------------


@bdd_then(rx(r'^отримую помилку "(?P<code>[^"]*)"$'))
def error_code(world: World, code: str) -> None:
    assert world.error is not None, "помилки не було"
    assert world.error.code == code


@bdd_then(rx(r'^отримую помилку "(?P<code>[^"]*)" з текстом "(?P<message>[^"]*)"$'))
def error_message(world: World, code: str, message: str) -> None:
    assert world.error is not None, "помилки не було"
    assert (world.error.code, world.error.message) == (code, message)


@bdd_then(
    rx(r'^отримую помилку "(?P<code>[^"]*)" з текстом, що містить "(?P<part>[^"]*)"$')
)
def error_contains(world: World, code: str, part: str) -> None:
    assert world.error is not None, "помилки не було"
    assert world.error.code == code
    assert part in world.error.message, world.error.message


@bdd_then(rx(r'^збереження впало зі збоєм "(?P<message>[^"]*)"$'))
def crashed(world: World, message: str) -> None:
    assert world.error is None, world.error
    assert world.crash is not None, "збою не було"
    assert str(world.crash) == message


@bdd_then("помилки не було")
def no_error(world: World) -> None:
    assert world.error is None, world.error


# --- чистка старих версій -------------------------------------------------------------------


@setup(
    r"^у вакансії (?P<job>\d+) лишилися (?P<count>\d+) старі версії (?P<kind>CV|листа) з файлами$"
)
def old_versions(world: World, job: str, count: str, kind: str) -> None:
    world.seed_versions(
        int(job),
        DocumentKind.CV if kind == "CV" else DocumentKind.COVER_LETTER,
        int(count),
    )


@bdd_when(rx(r"^я чищу старі версії (?P<mode>з підтвердженням|без підтвердження)$"))
def prune(world: World, mode: str) -> None:
    world.pruned = world.attempt(
        lambda: world.documents.prune_superseded(mode == "з підтвердженням")
    )


@bdd_then(
    rx(
        r"^чистка: документів (?P<documents>\d+), файлів (?P<files>\d+), видалено (?P<done>так|ні)$"
    )
)
def pruned_report(world: World, documents: str, files: str, done: str) -> None:
    assert world.error is None, world.error
    assert world.pruned == PruneData(
        documents=int(documents), files=int(files), applied=done == "так"
    )
