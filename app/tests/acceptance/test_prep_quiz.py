"""Кроки для features/prep_quiz.feature: питання до тем, відповіді з коробками Leitner, що на
повторенні сьогодні (за Мадридом), лічильники по темах. Use cases квізу + in-memory адаптери через
портал.

Світ і допоміжні кроки (користувач, вакансія, тема) — з `test_prep_topics`. Питання й тема — за
номером на користувача; внутрішній UUID у сценаріях не фігурує. Довгі значення для перевірки меж
пишуться як `а×500` (символ, «×», кількість). Ключ оцінки в кроках — `"пункт; пункт"`; питання без
ключа в короткій формі отримують один пункт «Key point».
"""

from datetime import UTC, datetime, timedelta

import pytest
from anyio.from_thread import BlockingPortal
from pytest_bdd import given as bdd_given
from pytest_bdd import scenarios
from pytest_bdd import then as bdd_then
from pytest_bdd import when as bdd_when

from application.contracts.quiz import (
    AnswerInput,
    DueQuizData,
    QuestionData,
    QuestionInput,
    QuestionsBriefData,
    QuizCountData,
    SavedQuestionsData,
)
from application.ports.prompts import PromptKey
from application.prep.quiz import QuizUseCases
from domain.prep.quiz import PastAnswer
from tests.acceptance.test_prep_topics import World as TopicsWorld
from tests.acceptance.test_prep_topics import action, item, rx, text, words
from tests.support.clock import FakeClock
from tests.support.ids import SequentialIds
from tests.support.quiz import InMemoryQuizUnitOfWork, QuizStore

scenarios("features/prep_quiz.feature")

QUESTION_RULES = "Write questions. Then call save_questions."
QUIZ_RULES = "Run the quiz. Then call record_answer."
KEY = ("Key point",)


class QuizPrompts:
    def get(self, key: PromptKey) -> str:
        return {
            PromptKey.PREP_TOPIC_RULES: "Propose topics.",
            PromptKey.PREP_QUESTION_RULES: QUESTION_RULES,
            PromptKey.PREP_QUIZ_RULES: QUIZ_RULES,
        }[key]


class World(TopicsWorld):
    def __init__(
        self, portal: BlockingPortal, clock: FakeClock, ids: SequentialIds
    ) -> None:
        super().__init__(portal, clock, ids)
        self.quiz_store = QuizStore.empty()
        self.quiz = QuizUseCases(
            lambda: InMemoryQuizUnitOfWork(
                self.jobs_store, self.prep_store, self.quiz_store
            ),
            clock,
            ids,
            QuizPrompts(),
        )
        self.questions_brief: QuestionsBriefData | None = None
        self.saved_questions: SavedQuestionsData | None = None
        self.due: DueQuizData | None = None
        self.answered: QuestionData | None = None
        self.counts: dict[int, QuizCountData] | None = None

    def reset_outcome(self) -> None:
        super().reset_outcome()
        self.questions_brief = None
        self.saved_questions = None
        self.due = None
        self.answered = None
        self.counts = None

    def questions_of(self, topic: int) -> tuple[QuestionData, ...]:
        brief: QuestionsBriefData = self.portal.call(
            self.quiz.prepare_questions, self.actor, topic
        )
        return brief.questions

    def question(self, number: int) -> QuestionData | None:
        """Питання за номером користувача: шукає по всіх його темах."""
        for topic in self.topics():
            for found in self.questions_of(topic.topic_number):
                if found.question_number == number:
                    return found
        return None

    def history(self, number: int) -> list[PastAnswer]:
        async def read() -> list[PastAnswer]:
            async with InMemoryQuizUnitOfWork(
                self.jobs_store, self.prep_store, self.quiz_store
            ) as uow:
                return await uow.prep_questions.answers(self.actor.user_id, number)

        history: list[PastAnswer] = self.portal.call(read)
        return history

    def save_questions(self, topic: int, items: list[QuestionInput]) -> None:
        self.saved_questions = self.attempt(
            lambda: self.quiz.save_questions(self.actor, topic, items)
        )

    def answer(self, number: int, grade: int, answer: str, feedback: str) -> None:
        data = AnswerInput(grade=grade, answer=answer, feedback=feedback)
        self.answered = self.attempt(
            lambda: self.quiz.record_answer(self.actor, number, data)
        )


@pytest.fixture
def world(portal: BlockingPortal, clock: FakeClock, ids: SequentialIds) -> World:
    return World(portal, clock, ids)


def question_input(question: str, points: str | None = None) -> QuestionInput:
    """Без `points` питання отримує один типовий пункт ключа; порожній `points` — ключа нема."""
    key = list(KEY) if points is None else [text(point) for point in words(points)]
    return QuestionInput(question=text(question), answer_points=key)


# --- хто я, передумови (як у test_prep_plan) -------------------------------------------------


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
@bdd_when(
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


@action(
    r'^я (?:зберігаю|зберіг) тему "(?P<slug>[^"]*)" для вакансії (?P<job>\d+) з gap "(?P<gap>[^"]*)"$'
)
def save_topic(world: World, slug: str, job: str, gap: str) -> None:
    world.save(int(job), [item(slug, gap)])


@bdd_given(rx(r"^минуло (?P<days>\d+) (?:день|дні|днів)$"))
@bdd_when(rx(r"^минуло (?P<days>\d+) (?:день|дні|днів)$"))
def days_passed(world: World, days: str) -> None:
    world.clock.advance(timedelta(days=int(days)))


@bdd_given(rx(r'^годинник показує "(?P<moment>[^"]*)" за UTC$'))
@bdd_when(rx(r'^годинник показує "(?P<moment>[^"]*)" за UTC$'))
def clock_shows(world: World, moment: str) -> None:
    target = datetime.strptime(moment, "%Y-%m-%d %H:%M").replace(tzinfo=UTC)
    world.clock.advance(target - world.clock.now())


# --- бриф --------------------------------------------------------------------------------------


@bdd_when(rx(r"^я готую питання до теми (?P<topic>\d+)$"))
def prepare_questions(world: World, topic: str) -> None:
    world.questions_brief = world.attempt(
        lambda: world.quiz.prepare_questions(world.actor, int(topic))
    )


def shown_brief(world: World) -> QuestionsBriefData:
    assert world.error is None, world.error
    assert world.questions_brief is not None, "бриф не готували"
    return world.questions_brief


@bdd_then(rx(r'^в брифі тема "(?P<slug>[^"]*)"$'))
def brief_topic(world: World, slug: str) -> None:
    assert shown_brief(world).detail.topic.slug == slug


@bdd_then(rx(r'^у брифі питання за номерами: "(?P<numbers>[^"]*)"$'))
def brief_questions(world: World, numbers: str) -> None:
    shown = [str(q.question_number) for q in shown_brief(world).questions]
    assert shown == words(numbers)


@bdd_then(rx(r"^у брифі питань нема$"))
def brief_no_questions(world: World) -> None:
    assert shown_brief(world).questions == ()


@bdd_then(rx(r'^правила питань у брифі: "(?P<rules>[^"]*)"$'))
def brief_rules(world: World, rules: str) -> None:
    assert shown_brief(world).rules == rules


# --- збереження питань -------------------------------------------------------------------------


@action(r"^я (?:зберігаю|зберіг) питання до теми (?P<topic>\d+):$")
def save_questions_table(world: World, datatable: list[list[str]], topic: str) -> None:
    items = [question_input(question, points) for question, points in datatable[1:]]
    world.save_questions(int(topic), items)


@action(
    r'^я (?:зберігаю|зберіг) питання "(?P<question>[^"]*)" з ключем "(?P<points>[^"]*)" до теми (?P<topic>\d+)$'
)
def save_question_with_key(
    world: World, question: str, points: str, topic: str
) -> None:
    world.save_questions(int(topic), [question_input(question, points)])


@action(
    r'^я (?:зберігаю|зберіг) питання "(?P<questions>[^"]*)" до теми (?P<topic>\d+)$'
)
def save_questions_short(world: World, questions: str, topic: str) -> None:
    items = [question_input(question) for question in words(questions)]
    world.save_questions(int(topic), items)


@action(r"^я (?:зберігаю|зберіг) (?P<count>\d+) питань до теми (?P<topic>\d+)$")
def save_generated(world: World, count: str, topic: str) -> None:
    items = [question_input(f"Question {n}?") for n in range(1, int(count) + 1)]
    world.save_questions(int(topic), items)


@bdd_when(rx(r"^я зберігаю порожній список питань до теми (?P<topic>\d+)$"))
def save_nothing(world: World, topic: str) -> None:
    world.save_questions(int(topic), [])


def shown_saved(world: World) -> SavedQuestionsData:
    assert world.error is None, world.error
    assert world.saved_questions is not None, "питання не зберігали"
    return world.saved_questions


@bdd_then(rx(r"^додано питань (?P<count>\d+)$"))
def added_count(world: World, count: str) -> None:
    assert len(shown_saved(world).added) == int(count)


@bdd_then(rx(r'^додані питання за номерами: "(?P<numbers>[^"]*)"$'))
def added_numbers(world: World, numbers: str) -> None:
    added = [str(q.question_number) for q in shown_saved(world).added]
    assert added == words(numbers)


@bdd_then(rx(r'^пропущено: "(?P<skipped>[^"]*)"$'))
def skipped_questions(world: World, skipped: str) -> None:
    assert list(shown_saved(world).skipped) == [text(s) for s in words(skipped)]


@bdd_then(rx(r"^дублів нема$"))
def no_duplicates(world: World) -> None:
    assert shown_saved(world).skipped == ()


@bdd_then(
    rx(
        r'^питання (?P<number>\d+): коробка (?P<box>\d), повторення "(?P<day>\d{4}-\d{2}-\d{2})"$'
    )
)
def question_schedule(world: World, number: str, box: str, day: str) -> None:
    found = world.question(int(number))
    assert found is not None, f"питання {number} нема"
    assert (found.box, found.due_on.isoformat()) == (int(box), day)


@bdd_then(rx(r"^питання (?P<number>\d+) у темі (?P<topic>\d+) «(?P<title>[^»]*)»$"))
def question_topic(world: World, number: str, topic: str, title: str) -> None:
    found = world.question(int(number))
    assert found is not None, f"питання {number} нема"
    assert (found.topic_number, found.topic_title) == (int(topic), title)


@bdd_then(rx(r"^у темі (?P<topic>\d+) питань (?P<count>\d+)$"))
def topic_question_count(world: World, topic: str, count: str) -> None:
    assert len(world.questions_of(int(topic))) == int(count)


# --- відповіді ---------------------------------------------------------------------------------


@action(
    r"^я (?:відповідаю|відповів) на питання (?P<number>\d+) оцінкою (?P<grade>-?\d+)"
    r'(?: відповіддю "(?P<answer>[^"]*)")?(?: фідбеком "(?P<feedback>[^"]*)")?$'
)
def answer_question(
    world: World,
    number: str,
    grade: str,
    answer: str | None,
    feedback: str | None,
) -> None:
    world.answer(int(number), int(grade), text(answer or ""), text(feedback or ""))


@action(
    r'^я (?:відповідаю|відповів) на питання (?P<number>\d+) оцінками "(?P<grades>[^"]*)"$'
)
def answer_with_grades(world: World, number: str, grades: str) -> None:
    for grade in words(grades.replace(",", ";")):
        world.answer(int(number), int(grade), "", "")
        assert world.error is None, world.error


@bdd_then(
    rx(
        r'^відповідь повернула питання (?P<number>\d+): коробка (?P<box>\d), повторення "(?P<day>\d{4}-\d{2}-\d{2})"$'
    )
)
def returned_question(world: World, number: str, box: str, day: str) -> None:
    assert world.error is None, world.error
    assert world.answered is not None, "відповіді не було"
    assert (
        world.answered.question_number,
        world.answered.box,
        world.answered.due_on.isoformat(),
    ) == (int(number), int(box), day)


@bdd_then(rx(r"^повернуте питання збігається з прочитаним$"))
def returned_equals_read(world: World) -> None:
    assert world.error is None, world.error
    assert world.answered is not None, "відповіді не було"
    assert world.answered == world.question(world.answered.question_number)


@bdd_then(rx(r"^в історії питання (?P<number>\d+) записів (?P<count>\d+)$"))
def history_size(world: World, number: str, count: str) -> None:
    assert len(world.history(int(number))) == int(count)


@bdd_then(
    rx(
        r"^запис (?P<index>\d+) історії питання (?P<number>\d+): оцінка (?P<grade>\d), "
        r'відповідь "(?P<answer>[^"]*)", фідбек "(?P<feedback>[^"]*)", коробка (?P<box>\d)$'
    )
)
def history_entry(
    world: World,
    index: str,
    number: str,
    grade: str,
    answer: str,
    feedback: str,
    box: str,
) -> None:
    entry = world.history(int(number))[int(index) - 1]
    assert (entry.grade, entry.answer, entry.feedback, entry.box) == (
        int(grade),
        text(answer),
        text(feedback),
        int(box),
    )


@bdd_then(
    rx(
        r'^запис (?P<index>\d+) історії питання (?P<number>\d+) зроблено "(?P<moment>[^"]*)" за UTC$'
    )
)
def history_moment(world: World, index: str, number: str, moment: str) -> None:
    entry = world.history(int(number))[int(index) - 1]
    assert f"{entry.answered_at:%Y-%m-%d %H:%M}" == moment


# --- квіз: що на повторенні --------------------------------------------------------------------


@bdd_when(
    rx(r"^я проходжу квіз(?: з лімітом (?P<limit>-?\d+))?(?: по темі (?P<topic>\d+))?$")
)
def run_quiz(world: World, limit: str | None, topic: str | None) -> None:
    if limit is None:
        world.due = world.attempt(
            lambda: world.quiz.due_questions(
                world.actor, topic_number=int(topic) if topic else None
            )
        )
    else:
        world.due = world.attempt(
            lambda: world.quiz.due_questions(
                world.actor,
                limit=int(limit),
                topic_number=int(topic) if topic else None,
            )
        )


def shown_quiz(world: World) -> DueQuizData:
    assert world.error is None, world.error
    assert world.due is not None, "квіз не проходили"
    return world.due


@bdd_then(rx(r'^у квізі питання за порядком: "(?P<numbers>[^"]*)"$'))
def quiz_order(world: World, numbers: str) -> None:
    shown = [str(d.question.question_number) for d in shown_quiz(world).questions]
    assert shown == words(numbers)


@bdd_then(rx(r"^у квізі питань нема$"))
def quiz_empty(world: World) -> None:
    assert shown_quiz(world).questions == ()


@bdd_then(rx(r"^у квізі питань (?P<count>\d+)$"))
def quiz_size(world: World, count: str) -> None:
    assert len(shown_quiz(world).questions) == int(count)


@bdd_then(rx(r"^усього на сьогодні (?P<total>\d+)$"))
def quiz_total(world: World, total: str) -> None:
    assert shown_quiz(world).total == int(total)


@bdd_then(rx(r'^правила квізу: "(?P<rules>[^"]*)"$'))
def quiz_rules(world: World, rules: str) -> None:
    assert shown_quiz(world).rules == rules


@bdd_then(rx(r'^у квізі питання (?P<number>\d+) має ключ "(?P<points>[^"]*)"$'))
def quiz_key(world: World, number: str, points: str) -> None:
    found = [
        d
        for d in shown_quiz(world).questions
        if d.question.question_number == int(number)
    ]
    assert len(found) == 1, found
    assert list(found[0].answer_points) == words(points)


@bdd_then(
    rx(
        r"^у квізі питання (?P<number>\d+) із теми (?P<topic>\d+) «(?P<title>[^»]*)», коробка (?P<box>\d)$"
    )
)
def quiz_question(world: World, number: str, topic: str, title: str, box: str) -> None:
    found = [
        d.question
        for d in shown_quiz(world).questions
        if d.question.question_number == int(number)
    ]
    assert len(found) == 1, found
    assert (found[0].topic_number, found[0].topic_title, found[0].box) == (
        int(topic),
        title,
        int(box),
    )


# --- лічильники по темах -----------------------------------------------------------------------


@bdd_when(rx(r"^я рахую питання по темах$"))
def count_questions(world: World) -> None:
    world.counts = world.attempt(lambda: world.quiz.count_questions(world.actor))


@bdd_then(
    rx(r"^по темі (?P<topic>\d+) питань (?P<total>\d+), на повторенні (?P<due>\d+)$")
)
def topic_counts(world: World, topic: str, total: str, due: str) -> None:
    assert world.error is None, world.error
    assert world.counts is not None, "питання не рахували"
    assert int(topic) in world.counts, world.counts
    shown = world.counts[int(topic)]
    assert (shown.total, shown.due) == (int(total), int(due))


@bdd_then(rx(r"^по темі (?P<topic>\d+) лічильника нема$"))
def no_topic_counts(world: World, topic: str) -> None:
    assert world.error is None, world.error
    assert world.counts is not None, "питання не рахували"
    assert int(topic) not in world.counts


# --- результат ---------------------------------------------------------------------------------


@bdd_then(rx(r'^отримую помилку "(?P<code>[^"]*)" з текстом "(?P<message>[^"]*)"$'))
def error_message(world: World, code: str, message: str) -> None:
    assert world.error is not None, "помилки не було"
    assert (world.error.code, world.error.message) == (code, text(message))
