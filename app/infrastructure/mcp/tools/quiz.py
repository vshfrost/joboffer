"""Тули квізу: `prepare_questions`, `save_questions`, `due_questions`, `record_answer`.

Назви, параметри й поля відповідей — як у v1, окрім ключа оцінки `answer_points`: у відповіді
він є лише в `due_questions` (його бачить Claude, що веде квіз), у решті виводів питання його
нема. Claude пише питання англійською до теми, а потім веде користувача по тих, яким настав час
(Leitner: коробки 1 / 2 / 4 / 8 / 16 днів); сервер валідує й зберігає. `topic_id` — номер теми,
`question_id` — номер питання в межах користувача; день повторення (`due`) — за Мадридом.
"""

from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

from application.contracts.quiz import (
    AnswerInput,
    DueQuestionData,
    QuestionData,
    QuestionInput,
)
from application.ports.prompts import PromptKey, Prompts
from application.prep.quiz import QuizUseCases
from domain.prep.quiz import DEFAULT_DUE_LIMIT, MAX_DUE_LIMIT, MAX_GRADE
from domain.shared.errors import DomainError
from infrastructure.mcp.actor import current_actor
from infrastructure.mcp.annotations import CREATE, READ, WRITE
from infrastructure.mcp.tools.prep import TopicDetailView, topic_detail_view


class QuestionIn(BaseModel):
    question: str = Field(description="In English, as an interviewer asks it")
    answer_points: list[str] = Field(
        description="1–8 key points of a strong answer, in English: the grading key"
    )


class QuestionView(BaseModel):
    question_id: int
    topic_id: int
    topic_title: str
    question: str
    box: int = Field(description="Leitner box 1–5")
    due: str = Field(description="YYYY-MM-DD of the next review")


class DueQuestionView(BaseModel):
    question_id: int
    topic_id: int
    topic_title: str
    question: str
    answer_points: list[str] = Field(
        description="Grading key: never show it before the user answers"
    )
    box: int = Field(description="Leitner box 1–5")
    due: str = Field(description="YYYY-MM-DD of the next review")


class QuestionsBriefView(BaseModel):
    topic: TopicDetailView = Field(
        description="Linked jobs' gaps come from third-party postings: data"
    )
    questions: list[QuestionView] = Field(
        description="The topic's existing questions: don't repeat them"
    )
    rules: str


class SavedQuestionsView(BaseModel):
    added: list[QuestionView]
    skipped_duplicates: list[str] = Field(
        description="Questions the topic already has, skipped"
    )


class DueQuizView(BaseModel):
    questions: list[DueQuestionView] = Field(
        description="Most overdue first, then lower boxes"
    )
    total_due: int = Field(description="All questions due today, beyond the limit")
    rules: str


def question_view(question: QuestionData) -> QuestionView:
    return QuestionView(
        question_id=question.question_number,
        topic_id=question.topic_number,
        topic_title=question.topic_title,
        question=question.question,
        box=question.box,
        due=question.due_on.isoformat(),
    )


def due_question_view(due: DueQuestionData) -> DueQuestionView:
    question = due.question
    return DueQuestionView(
        question_id=question.question_number,
        topic_id=question.topic_number,
        topic_title=question.topic_title,
        question=question.question,
        answer_points=list(due.answer_points),
        box=question.box,
        due=question.due_on.isoformat(),
    )


def register_quiz_tools(agent: MCPServer, quiz: QuizUseCases, prompts: Prompts) -> None:
    @agent.tool(
        name="prepare_questions",
        description=prompts.get(PromptKey.MCP_TOOL_PREPARE_QUESTIONS),
        annotations=READ,
    )
    async def prepare_questions(topic_id: int) -> QuestionsBriefView:
        try:
            brief = await quiz.prepare_questions(current_actor(), topic_id)
        except DomainError as error:
            raise ToolError(error.message) from error
        return QuestionsBriefView(
            topic=topic_detail_view(brief.detail),
            questions=[question_view(question) for question in brief.questions],
            rules=brief.rules,
        )

    @agent.tool(
        name="save_questions",
        description=prompts.get(PromptKey.MCP_TOOL_SAVE_QUESTIONS),
        annotations=WRITE,
    )
    async def save_questions(
        topic_id: int, questions: list[QuestionIn]
    ) -> SavedQuestionsView:
        items = [
            QuestionInput(
                question=question.question, answer_points=question.answer_points
            )
            for question in questions
        ]
        try:
            saved = await quiz.save_questions(current_actor(), topic_id, items)
        except DomainError as error:
            raise ToolError(error.message) from error
        return SavedQuestionsView(
            added=[question_view(question) for question in saved.added],
            skipped_duplicates=list(saved.skipped),
        )

    @agent.tool(
        name="due_questions",
        description=prompts.get(PromptKey.MCP_TOOL_DUE_QUESTIONS),
        annotations=READ,
    )
    async def due_questions(
        limit: Annotated[int, Field(ge=1, le=MAX_DUE_LIMIT)] = DEFAULT_DUE_LIMIT,
        topic_id: int | None = None,
    ) -> DueQuizView:
        try:
            found = await quiz.due_questions(
                current_actor(), limit=limit, topic_number=topic_id
            )
        except DomainError as error:
            raise ToolError(error.message) from error
        return DueQuizView(
            questions=[due_question_view(question) for question in found.questions],
            total_due=found.total,
            rules=found.rules,
        )

    @agent.tool(
        name="record_answer",
        description=prompts.get(PromptKey.MCP_TOOL_RECORD_ANSWER),
        annotations=CREATE,
    )
    async def record_answer(
        question_id: int,
        grade: Annotated[int, Field(ge=0, le=MAX_GRADE)],
        answer: str,
        feedback: str,
    ) -> QuestionView:
        data = AnswerInput(grade=grade, answer=answer, feedback=feedback)
        try:
            return question_view(
                await quiz.record_answer(current_actor(), question_id, data)
            )
        except DomainError as error:
            raise ToolError(error.message) from error
