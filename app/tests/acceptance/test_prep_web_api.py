"""Кроки для features/prep_web_api.feature: реєстр тем, сторінка теми, «виконано» з нотаткою, «готово»
і підготовка до вакансії для вебу. Use cases вебу (поверх тем, плану й квізу) + in-memory адаптери
через портал.

Світ і допоміжні кроки (користувач, вакансія, тема, план, питання) — з `test_prep_topics`,
`test_prep_plan` і `test_prep_quiz`. Тема, крок і питання — за номером на користувача. Довгі значення
для перевірки меж пишуться як `а×2000` (символ, «×», кількість). Усе, що показав реєстр, сторінка чи
підготовка до вакансії, зводиться до рядків теми: кроки «Тоді» читають їх, не знаючи звідки вони.
"""

import re
from datetime import UTC, datetime, timedelta

import pytest
from anyio.from_thread import BlockingPortal
from pytest_bdd import given as bdd_given
from pytest_bdd import scenarios
from pytest_bdd import then as bdd_then
from pytest_bdd import when as bdd_when

from application.contracts.prep import StepData, TopicJobData
from application.contracts.prep_web import (
    JobPrepData,
    TopicBoardData,
    TopicPageData,
    TopicRowData,
)
from application.contracts.quiz import AnswerInput, QuestionInput
from application.prep.quiz import QuizUseCases
from application.prep.web import PrepWebUseCases
from domain.shared.errors import InvalidValue
from domain.shared.local_time import local_day
from tests.acceptance.test_prep_plan import World as PlanWorld
from tests.acceptance.test_prep_plan import plan_steps
from tests.acceptance.test_prep_quiz import QuizPrompts
from tests.acceptance.test_prep_topics import action, item, rx, text, words
from tests.support.clock import FakeClock
from tests.support.ids import SequentialIds
from tests.support.quiz import InMemoryQuizUnitOfWork, QuizStore

scenarios("features/prep_web_api.feature")

FIELD = re.compile(r'([^\s"]+) "([^"]*)"')
KEY = ("Key point",)


class World(PlanWorld):
    def __init__(
        self, portal: BlockingPortal, clock: FakeClock, ids: SequentialIds
    ) -> None:
        super().__init__(portal, clock, ids)
        self.quiz_store = QuizStore.empty()

        def unit_of_work() -> InMemoryQuizUnitOfWork:
            return InMemoryQuizUnitOfWork(
                self.jobs_store, self.prep_store, self.quiz_store
            )

        self.quiz = QuizUseCases(unit_of_work, clock, ids, QuizPrompts())
        self.web = PrepWebUseCases(unit_of_work, clock, self.prep)
        self.rows: list[TopicRowData] = []
        self.board: TopicBoardData | None = None
        self.page: TopicPageData | None = None
        self.job_prep: JobPrepData | None = None

    def reset_outcome(self) -> None:
        super().reset_outcome()
        self.rows = []
        self.board = None
        self.page = None
        self.job_prep = None

    def show_page(self, page: TopicPageData | None) -> None:
        self.page = page
        if page is not None:
            self.rows = [
                TopicRowData(
                    topic=page.detail.topic, percent=page.percent, quiz=page.quiz
                )
            ]

    def row(self, slug: str) -> TopicRowData:
        assert self.error is None, self.error
        found = [row for row in self.rows if row.topic.slug == slug]
        assert len(found) == 1, (slug, [row.topic.slug for row in self.rows])
        return found[0]

    def shown_page(self) -> TopicPageData:
        assert self.error is None, self.error
        assert self.page is not None, "сторінку теми не показували"
        return self.page

    def page_step(self, number: int) -> StepData:
        found = [
            step
            for step in self.shown_page().detail.steps
            if step.step_number == number
        ]
        assert len(found) == 1, (number, found)
        return found[0]


@pytest.fixture
def world(portal: BlockingPortal, clock: FakeClock, ids: SequentialIds) -> World:
    return World(portal, clock, ids)


# --- хто я, передумови (як у test_prep_plan і test_prep_quiz) ------------------------------------


@bdd_given(rx(r'^я — користувач "(?P<name>[^"]*)"$'))
@bdd_given(rx(r'^я стаю користувачем "(?P<name>[^"]*)"$'))
@bdd_when(rx(r'^я стаю користувачем "(?P<name>[^"]*)"$'))
def become_user(world: World, name: str) -> None:
    world.become(name)


@bdd_given(
    rx(
        r'^є проаналізована вакансія "(?P<title>[^"]*)"(?: компанії "(?P<company>[^"]*)")?'
        r' зі скором (?P<score>\d+)(?: і прогалинами "(?P<gaps>[^"]*)")?$'
    )
)
def analysed_job(
    world: World, title: str, company: str | None, score: str, gaps: str | None
) -> None:
    world.add_job(title, company or "")
    number = len(
        [key for key in world.jobs_store.jobs if key[0] == world.actor.user_id]
    )
    world.analyse(number, int(score), words(gaps or ""))


@bdd_given(rx(r'^є вакансія "(?P<title>[^"]*)" без аналізу$'))
def raw_job(world: World, title: str) -> None:
    world.add_job(title, "")


@action(
    r'^я (?:зберіг|зберігаю) тему "(?P<slug>[^"]*)" для вакансії (?P<job>\d+) з gap "(?P<gap>[^"]*)"'
    r'(?P<fields>(?:, [^\s"]+ "[^"]*")*)$'
)
def save_topic(world: World, slug: str, job: str, gap: str, fields: str) -> None:
    values = dict(FIELD.findall(fields))
    world.save(
        int(job),
        [
            item(
                slug,
                gap,
                kind=values.get("вид", "tech"),
                deadline=values.get("дедлайн", ""),
            )
        ],
    )


@action(
    r'^я (?:зберіг|зберігаю) план теми (?P<topic>\d+) з кроками "(?P<kinds>[^"]*)"$'
)
def save_plan(world: World, topic: str, kinds: str) -> None:
    world.attempt(
        lambda: world.prep.save_topic_plan(world.actor, int(topic), plan_steps(kinds))
    )


@bdd_given(
    rx(
        r'^я зберіг план теми (?P<topic>\d+) з кроками "(?P<kinds>[^"]*)", де крок (?P<index>\d+): '
        r'(?P<fields>(?:[^\s"]+ "[^"]*"(?:, )?)+)$'
    )
)
def save_plan_with_step(
    world: World, topic: str, kinds: str, index: str, fields: str
) -> None:
    steps = plan_steps(kinds, int(index), dict(FIELD.findall(fields)))
    world.attempt(lambda: world.prep.save_topic_plan(world.actor, int(topic), steps))
    assert world.error is None, world.error


@action(
    r'^я (?:зберіг|зберігаю) питання "(?P<questions>[^"]*)" до теми (?P<topic>\d+)$'
)
def save_questions(world: World, questions: str, topic: str) -> None:
    items = [QuestionInput(question=q, answer_points=KEY) for q in words(questions)]
    world.attempt(lambda: world.quiz.save_questions(world.actor, int(topic), items))


@action(
    r"^я (?:відповідаю|відповів) на питання (?P<number>\d+) оцінкою (?P<grade>\d+)$"
)
def answer_question(world: World, number: str, grade: str) -> None:
    data = AnswerInput(grade=int(grade))
    world.attempt(lambda: world.quiz.record_answer(world.actor, int(number), data))


@action(
    r'^я (?:завершую|завершив) крок (?P<step>\d+)(?: з нотаткою "(?P<note>[^"]*)")?$'
)
def complete_step(world: World, step: str, note: str | None) -> None:
    world.show_page(
        world.attempt(
            lambda: world.web.complete_step(world.actor, int(step), text(note or ""))
        )
    )


@action(r"^я (?:позначаю|позначив) тему (?P<topic>\d+) готовою$")
def mark_ready(world: World, topic: str) -> None:
    world.show_page(
        world.attempt(
            lambda: world.web.set_topic_ready(world.actor, int(topic), ready=True)
        )
    )


@action(r"^я (?:знімаю|зняв) позначку «готово» з теми (?P<topic>\d+)$")
def unmark_ready(world: World, topic: str) -> None:
    world.show_page(
        world.attempt(
            lambda: world.web.set_topic_ready(world.actor, int(topic), ready=False)
        )
    )


@bdd_given(rx(r"^минуло (?P<days>\d+) (?:день|дні|днів)$"))
@bdd_when(rx(r"^минуло (?P<days>\d+) (?:день|дні|днів)$"))
def days_passed(world: World, days: str) -> None:
    world.clock.advance(timedelta(days=int(days)))


@bdd_given(rx(r'^годинник показує "(?P<moment>[^"]*)" за UTC$'))
def clock_shows(world: World, moment: str) -> None:
    target = datetime.strptime(moment, "%Y-%m-%d %H:%M").replace(tzinfo=UTC)
    world.clock.advance(target - world.clock.now())


# --- перегляд ----------------------------------------------------------------------------------


@bdd_when(rx(r"^я переглядаю реєстр підготовки$"))
def view_board(world: World) -> None:
    world.board = world.attempt(lambda: world.web.topics(world.actor))
    if world.board is not None:
        world.rows = list(world.board.topics)


@bdd_when(rx(r"^я дивлюся сторінку теми (?P<topic>\d+)$"))
def view_page(world: World, topic: str) -> None:
    world.show_page(world.attempt(lambda: world.web.topic(world.actor, int(topic))))


@bdd_when(rx(r"^я дивлюся підготовку до вакансії (?P<job>\d+)$"))
def view_job_prep(world: World, job: str) -> None:
    world.job_prep = world.attempt(lambda: world.web.job_prep(world.actor, int(job)))
    if world.job_prep is not None:
        world.rows = list(world.job_prep.topics)


# --- рядки теми --------------------------------------------------------------------------------


@bdd_then(rx(r'^теми за порядком: "(?P<slugs>[^"]*)"$'))
def topics_in_order(world: World, slugs: str) -> None:
    assert world.error is None, world.error
    assert [row.topic.slug for row in world.rows] == words(slugs)


@bdd_then(rx(r'^тема "(?P<slug>[^"]*)": пріоритет (?P<priority>\d+)$'))
def topic_priority(world: World, slug: str, priority: str) -> None:
    assert world.row(slug).topic.priority == int(priority)


@bdd_then(
    rx(
        r'^тема "(?P<slug>[^"]*)": статус "(?P<status>[^"]*)", (?P<percent>\d+)%, '
        r"виконано (?P<done>\d+) з (?P<total>\d+), лишилось (?P<minutes>\d+) хв$"
    )
)
def topic_progress(
    world: World,
    slug: str,
    status: str,
    percent: str,
    done: str,
    total: str,
    minutes: str,
) -> None:
    row = world.row(slug)
    assert (
        row.topic.status.value,
        row.percent,
        row.topic.steps_done,
        row.topic.steps_total,
        row.topic.minutes_left,
    ) == (status, int(percent), int(done), int(total), int(minutes))


@bdd_then(
    rx(
        r'^тема "(?P<slug>[^"]*)": вид "(?P<kind>[^"]*)", дедлайн "(?P<deadline>[^"]*)"$'
    )
)
def topic_kind_and_deadline(world: World, slug: str, kind: str, deadline: str) -> None:
    topic = world.row(slug).topic
    shown = "немає" if topic.deadline is None else topic.deadline.isoformat()
    assert (topic.kind.value, shown) == (kind, deadline)


def job_line(job: TopicJobData) -> str:
    company = "" if job.company is None else f" ({job.company})"
    return f"{job.job_number} {job.title}{company} скор {job.score}: {job.gap}"


@bdd_then(rx(r'^тема "(?P<slug>[^"]*)" прив\'язана до вакансій: "(?P<jobs>[^"]*)"$'))
def topic_jobs(world: World, slug: str, jobs: str) -> None:
    assert [job_line(job) for job in world.row(slug).topic.jobs] == words(jobs)


@bdd_then(
    rx(
        r'^тема "(?P<slug>[^"]*)": квіз усього (?P<total>\d+), на повторенні (?P<due>\d+)$'
    )
)
def topic_quiz(world: World, slug: str, total: str, due: str) -> None:
    quiz = world.row(slug).quiz
    assert (quiz.total, quiz.due) == (int(total), int(due))


@bdd_then(rx(r"^загальний квіз: усього (?P<total>\d+), на повторенні (?P<due>\d+)$"))
def board_quiz(world: World, total: str, due: str) -> None:
    assert world.error is None, world.error
    assert world.board is not None, "реєстр не переглядали"
    assert (world.board.quiz.total, world.board.quiz.due) == (int(total), int(due))


# --- сторінка теми -----------------------------------------------------------------------------


@bdd_then(
    rx(
        r'^крок (?P<step>\d+) на сторінці: вид "(?P<kind>[^"]*)", назва "(?P<title>[^"]*)", '
        r'хвилин (?P<minutes>\d+), деталі "(?P<details>[^"]*)", ресурси "(?P<links>[^"]*)"$'
    )
)
def page_step_content(
    world: World,
    step: str,
    kind: str,
    title: str,
    minutes: str,
    details: str,
    links: str,
) -> None:
    found = world.page_step(int(step))
    shown = [f"{r.title} | {r.url}" for r in found.resources]
    assert (found.kind.value, found.title, found.minutes, found.details, shown) == (
        kind,
        title,
        int(minutes),
        details,
        words(links),
    )


@bdd_then(
    rx(
        r'^крок (?P<step>\d+) на сторінці виконано (?P<day>\d{4}-\d{2}-\d{2}) з нотаткою "(?P<note>[^"]*)"$'
    )
)
def page_step_done(world: World, step: str, day: str, note: str) -> None:
    found = world.page_step(int(step))
    assert found.done_at is not None, f"крок {step} не виконано"
    assert (local_day(found.done_at), found.note) == (day, text(note))


@bdd_then(rx(r"^крок (?P<step>\d+) на сторінці не виконано$"))
def page_step_pending(world: World, step: str) -> None:
    assert world.page_step(int(step)).done_at is None


@bdd_then(rx(r"^наступний крок на сторінці — (?P<step>\d+)$"))
def page_next_step(world: World, step: str) -> None:
    assert world.shown_page().detail.next_step_number == int(step)


@bdd_then(rx(r"^наступного кроку на сторінці нема$"))
def page_no_next_step(world: World) -> None:
    assert world.shown_page().detail.next_step_number is None


@bdd_then(rx(r"^крок (?P<step>\d+) теми (?P<topic>\d+) не виконано$"))
def step_pending(world: World, step: str, topic: str) -> None:
    found = [s for s in world.read(int(topic)).steps if s.step_number == int(step)]
    assert len(found) == 1
    assert found[0].done_at is None


# --- підготовка до вакансії --------------------------------------------------------------------


@bdd_then(rx(r"^готовність до вакансії (?P<percent>\d+)%$"))
def job_readiness(world: World, percent: str) -> None:
    assert world.error is None, world.error
    assert world.job_prep is not None, "підготовку до вакансії не дивились"
    assert world.job_prep.readiness == int(percent)


@bdd_then(rx(r"^готовності до вакансії нема$"))
def job_without_readiness(world: World) -> None:
    assert world.error is None, world.error
    assert world.job_prep is not None, "підготовку до вакансії не дивились"
    assert world.job_prep.readiness is None


# --- результат ---------------------------------------------------------------------------------


@bdd_then(rx(r'^отримую помилку "(?P<code>[^"]*)" з текстом "(?P<message>[^"]*)"$'))
def error_message(world: World, code: str, message: str) -> None:
    assert world.error is not None, "помилки не було"
    assert (world.error.code, world.error.message) == (code, text(message))


@bdd_then(rx(r'^помилка стосується поля "(?P<field>[^"]*)"$'))
def error_field(world: World, field: str) -> None:
    assert isinstance(world.error, InvalidValue), world.error
    assert world.error.field == field
