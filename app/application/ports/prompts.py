"""Порт каталогу промптів. Текст промптів живе у файлах `app/prompts/`, а не в коді."""

from enum import StrEnum
from typing import Protocol


class PromptKey(StrEnum):
    """Значення — шлях `<область>/[<тека>/]<імʼя>` до файлу промпта без розширення."""

    MCP_INSTRUCTIONS = "mcp/instructions"
    ANALYSIS_RUBRIC = "analysis/rubric"
    DOCUMENTS_CV_RULES = "documents/cv_rules"
    DOCUMENTS_COVER_LETTER_RULES = "documents/cover_letter_rules"
    PREP_KIT_RULES = "prep/kit_rules"
    PREP_PLAN_RULES = "prep/plan_rules"
    PREP_QUESTION_RULES = "prep/question_rules"
    PREP_QUIZ_RULES = "prep/quiz_rules"
    PREP_TOPIC_RULES = "prep/topic_rules"
    MCP_TOOL_ADD_JOB = "mcp/tools/add_job"
    MCP_TOOL_ANSWER_GAP = "mcp/tools/answer_gap"
    MCP_TOOL_CONFIRM_FACTS = "mcp/tools/confirm_facts"
    MCP_TOOL_COMPLETE_STEP = "mcp/tools/complete_step"
    MCP_TOOL_DELETE_FACT = "mcp/tools/delete_fact"
    MCP_TOOL_DISMISS_JOBS = "mcp/tools/dismiss_jobs"
    MCP_TOOL_DUE_QUESTIONS = "mcp/tools/due_questions"
    MCP_TOOL_GET_DOCUMENT_DOWNLOAD = "mcp/tools/get_document_download"
    MCP_TOOL_GET_CV_FUNNEL = "mcp/tools/get_cv_funnel"
    MCP_TOOL_GET_JOB = "mcp/tools/get_job"
    MCP_TOOL_GET_SCENARIO = "mcp/tools/get_scenario"
    MCP_TOOL_GET_TOPIC = "mcp/tools/get_topic"
    MCP_TOOL_GET_MAIL_INBOX = "mcp/tools/get_mail_inbox"
    MCP_TOOL_GET_ORIGINAL_CV = "mcp/tools/get_original_cv"
    MCP_TOOL_GET_PROFILE = "mcp/tools/get_profile"
    MCP_TOOL_GET_SOURCES = "mcp/tools/get_sources"
    MCP_TOOL_LIST_DOCUMENTS = "mcp/tools/list_documents"
    MCP_TOOL_LIST_FACTS = "mcp/tools/list_facts"
    MCP_TOOL_LIST_JOBS = "mcp/tools/list_jobs"
    MCP_TOOL_LIST_PHOTOS = "mcp/tools/list_photos"
    MCP_TOOL_LIST_PREP_TOPICS = "mcp/tools/list_prep_topics"
    MCP_TOOL_LIST_REPLIES = "mcp/tools/list_replies"
    MCP_TOOL_MARK_APPLIED = "mcp/tools/mark_applied"
    MCP_TOOL_PREPARE_ANALYSIS = "mcp/tools/prepare_analysis"
    MCP_TOOL_PREPARE_COVER_LETTER = "mcp/tools/prepare_cover_letter"
    MCP_TOOL_PREPARE_CV = "mcp/tools/prepare_cv"
    MCP_TOOL_PREPARE_INTERVIEW_KIT = "mcp/tools/prepare_interview_kit"
    MCP_TOOL_PREPARE_PREP_TOPICS = "mcp/tools/prepare_prep_topics"
    MCP_TOOL_PREPARE_QUESTIONS = "mcp/tools/prepare_questions"
    MCP_TOOL_PREPARE_TOPIC_PLAN = "mcp/tools/prepare_topic_plan"
    MCP_TOOL_PREPARE_TRIAGE = "mcp/tools/prepare_triage"
    MCP_TOOL_RECORD_ANSWER = "mcp/tools/record_answer"
    MCP_TOOL_REFRESH_SOURCES = "mcp/tools/refresh_sources"
    MCP_TOOL_RESTORE_JOB = "mcp/tools/restore_job"
    MCP_TOOL_REVIEW_REPLY = "mcp/tools/review_reply"
    MCP_TOOL_SAVE_ANALYSIS = "mcp/tools/save_analysis"
    MCP_TOOL_SAVE_COVER_LETTER = "mcp/tools/save_cover_letter"
    MCP_TOOL_SAVE_CV = "mcp/tools/save_cv"
    MCP_TOOL_CHECK_CV = "mcp/tools/check_cv"
    MCP_TOOL_CHECK_COVER_LETTER = "mcp/tools/check_cover_letter"
    MCP_TOOL_SAVE_FACTS = "mcp/tools/save_facts"
    MCP_TOOL_SAVE_INTERVIEW_KIT = "mcp/tools/save_interview_kit"
    MCP_TOOL_SAVE_PREP_TOPICS = "mcp/tools/save_prep_topics"
    MCP_TOOL_SAVE_QUESTIONS = "mcp/tools/save_questions"
    MCP_TOOL_SAVE_TOPIC_PLAN = "mcp/tools/save_topic_plan"
    MCP_TOOL_SAVE_TRIAGE = "mcp/tools/save_triage"
    MCP_TOOL_SET_APPLICATION_STATUS = "mcp/tools/set_application_status"
    MCP_TOOL_SET_TOPIC_READY = "mcp/tools/set_topic_ready"
    MCP_TOOL_SAVE_ORIGINAL_CV = "mcp/tools/save_original_cv"
    MCP_TOOL_UPDATE_FACT = "mcp/tools/update_fact"
    MCP_TOOL_UPDATE_PROFILE = "mcp/tools/update_profile"
    MAIL_REVIEW_RULES = "mail/review_rules"
    TRIAGE_RULES = "triage/rules"
    ONBOARDING_SETUP = "onboarding/setup"
    SCENARIO_NEXT_STEP = "scenarios/next_step"
    REQUEST_ANALYSIS = "requests/analysis"
    REQUEST_TRIAGE = "requests/triage"
    REQUEST_CV = "requests/cv"
    REQUEST_COVER_LETTER = "requests/cover_letter"
    REQUEST_PLAN = "requests/plan"
    REQUEST_QUESTIONS = "requests/questions"
    REQUEST_QUIZ = "requests/quiz"
    REQUEST_QUIZ_TOPIC = "requests/quiz_topic"
    REQUEST_TOPICS = "requests/topics"
    REQUEST_JOB_PREP = "requests/job_prep"
    REQUEST_INTERVIEW_KIT = "requests/interview_kit"
    REQUEST_GAPS = "requests/gaps"
    REQUEST_FACTS = "requests/facts"
    REQUEST_ADD_JOB = "requests/add_job"
    REQUEST_REANALYSIS = "requests/reanalysis"
    REQUEST_APPLY = "requests/apply"


# Промпти, які бачить веб: готові тексти для агента, а не правила для моделі. Шаблони (`{job_id}`,
# `{topic_id}`) веб підставляє сам; `GET /prompts` віддає їх дослівно.
WEB_PROMPT_KEYS = tuple(
    key for key in PromptKey if key.value.startswith(("onboarding/", "requests/"))
)


class PromptsUnavailableError(Exception):
    """Промпт не вдалося прочитати: файлу нема або він не UTF-8. Повідомлення називає файл."""


class Prompts(Protocol):
    def get(self, key: PromptKey) -> str:
        """Текст промпта дослівно, як у файлі."""
        ...
