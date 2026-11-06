"""Use cases документів: бриф для Claude, збереження версій з перевіркою фактів, список.

Семантика і тексти помилок — як у v1 (`origin/main` `99a2007`).
"""

from dataclasses import replace
from datetime import datetime, timedelta

import pytest
from anyio.from_thread import BlockingPortal

from application.analysis.use_cases import AnalysisUseCases
from application.contracts.actor import Actor, Channel, Scope
from application.contracts.analysis import AnalysisInput
from application.contracts.documents import (
    ClaimData,
    CoverLetterBriefData,
    CoverLetterData,
    CvBriefData,
    CvData,
    CvEntryData,
    CvSectionData,
    DocumentData,
)
from application.contracts.profile import (
    ContactsData,
    RulesData,
    SectionData,
    TargetData,
)
from application.documents.use_cases import DocumentUseCases
from application.ports.prompts import PromptKey
from application.profile.use_cases import ProfileUseCases
from domain.documents.document import DocumentKind
from domain.facts.fact import NewFact
from domain.facts.ids import FactId
from domain.identity.ids import UserId
from domain.jobs.ids import JobId
from domain.jobs.job import NewJob
from domain.profile.profile import Profile
from domain.shared.errors import InvalidValue, NotFound
from tests.support.analysis import InMemoryAnalysisUnitOfWork
from tests.support.clock import FakeClock
from tests.support.documents import DocumentStore, InMemoryDocumentUnitOfWork
from tests.support.facts import InMemoryFactUnitOfWork
from tests.support.facts import Store as FactStore
from tests.support.ids import SequentialIds
from tests.support.jobs import InMemoryJobUnitOfWork, Store
from tests.support.pdf import Shop
from tests.support.profile import InMemoryProfileUnitOfWork

CV_RULES = "CV rules."
LETTER_RULES = "Cover letter rules."
RUBRIC = "Rubric for {candidate}{domain_examples}."
SECTION_NAMES = (
    "Experience, Projects, Achievements, Skills, Education, "
    "Education and Languages, Certifications, Languages"
)


class FakePrompts:
    def get(self, key: PromptKey) -> str:
        return {
            PromptKey.DOCUMENTS_CV_RULES: CV_RULES,
            PromptKey.DOCUMENTS_COVER_LETTER_RULES: LETTER_RULES,
            PromptKey.ANALYSIS_RUBRIC: RUBRIC,
        }[key]


def claim(text: str, *fact_ids: int) -> ClaimData:
    return ClaimData(text=text, fact_ids=fact_ids)


def cv_data(*fact_ids: int, summary: str = "Payments backend") -> CvData:
    """CV з однією секцією Experience; усі рядки стоять на тих самих фактах."""
    return CvData(
        headline=claim("Senior Backend Engineer", *fact_ids),
        summary=claim(summary, *fact_ids),
        sections=(
            CvSectionData(
                name="Experience",
                entries=(
                    CvEntryData(
                        heading=claim("Engineer · Acme", *fact_ids),
                        bullets=(claim("Built payment APIs", *fact_ids),),
                        meta=claim("2021 - 2024", *fact_ids),
                        subtitle=claim("Payments team of 5", *fact_ids),
                    ),
                ),
            ),
        ),
    )


def letter_text(words: int = 160, tail: str = "Best regards,\nAlex") -> str:
    return "Dear team,\n\n" + " ".join(["word"] * words) + "\n\n" + tail


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
        self.alice = self._actor()
        self.bob = self._actor()
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
        # Ім'я з профілю стоїть у шапці PDF: без нього документ не зберігається.
        for actor, name in ((self.alice, "Alice Example"), (self.bob, "Bob Example")):
            self.set_profile(actor, ContactsData(full_name=name))

    def _actor(self) -> Actor:
        return Actor(
            user_id=UserId(self.ids.new()),
            channel=Channel.WEB,
            client_id="web",
            grant_id=None,
            scopes=frozenset(Scope),
            correlation_id="test",
        )

    def seed(
        self,
        actor: Actor,
        text: str | None = "Senior Python engineer. Remote.",
        *,
        title: str | None = "Engineer",
        company: str | None = "Acme",
    ) -> int:
        self.clock.advance(timedelta(minutes=1))

        async def run() -> int:
            async with InMemoryJobUnitOfWork(self.jobs_store) as uow:
                number = await uow.jobs.add(
                    actor.user_id,
                    JobId(self.ids.new()),
                    NewJob(text=text, title=title, company=company),
                    self.clock.now(),
                )
                await uow.commit()
                return number

        return self.portal.call(run)

    def fact(
        self, actor: Actor, text: str, *, kind: str = "skill", confirmed: bool = True
    ) -> int:
        async def run() -> int:
            async with InMemoryFactUnitOfWork(self.facts_store) as uow:
                added = await uow.facts.add(
                    actor.user_id,
                    FactId(self.ids.new()),
                    NewFact.parse(kind=kind, text=text),
                    self.clock.now(),
                )
                if confirmed:
                    await uow.facts.confirm(
                        actor.user_id, [added.number], self.clock.now()
                    )
                await uow.commit()
                return added.number

        return self.portal.call(run)

    def analyse(self, actor: Actor, number: int, **fields: object) -> None:
        data = AnalysisInput(**({"score": 70, "summary": "A backend role."} | fields))  # type: ignore[arg-type]
        self.portal.call(self.analysis.save_analysis, actor, number, data)

    def prepare_cv(self, actor: Actor, number: int) -> CvBriefData:
        return self.portal.call(self.documents.prepare_cv, actor, number)

    def prepare_letter(self, actor: Actor, number: int) -> CoverLetterBriefData:
        return self.portal.call(self.documents.prepare_cover_letter, actor, number)

    def save_cv(self, actor: Actor, number: int, data: CvData) -> DocumentData:
        self.clock.advance(timedelta(minutes=1))
        return self.portal.call(self.documents.save_cv, actor, number, data)

    def save_letter(
        self, actor: Actor, number: int, data: CoverLetterData
    ) -> DocumentData:
        self.clock.advance(timedelta(minutes=1))
        return self.portal.call(self.documents.save_cover_letter, actor, number, data)

    def listed(self, actor: Actor, number: int) -> tuple[DocumentData, ...]:
        return self.portal.call(self.documents.list_documents, actor, number)

    def set_profile(self, actor: Actor, *sections: SectionData) -> None:
        for section in sections:
            self.portal.call(self.profile.save_section, actor, section)


@pytest.fixture
def world(portal: BlockingPortal, clock: FakeClock, ids: SequentialIds) -> World:
    return World(portal, clock, ids)


# --- prepare_cv ---------------------------------------------------------------


def test_cv_brief_for_a_missing_job_is_not_found(world: World) -> None:
    with pytest.raises(NotFound) as error:
        world.prepare_cv(world.alice, 9)
    assert error.value.message == "Вакансію 9 не знайдено."


def test_cv_brief_for_a_job_of_another_user_is_not_found(world: World) -> None:
    theirs = world.seed(world.bob)
    with pytest.raises(NotFound):
        world.prepare_cv(world.alice, theirs)


def test_cv_brief_for_a_job_without_text_is_refused(world: World) -> None:
    waiting = world.seed(world.alice, None)
    with pytest.raises(InvalidValue) as error:
        world.prepare_cv(world.alice, waiting)
    assert error.value.message == (
        f"У вакансії {waiting} нема тексту опису (вона з листа-алерту): спершу додай текст."
    )


def test_cv_brief_has_the_job_and_its_text(world: World) -> None:
    number = world.seed(world.alice, "Go role", title="Go Dev", company="Acme")

    brief = world.prepare_cv(world.alice, number)

    assert (brief.job.job_number, brief.job.title, brief.job.text) == (
        number,
        "Go Dev",
        "Go role",
    )


def test_cv_brief_has_no_analysis_until_the_job_is_analysed(world: World) -> None:
    number = world.seed(world.alice)
    assert world.prepare_cv(world.alice, number).analysis is None

    world.analyse(world.alice, number, keywords=["asyncio"], must_have=["Python"])
    analysis = world.prepare_cv(world.alice, number).analysis

    assert analysis is not None
    assert (analysis.score, analysis.keywords, analysis.must_have) == (
        70,
        ("asyncio",),
        ("Python",),
    )


def test_cv_brief_carries_what_the_employer_asks_of_candidates(world: World) -> None:
    number = world.seed(world.alice)
    asks = ["Send your GitHub", "Skip the list of frameworks"]

    world.analyse(world.alice, number, candidate_asks=asks)
    analysis = world.prepare_cv(world.alice, number).analysis

    assert analysis is not None
    assert analysis.candidate_asks == tuple(asks)


def test_cv_brief_has_the_profile_and_an_empty_one_when_none_is_saved(
    world: World,
) -> None:
    number = world.seed(world.alice)
    world.set_profile(world.alice, ContactsData())
    empty = world.prepare_cv(world.alice, number).profile
    assert (empty.contacts.full_name, empty.target.roles) == ("", ())

    world.set_profile(
        world.alice,
        TargetData(roles=("Backend",)),
        ContactsData(full_name="Test User", email="test@example.com"),
        RulesData(),
    )
    profile = world.prepare_cv(world.alice, number).profile

    assert (profile.contacts.full_name, profile.target.roles) == (
        "Test User",
        ("Backend",),
    )


def test_cv_brief_carries_only_confirmed_facts_by_kind_then_number(
    world: World,
) -> None:
    number = world.seed(world.alice)
    skill_1 = world.fact(world.alice, "Python")
    world.fact(world.alice, "Rust", confirmed=False)
    experience = world.fact(world.alice, "5 years at Acme", kind="experience")
    skill_2 = world.fact(world.alice, "Postgres")
    language = world.fact(world.alice, "English C1", kind="language")
    world.fact(world.bob, "Not mine")

    brief = world.prepare_cv(world.alice, number)

    assert [fact.fact_number for fact in brief.confirmed_facts] == [
        experience,
        skill_1,
        skill_2,
        language,
    ]


def test_cv_brief_without_confirmed_facts_has_an_empty_list(world: World) -> None:
    number = world.seed(world.alice)
    world.fact(world.alice, "Rust", confirmed=False)

    assert world.prepare_cv(world.alice, number).confirmed_facts == ()


def test_cv_brief_has_the_cv_rules(world: World) -> None:
    number = world.seed(world.alice)
    assert world.prepare_cv(world.alice, number).rules == CV_RULES


def test_cv_brief_has_no_previous_version_at_first(world: World) -> None:
    number = world.seed(world.alice)
    assert world.prepare_cv(world.alice, number).previous is None


def test_cv_brief_previous_is_the_latest_cv_not_a_letter(world: World) -> None:
    number = world.seed(world.alice)
    fact = world.fact(world.alice, "Python")
    world.save_cv(world.alice, number, cv_data(fact, summary="First"))
    second = world.save_cv(world.alice, number, cv_data(fact, summary="Second"))
    world.save_letter(
        world.alice, number, CoverLetterData(text=letter_text(), fact_ids=(fact,))
    )

    previous = world.prepare_cv(world.alice, number).previous

    assert previous == second
    assert previous is not None
    assert (previous.kind, previous.version) == (DocumentKind.CV, 2)


# --- prepare_cover_letter -----------------------------------------------------


def test_letter_brief_for_a_missing_job_is_not_found(world: World) -> None:
    with pytest.raises(NotFound) as error:
        world.prepare_letter(world.alice, 9)
    assert error.value.message == "Вакансію 9 не знайдено."


def test_letter_brief_for_a_job_of_another_user_is_not_found(world: World) -> None:
    theirs = world.seed(world.bob)
    with pytest.raises(NotFound):
        world.prepare_letter(world.alice, theirs)


def test_letter_brief_for_a_job_without_text_is_refused(world: World) -> None:
    waiting = world.seed(world.alice, None)
    with pytest.raises(InvalidValue) as error:
        world.prepare_letter(world.alice, waiting)
    assert error.value.message == (
        f"У вакансії {waiting} нема тексту опису (вона з листа-алерту): спершу додай текст."
    )


def test_letter_brief_has_job_analysis_profile_facts_and_rules(world: World) -> None:
    number = world.seed(world.alice, "Go role", title="Go Dev")
    world.analyse(world.alice, number, keywords=["Go"])
    fact = world.fact(world.alice, "Python")
    world.fact(world.alice, "Rust", confirmed=False)
    world.set_profile(world.alice, ContactsData(full_name="Test User"))

    brief = world.prepare_letter(world.alice, number)

    assert (brief.job.title, brief.job.text) == ("Go Dev", "Go role")
    assert brief.analysis is not None
    assert brief.analysis.keywords == ("Go",)
    assert brief.profile.contacts.full_name == "Test User"
    assert [item.fact_number for item in brief.confirmed_facts] == [fact]
    assert brief.rules == LETTER_RULES


def test_letter_brief_carries_what_the_employer_asks_of_candidates(
    world: World,
) -> None:
    number = world.seed(world.alice)
    asks = ["Describe a project you are proud of"]

    world.analyse(world.alice, number, candidate_asks=asks)
    brief = world.prepare_letter(world.alice, number)

    assert brief.analysis is not None
    assert brief.analysis.candidate_asks == tuple(asks)


def test_letter_brief_works_without_a_cv(world: World) -> None:
    number = world.seed(world.alice)

    brief = world.prepare_letter(world.alice, number)

    assert (brief.cv, brief.previous, brief.analysis) == (None, None, None)


def test_letter_brief_has_the_latest_cv_and_the_previous_letter(world: World) -> None:
    number = world.seed(world.alice)
    fact = world.fact(world.alice, "Python")
    world.save_cv(world.alice, number, cv_data(fact, summary="First"))
    cv = world.save_cv(world.alice, number, cv_data(fact, summary="Second"))
    world.save_letter(
        world.alice, number, CoverLetterData(text=letter_text(), fact_ids=(fact,))
    )
    letter = world.save_letter(
        world.alice, number, CoverLetterData(text=letter_text(170), fact_ids=(fact,))
    )

    brief = world.prepare_letter(world.alice, number)

    assert brief.cv == cv
    assert brief.previous == letter
    assert brief.previous is not None
    assert (brief.previous.kind, brief.previous.version) == (
        DocumentKind.COVER_LETTER,
        2,
    )


# --- save_cv ------------------------------------------------------------------


def test_saved_cv_comes_back_as_the_first_version(world: World) -> None:
    number = world.seed(world.alice)
    fact = world.fact(world.alice, "Python")
    data = cv_data(fact)

    saved = world.save_cv(world.alice, number, data)

    assert replace(saved, lint=None) == DocumentData(
        document_number=1,
        job_number=number,
        kind=DocumentKind.CV,
        version=1,
        content=data,
        created_at=world.clock.now(),
    )


def test_cv_lines_are_trimmed_and_repeated_fact_ids_dropped(world: World) -> None:
    number = world.seed(world.alice)
    first = world.fact(world.alice, "Python")
    second = world.fact(world.alice, "Postgres")
    messy = CvData(
        headline=ClaimData(text="  Senior Engineer ", fact_ids=[second, first, second]),
        summary=claim("Summary", first),
        sections=[
            CvSectionData(
                name=" Skills ",
                entries=[CvEntryData(heading=claim("Backend", first), bullets=[])],
            )
        ],
    )

    saved = world.save_cv(world.alice, number, messy)

    assert isinstance(saved.content, CvData)
    assert saved.content.headline == claim("Senior Engineer", second, first)
    assert saved.content.sections == (
        CvSectionData(
            name="Skills", entries=(CvEntryData(heading=claim("Backend", first)),)
        ),
    )


def test_cv_with_an_unknown_fact_is_rejected_and_nothing_is_saved(
    world: World,
) -> None:
    number = world.seed(world.alice)
    fact = world.fact(world.alice, "Python")

    with pytest.raises(InvalidValue) as error:
        world.save_cv(world.alice, number, cv_data(fact, 99))

    assert error.value.message == "Факти не знайдено: #99."
    assert world.listed(world.alice, number) == ()


def test_cv_with_an_unconfirmed_fact_is_rejected_and_nothing_is_saved(
    world: World,
) -> None:
    number = world.seed(world.alice)
    confirmed = world.fact(world.alice, "Python")
    unconfirmed = world.fact(world.alice, "Rust", confirmed=False)

    with pytest.raises(InvalidValue) as error:
        world.save_cv(world.alice, number, cv_data(confirmed, unconfirmed))

    assert error.value.message == (
        f"Факти не підтверджені: #{unconfirmed} — спершу користувач їх підтверджує."
    )
    assert world.listed(world.alice, number) == ()


def test_cv_cannot_cite_a_fact_of_another_user(world: World) -> None:
    number = world.seed(world.alice)
    theirs = world.fact(world.bob, "Their secret")

    with pytest.raises(InvalidValue) as error:
        world.save_cv(world.alice, number, cv_data(theirs))

    assert error.value.message == f"Факти не знайдено: #{theirs}."


def test_cv_with_an_unknown_section_is_rejected_with_the_allowed_names(
    world: World,
) -> None:
    number = world.seed(world.alice)
    fact = world.fact(world.alice, "Python")
    data = CvData(
        headline=claim("Engineer", fact),
        summary=claim("Summary", fact),
        sections=[
            CvSectionData(
                name="Hobbies", entries=[CvEntryData(heading=claim("Chess", fact))]
            )
        ],
    )

    with pytest.raises(InvalidValue) as error:
        world.save_cv(world.alice, number, data)

    assert error.value.message == f"Секція 'Hobbies' — допустимо: {SECTION_NAMES}."


def test_cv_over_the_limits_is_rejected_and_nothing_is_saved(world: World) -> None:
    number = world.seed(world.alice)
    fact = world.fact(world.alice, "Python")
    data = cv_data(fact, summary="x" * 401)

    with pytest.raises(InvalidValue) as error:
        world.save_cv(world.alice, number, data)

    assert error.value.message == (
        f"Кожен рядок — від 1 до 400 символів: {'x' * 60!r}."
    )
    assert world.listed(world.alice, number) == ()


def test_cv_without_a_fact_on_a_line_is_rejected(world: World) -> None:
    number = world.seed(world.alice)
    fact = world.fact(world.alice, "Python")
    data = CvData(headline=claim("Engineer"), summary=claim("Summary", fact))

    with pytest.raises(InvalidValue) as error:
        world.save_cv(world.alice, number, data)

    assert error.value.message == "Рядок без fact_ids: 'Engineer'."


def test_cv_without_sections_is_rejected(world: World) -> None:
    number = world.seed(world.alice)
    fact = world.fact(world.alice, "Python")
    data = CvData(headline=claim("Engineer", fact), summary=claim("Summary", fact))

    with pytest.raises(InvalidValue) as error:
        world.save_cv(world.alice, number, data)

    assert error.value.message == "CV без секцій."


def test_cv_for_a_missing_job_is_not_found(world: World) -> None:
    fact = world.fact(world.alice, "Python")
    with pytest.raises(NotFound) as error:
        world.save_cv(world.alice, 9, cv_data(fact))
    assert error.value.message == "Вакансію 9 не знайдено."


def test_cv_for_a_job_of_another_user_is_not_found(world: World) -> None:
    theirs = world.seed(world.bob)
    fact = world.fact(world.alice, "Python")
    with pytest.raises(NotFound):
        world.save_cv(world.alice, theirs, cv_data(fact))
    assert world.listed(world.bob, theirs) == ()


def test_cv_for_a_job_without_text_is_refused(world: World) -> None:
    waiting = world.seed(world.alice, None)
    fact = world.fact(world.alice, "Python")
    with pytest.raises(InvalidValue) as error:
        world.save_cv(world.alice, waiting, cv_data(fact))
    assert error.value.message == (
        f"У вакансії {waiting} нема тексту опису (вона з листа-алерту): спершу додай текст."
    )


# --- save_cover_letter --------------------------------------------------------


def test_saved_letter_comes_back_as_the_first_version(world: World) -> None:
    number = world.seed(world.alice)
    fact = world.fact(world.alice, "Python")
    text = letter_text()

    saved = world.save_letter(
        world.alice, number, CoverLetterData(text=text, fact_ids=(fact,))
    )

    assert replace(saved, lint=None) == DocumentData(
        document_number=1,
        job_number=number,
        kind=DocumentKind.COVER_LETTER,
        version=1,
        content=CoverLetterData(text=text, fact_ids=(fact,)),
        created_at=world.clock.now(),
    )


def test_letter_keeps_paragraphs_and_a_single_line_break_inside_one(
    world: World,
) -> None:
    number = world.seed(world.alice)
    fact = world.fact(world.alice, "Python")
    raw = (
        "  Dear team,\n\n\n"
        + " ".join(["word"] * 160)
        + "\r\n\r\nBest regards,\r\nAlex\n\n"
    )

    saved = world.save_letter(
        world.alice, number, CoverLetterData(text=raw, fact_ids=(fact, fact))
    )

    assert saved.content == CoverLetterData(
        text="Dear team,\n\n" + " ".join(["word"] * 160) + "\n\nBest regards,\nAlex",
        fact_ids=(fact,),
    )


@pytest.mark.parametrize(
    ("words", "message"),
    [
        (50, "Лист — 150–250 слів, а тут 55."),
        (300, "Лист — 150–250 слів, а тут 305."),
    ],
)
def test_letter_outside_the_word_range_is_rejected(
    world: World, words: int, message: str
) -> None:
    number = world.seed(world.alice)
    fact = world.fact(world.alice, "Python")
    # «Dear team,» (2) + слова + «Best regards, Alex» (3).
    data = CoverLetterData(text=letter_text(words), fact_ids=(fact,))

    with pytest.raises(InvalidValue) as error:
        world.save_letter(world.alice, number, data)

    assert error.value.message == message
    assert world.listed(world.alice, number) == ()


def test_letter_with_an_unfilled_template_is_rejected(world: World) -> None:
    number = world.seed(world.alice)
    fact = world.fact(world.alice, "Python")
    data = CoverLetterData(
        text=letter_text(tail="Best regards,\n[Your Name]"), fact_ids=(fact,)
    )

    with pytest.raises(InvalidValue) as error:
        world.save_letter(world.alice, number, data)

    assert error.value.message == "Незаповнений шаблон у листі: [Your Name]."
    assert world.listed(world.alice, number) == ()


def test_letter_without_facts_is_rejected(world: World) -> None:
    number = world.seed(world.alice)

    with pytest.raises(InvalidValue) as error:
        world.save_letter(world.alice, number, CoverLetterData(text=letter_text()))

    assert error.value.message == (
        "Лист без fact_ids: вкажи факти, на які він спирається."
    )


def test_letter_with_more_than_thirty_facts_is_rejected(world: World) -> None:
    number = world.seed(world.alice)
    facts = tuple(world.fact(world.alice, f"Fact {i}") for i in range(31))

    with pytest.raises(InvalidValue) as error:
        world.save_letter(
            world.alice, number, CoverLetterData(text=letter_text(), fact_ids=facts)
        )

    assert error.value.message == "Не більше 30 fact_ids у листі."


def test_letter_with_an_unknown_fact_is_rejected_and_nothing_is_saved(
    world: World,
) -> None:
    number = world.seed(world.alice)
    fact = world.fact(world.alice, "Python")

    with pytest.raises(InvalidValue) as error:
        world.save_letter(
            world.alice,
            number,
            CoverLetterData(text=letter_text(), fact_ids=(fact, 77)),
        )

    assert error.value.message == "Факти не знайдено: #77."
    assert world.listed(world.alice, number) == ()


def test_letter_with_an_unconfirmed_fact_is_rejected_and_nothing_is_saved(
    world: World,
) -> None:
    number = world.seed(world.alice)
    unconfirmed = world.fact(world.alice, "Rust", confirmed=False)

    with pytest.raises(InvalidValue) as error:
        world.save_letter(
            world.alice,
            number,
            CoverLetterData(text=letter_text(), fact_ids=(unconfirmed,)),
        )

    assert error.value.message == (
        f"Факти не підтверджені: #{unconfirmed} — спершу користувач їх підтверджує."
    )
    assert world.listed(world.alice, number) == ()


def test_letter_for_a_missing_job_is_not_found(world: World) -> None:
    fact = world.fact(world.alice, "Python")
    with pytest.raises(NotFound) as error:
        world.save_letter(
            world.alice, 9, CoverLetterData(text=letter_text(), fact_ids=(fact,))
        )
    assert error.value.message == "Вакансію 9 не знайдено."


def test_letter_for_a_job_without_text_is_refused(world: World) -> None:
    waiting = world.seed(world.alice, None)
    fact = world.fact(world.alice, "Python")
    with pytest.raises(InvalidValue):
        world.save_letter(
            world.alice, waiting, CoverLetterData(text=letter_text(), fact_ids=(fact,))
        )


def test_letter_does_not_need_a_cv(world: World) -> None:
    number = world.seed(world.alice)
    fact = world.fact(world.alice, "Python")

    saved = world.save_letter(
        world.alice, number, CoverLetterData(text=letter_text(), fact_ids=(fact,))
    )

    assert saved.version == 1


# --- версії й номери ----------------------------------------------------------


def test_cv_and_letter_versions_of_one_job_count_separately(world: World) -> None:
    number = world.seed(world.alice)
    fact = world.fact(world.alice, "Python")
    letter = CoverLetterData(text=letter_text(), fact_ids=(fact,))

    first_cv = world.save_cv(world.alice, number, cv_data(fact))
    second_cv = world.save_cv(world.alice, number, cv_data(fact))
    first_letter = world.save_letter(world.alice, number, letter)
    third_cv = world.save_cv(world.alice, number, cv_data(fact))
    second_letter = world.save_letter(world.alice, number, letter)

    assert [
        (d.kind, d.version)
        for d in (first_cv, second_cv, first_letter, third_cv, second_letter)
    ] == [
        (DocumentKind.CV, 1),
        (DocumentKind.CV, 2),
        (DocumentKind.COVER_LETTER, 1),
        (DocumentKind.CV, 3),
        (DocumentKind.COVER_LETTER, 2),
    ]


def test_another_job_starts_its_versions_from_one(world: World) -> None:
    first = world.seed(world.alice)
    other = world.seed(world.alice)
    fact = world.fact(world.alice, "Python")
    world.save_cv(world.alice, first, cv_data(fact))
    world.save_cv(world.alice, first, cv_data(fact))

    saved = world.save_cv(world.alice, other, cv_data(fact))

    assert (saved.job_number, saved.version) == (other, 1)


def test_document_numbers_count_per_user_across_jobs_and_kinds(world: World) -> None:
    first = world.seed(world.alice)
    other = world.seed(world.alice)
    fact = world.fact(world.alice, "Python")
    letter = CoverLetterData(text=letter_text(), fact_ids=(fact,))

    numbers = [
        world.save_cv(world.alice, first, cv_data(fact)).document_number,
        world.save_letter(world.alice, first, letter).document_number,
        world.save_cv(world.alice, other, cv_data(fact)).document_number,
    ]

    assert numbers == [1, 2, 3]


def test_every_user_numbers_documents_from_one(world: World) -> None:
    mine = world.seed(world.alice)
    theirs = world.seed(world.bob)
    mine_fact = world.fact(world.alice, "Python")
    their_fact = world.fact(world.bob, "Go")
    world.save_cv(world.alice, mine, cv_data(mine_fact))

    saved = world.save_cv(world.bob, theirs, cv_data(their_fact))

    assert saved.document_number == 1


# --- list_documents -----------------------------------------------------------


def test_a_job_without_documents_has_an_empty_list(world: World) -> None:
    number = world.seed(world.alice)
    assert world.listed(world.alice, number) == ()


def test_documents_of_a_missing_job_are_an_empty_list(world: World) -> None:
    assert world.listed(world.alice, 9) == ()


def test_documents_list_has_one_document_of_each_kind_newest_first(
    world: World,
) -> None:
    number = world.seed(world.alice)
    fact = world.fact(world.alice, "Python")
    world.save_cv(world.alice, number, cv_data(fact, summary="First"))
    letter = world.save_letter(
        world.alice, number, CoverLetterData(text=letter_text(), fact_ids=(fact,))
    )
    cv = world.save_cv(world.alice, number, cv_data(fact, summary="Second"))

    assert world.listed(world.alice, number) == (cv, letter)


def test_documents_list_has_the_content_of_the_current_cv_only(world: World) -> None:
    number = world.seed(world.alice)
    fact = world.fact(world.alice, "Python")
    world.save_cv(world.alice, number, cv_data(fact, summary="First"))
    world.save_cv(world.alice, number, cv_data(fact, summary="Second"))

    listed = world.listed(world.alice, number)

    assert [item.content for item in listed] == [cv_data(fact, summary="Second")]


def test_documents_list_has_only_the_documents_of_that_job(world: World) -> None:
    first = world.seed(world.alice)
    other = world.seed(world.alice)
    fact = world.fact(world.alice, "Python")
    world.save_cv(world.alice, first, cv_data(fact))
    on_other = world.save_cv(world.alice, other, cv_data(fact))

    assert world.listed(world.alice, other) == (on_other,)


def test_a_user_never_sees_documents_of_another(world: World) -> None:
    mine = world.seed(world.alice)
    theirs = world.seed(world.bob)
    mine_fact = world.fact(world.alice, "Python")
    their_fact = world.fact(world.bob, "Go")
    world.save_cv(world.alice, mine, cv_data(mine_fact))
    their_doc = world.save_cv(world.bob, theirs, cv_data(their_fact))

    # Номери вакансій у користувачів збігаються: це різні вакансії.
    assert mine == theirs
    assert world.listed(world.bob, theirs) == (their_doc,)
    assert world.prepare_cv(world.bob, theirs).previous == their_doc
    assert world.prepare_letter(world.bob, theirs).cv == their_doc


def test_a_saved_document_stamps_the_current_time(world: World) -> None:
    number = world.seed(world.alice)
    fact = world.fact(world.alice, "Python")

    saved = world.save_cv(world.alice, number, cv_data(fact))

    assert saved.created_at == world.clock.now()
    assert isinstance(saved.created_at, datetime)
