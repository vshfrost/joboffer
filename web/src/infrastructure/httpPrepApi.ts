import {
  KIT_QUESTION_KINDS,
  STEP_KINDS,
  TOPIC_KINDS,
  TOPIC_STATUSES,
  type InterviewKit,
  type JobPrep,
  type KitQuestion,
  type KitQuestionKind,
  type KitStory,
  type QuizCount,
  type Step,
  type StepKind,
  type StepResource,
  type Topic,
  type TopicJob,
  type TopicKind,
  type TopicRow,
  type TopicStatus,
} from "../domain/prep";
import { PrepNotFoundError, PrepUnauthorizedError, PrepUnavailableError, PrepValidationError } from "../domain/prepErrors";
import type { PrepApi } from "../ports/prepApi";
import type { ApiClient, ApiResponse } from "./apiClient";

const CONTRACT = "Відповідь сервера не за контрактом";
const INVALID_NOTE = "Нотатка не пройшла перевірку";

export function createHttpPrepApi(client: ApiClient): PrepApi {
  return {
    async topics() {
      const response = await requestOrUnavailable(() => client.request("GET", "/prep/topics"));
      const record = asRecord(okBody(response));
      return { topics: arrayOf(record, "topics").map(readRow), quiz: readQuiz(record["quiz"]) };
    },

    async topic(topicId) {
      const response = await requestOrUnavailable(() => client.request("GET", `/prep/topics/${topicId}`));
      return readTopic(okBody(response, true));
    },

    async completeStep(stepId, note) {
      const response = await requestOrUnavailable(() => client.request("POST", `/prep/steps/${stepId}/done`, { note }));
      if (response.status === 422) {
        throw readValidation(response);
      }
      return readTopic(okBody(response, true));
    },

    async setReady(topicId, ready) {
      const response = await requestOrUnavailable(() => client.request("PUT", `/prep/topics/${topicId}/ready`, { ready }));
      return readTopic(okBody(response, true));
    },

    async jobPrep(jobId) {
      const response = await requestOrUnavailable(() => client.request("GET", `/jobs/${jobId}/prep`));
      return readJobPrep(okBody(response, true));
    },

    async interviewKit(jobId) {
      const response = await requestOrUnavailable(() => client.request("GET", `/jobs/${jobId}/interview-kit`));
      return readKit(okBody(response, true));
    },
  };
}

/** Тіло успішної (200) відповіді; решта статусів — окремі помилки. */
function okBody(response: ApiResponse, notFound = false): unknown {
  if (response.status === 401) {
    throw new PrepUnauthorizedError();
  }
  if (notFound && response.status === 404) {
    throw new PrepNotFoundError();
  }
  if (response.status !== 200) {
    throw new PrepUnavailableError(`Підготовка: відповідь ${response.status}`);
  }
  return response.body;
}

async function requestOrUnavailable<T>(call: () => Promise<T>): Promise<T> {
  try {
    return await call();
  } catch {
    // API-клієнт кидає лише збій мережі.
    throw new PrepUnavailableError("Мережа недоступна");
  }
}

function messageOf(body: unknown): string | null {
  return isRecord(body) && typeof body["message"] === "string" && body["message"] !== "" ? body["message"] : null;
}

/** `{message, field_errors: [{field, message}]}` → помилка перевірки; без розпізнаних полів — збій контракту. */
function readValidation(response: ApiResponse): PrepValidationError | PrepUnavailableError {
  const items = isRecord(response.body) ? response.body["field_errors"] : undefined;
  if (!Array.isArray(items)) {
    return contract();
  }
  const fieldErrors: Record<string, string> = {};
  for (const item of items) {
    if (!isRecord(item) || typeof item["field"] !== "string" || typeof item["message"] !== "string") {
      return contract();
    }
    fieldErrors[item["field"]] ??= item["message"];
  }
  return Object.keys(fieldErrors).length === 0 ? contract() : new PrepValidationError(messageOf(response.body) ?? INVALID_NOTE, fieldErrors);
}

function readQuiz(value: unknown): QuizCount {
  const quiz = asRecord(value);
  return { total: numberOf(quiz, "total"), due: numberOf(quiz, "due") };
}

function readJob(value: unknown): TopicJob {
  const job = asRecord(value);
  return {
    jobId: numberOf(job, "job_id"),
    title: stringOrNull(job, "title"),
    company: stringOrNull(job, "company"),
    score: numberOf(job, "score"),
    gap: stringOf(job, "gap"),
  };
}

function readRow(value: unknown): TopicRow {
  const row = asRecord(value);
  return {
    id: numberOf(row, "topic_id"),
    slug: stringOf(row, "slug"),
    title: stringOf(row, "title"),
    kind: oneOf<TopicKind>(row, "kind", TOPIC_KINDS),
    summary: stringOf(row, "summary"),
    status: oneOf<TopicStatus>(row, "status", TOPIC_STATUSES),
    percent: numberOf(row, "percent"),
    stepsDone: numberOf(row, "steps_done"),
    stepsTotal: numberOf(row, "steps_total"),
    minutesLeft: numberOf(row, "minutes_left"),
    deadline: stringOrNull(row, "deadline"),
    priority: numberOf(row, "priority"),
    jobs: arrayOf(row, "jobs").map(readJob),
    quiz: readQuiz(row["quiz"]),
  };
}

function readResource(value: unknown): StepResource {
  const resource = asRecord(value);
  return { title: stringOf(resource, "title"), url: stringOf(resource, "url") };
}

function readStep(value: unknown): Step {
  const step = asRecord(value);
  return {
    id: numberOf(step, "step_id"),
    position: numberOf(step, "position"),
    kind: oneOf<StepKind>(step, "kind", STEP_KINDS),
    title: stringOf(step, "title"),
    minutes: numberOf(step, "minutes"),
    details: stringOf(step, "details"),
    resources: arrayOf(step, "resources").map(readResource),
    doneOn: stringOrNull(step, "done_on"),
    note: stringOf(step, "note"),
  };
}

function readTopic(value: unknown): Topic {
  const topic = asRecord(value);
  return { ...readRow(topic), nextStepId: topic["next_step_id"] === null ? null : numberOf(topic, "next_step_id"), steps: arrayOf(topic, "steps").map(readStep) };
}

function readJobPrep(value: unknown): JobPrep {
  const prep = asRecord(value);
  return { readiness: prep["readiness"] === null ? null : numberOf(prep, "readiness"), topics: arrayOf(prep, "topics").map(readRow) };
}

function readQuestion(value: unknown): KitQuestion {
  const question = asRecord(value);
  return {
    kind: oneOf<KitQuestionKind>(question, "kind", KIT_QUESTION_KINDS),
    question: stringOf(question, "question"),
    topicId: question["topic_id"] === null ? null : numberOf(question, "topic_id"),
  };
}

function readStory(value: unknown): KitStory {
  const story = asRecord(value);
  return {
    title: stringOf(story, "title"),
    situation: stringOf(story, "situation"),
    task: stringOf(story, "task"),
    action: stringOf(story, "action"),
    result: stringOf(story, "result"),
    factIds: arrayOf(story, "fact_ids").map((id) => {
      if (typeof id !== "number") {
        throw contract();
      }
      return id;
    }),
  };
}

function readKit(value: unknown): InterviewKit {
  const kit = asRecord(value);
  return {
    id: numberOf(kit, "kit_id"),
    jobId: numberOf(kit, "job_id"),
    version: numberOf(kit, "version"),
    createdOn: stringOf(kit, "created_on"),
    questions: arrayOf(kit, "questions").map(readQuestion),
    stories: arrayOf(kit, "stories").map(readStory),
    companyQuestions: arrayOf(kit, "company_questions").map((question) => {
      if (typeof question !== "string") {
        throw contract();
      }
      return question;
    }),
  };
}

function contract(): PrepUnavailableError {
  return new PrepUnavailableError(CONTRACT);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function asRecord(value: unknown): Record<string, unknown> {
  if (!isRecord(value)) {
    throw contract();
  }
  return value;
}

function arrayOf(record: Record<string, unknown>, key: string): unknown[] {
  const value = record[key];
  if (!Array.isArray(value)) {
    throw contract();
  }
  return value;
}

function stringOf(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  if (typeof value !== "string") {
    throw contract();
  }
  return value;
}

function stringOrNull(record: Record<string, unknown>, key: string): string | null {
  return record[key] === null ? null : stringOf(record, key);
}

function numberOf(record: Record<string, unknown>, key: string): number {
  const value = record[key];
  if (typeof value !== "number") {
    throw contract();
  }
  return value;
}

function oneOf<T extends string>(record: Record<string, unknown>, key: string, allowed: readonly string[]): T {
  const value = record[key];
  if (typeof value !== "string" || !allowed.includes(value)) {
    throw contract();
  }
  return value as T;
}
