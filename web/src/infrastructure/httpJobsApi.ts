import {
  GAP_STATUSES,
  SENIORITIES,
  TRIAGE_SOURCES,
  VERDICTS,
  WORK_MODES,
  type Gap,
  type GapStatus,
  type JobAnalysis,
  type Seniority,
  type Triage,
  type TriageSource,
  type TriageVerdict,
  type WorkMode,
} from "../domain/analysis";
import { ADD_OUTCOMES, type AddedJob, type Job, type JobList, type JobSummary, type JobTabCounts } from "../domain/jobs";
import { APPLICATION_STATUSES, type ApplicationStatus } from "../domain/applications";
import { AnalysisNotFoundError, JobAppliedError, JobNotFoundError, JobsUnavailableError, JobsValidationError } from "../domain/jobsErrors";
import type { JobsApi } from "../ports/jobsApi";
import type { ApiClient, ApiResponse } from "./apiClient";

const CONTRACT = "Відповідь сервера не за контрактом";

export function createHttpJobsApi(client: ApiClient): JobsApi {
  return {
    async list(query) {
      const params = new URLSearchParams();
      if (query.query !== "") params.set("query", query.query);
      if (query.days !== "") params.set("days", query.days);
      if (query.source !== "") params.set("source", query.source);
      if (query.needsText) params.set("needs_text", "true");
      if (query.dismissed) params.set("dismissed", "true");
      if (query.triageVerdict !== "") params.set("triage_verdict", query.triageVerdict);
      if (query.workMode !== "") params.set("work_mode", query.workMode);
      if (query.stage !== "") params.set("stage", query.stage);
      if (query.status !== "") params.set("status", query.status);
      params.set("limit", String(query.limit));
      const response = await requestOrUnavailable(() => client.request("GET", `/jobs?${params.toString()}`));
      if (response.status !== 200) {
        throw new JobsUnavailableError(`Вакансії: відповідь ${response.status}`);
      }
      return readList(response.body);
    },

    async get(id) {
      const response = await requestOrUnavailable(() => client.request("GET", `/jobs/${id}`));
      if (response.status === 404) {
        throw new JobNotFoundError();
      }
      if (response.status !== 200) {
        throw new JobsUnavailableError(`Вакансія: відповідь ${response.status}`);
      }
      return readJob(response.body);
    },

    async getAnalysis(id) {
      const response = await requestOrUnavailable(() => client.request("GET", `/jobs/${id}/analysis`));
      if (response.status === 404) {
        throw new AnalysisNotFoundError();
      }
      if (response.status !== 200) {
        throw new JobsUnavailableError(`Аналіз: відповідь ${response.status}`);
      }
      return readAnalysis(response.body);
    },

    async dismiss(ids, reason) {
      const response = await requestOrUnavailable(() => client.request("POST", "/jobs/dismiss", { job_ids: [...ids], reason }));
      if (response.status === 422) {
        throw new JobsValidationError(readFieldErrors(response));
      }
      if (response.status === 409) {
        throw new JobAppliedError();
      }
      if (response.status !== 204) {
        throw new JobsUnavailableError(`Приховування: відповідь ${response.status}`);
      }
    },

    async restore(id) {
      const response = await requestOrUnavailable(() => client.request("POST", `/jobs/${id}/restore`));
      if (response.status === 404) {
        throw new JobNotFoundError();
      }
      if (response.status !== 204) {
        throw new JobsUnavailableError(`Повернення: відповідь ${response.status}`);
      }
    },

    async add(input) {
      const response = await requestOrUnavailable(() => client.request("POST", "/jobs", { ...input }));
      if (response.status === 422) {
        throw new JobsValidationError(readFieldErrors(response));
      }
      if (response.status !== 200 && response.status !== 201) {
        throw new JobsUnavailableError(`Додавання: відповідь ${response.status}`);
      }
      return readAdded(response.body);
    },
  };
}

async function requestOrUnavailable<T>(call: () => Promise<T>): Promise<T> {
  try {
    return await call();
  } catch (error) {
    throw new JobsUnavailableError(error instanceof Error ? error.message : "Мережа недоступна");
  }
}

/** `{field_errors: [{field, message}]}` → поле → текст; без розпізнаних полів — збій контракту. */
function readFieldErrors(response: ApiResponse): Record<string, string> {
  const items = isRecord(response.body) ? response.body["field_errors"] : undefined;
  if (!Array.isArray(items)) {
    throw new JobsUnavailableError(CONTRACT);
  }
  const errors: Record<string, string> = {};
  for (const item of items) {
    if (!isRecord(item) || typeof item["field"] !== "string" || typeof item["message"] !== "string") {
      throw new JobsUnavailableError(CONTRACT);
    }
    errors[item["field"]] ??= item["message"];
  }
  if (Object.keys(errors).length === 0) {
    throw new JobsUnavailableError(CONTRACT);
  }
  return errors;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function text(value: unknown): string {
  if (typeof value !== "string") {
    throw new JobsUnavailableError(CONTRACT);
  }
  return value;
}

function textOrNull(value: unknown): string | null {
  return value === null ? null : text(value);
}

function flag(value: unknown): boolean {
  if (typeof value !== "boolean") {
    throw new JobsUnavailableError(CONTRACT);
  }
  return value;
}

function integer(value: unknown): number {
  if (typeof value !== "number" || !Number.isInteger(value)) {
    throw new JobsUnavailableError(CONTRACT);
  }
  return value;
}

function integerOrNull(value: unknown): number | null {
  return value === null ? null : integer(value);
}

function flagOrNull(value: unknown): boolean | null {
  return value === null ? null : flag(value);
}

function texts(value: unknown): string[] {
  if (!Array.isArray(value)) {
    throw new JobsUnavailableError(CONTRACT);
  }
  return value.map(text);
}

/** Прогалини аналізу — об'єкти `{number, gap, question, status, fact_ids}`. */
function gaps(value: unknown): Gap[] {
  if (!Array.isArray(value)) {
    throw new JobsUnavailableError(CONTRACT);
  }
  return value.map((item) => {
    if (!isRecord(item)) {
      throw new JobsUnavailableError(CONTRACT);
    }
    return {
      number: integer(item["number"]),
      gap: text(item["gap"]),
      question: textOrNull(item["question"]),
      status: oneOf<GapStatus>(GAP_STATUSES, item["status"]),
      factIds: integers(item["fact_ids"]),
    };
  });
}

function integers(value: unknown): number[] {
  if (!Array.isArray(value)) {
    throw new JobsUnavailableError(CONTRACT);
  }
  return value.map(integer);
}

/** Значення з відомого переліку; усе інше — збій контракту. */
function oneOf<T extends string>(known: readonly T[], value: unknown): T {
  const found = known.find((candidate) => candidate === value);
  if (found === undefined) {
    throw new JobsUnavailableError(CONTRACT);
  }
  return found;
}

function oneOfOrNull<T extends string>(known: readonly T[], value: unknown): T | null {
  return value === null ? null : oneOf(known, value);
}

function readList(body: unknown): JobList {
  if (!isRecord(body) || !Array.isArray(body["items"]) || !Array.isArray(body["sources"])) {
    throw new JobsUnavailableError(CONTRACT);
  }
  return { items: body["items"].map(readSummary), sources: body["sources"].map(text), counts: readCounts(body["counts"]) };
}

function readCounts(value: unknown): JobTabCounts {
  if (!isRecord(value)) {
    throw new JobsUnavailableError(CONTRACT);
  }
  return { inProgress: integer(value["in_progress"]), appliedUnreviewed: integer(value["applied_unreviewed"]), needsText: flag(value["needs_text"]) };
}

function readAdded(body: unknown): AddedJob {
  const outcome = isRecord(body) ? body["outcome"] : undefined;
  if (!isRecord(body) || !ADD_OUTCOMES.some((known) => known === outcome)) {
    throw new JobsUnavailableError(CONTRACT);
  }
  return { id: integer(body["job_id"]), outcome: outcome as AddedJob["outcome"] };
}

function readSummary(item: unknown): JobSummary {
  if (!isRecord(item)) {
    throw new JobsUnavailableError(CONTRACT);
  }
  return {
    id: integer(item["job_id"]),
    source: text(item["source"]),
    url: textOrNull(item["url"]),
    title: textOrNull(item["title"]),
    company: textOrNull(item["company"]),
    createdAt: text(item["created_at"]),
    needsText: flag(item["needs_text"]),
    dismissed: flag(item["dismissed"]),
    score: integerOrNull(item["score"]),
    filtersPassed: flagOrNull(item["filters_passed"]),
    workMode: oneOfOrNull<WorkMode>(WORK_MODES, item["work_mode"]),
    triageScore: integerOrNull(item["triage_score"]),
    triageVerdict: oneOfOrNull<TriageVerdict>(VERDICTS, item["triage_verdict"]),
    triageReason: textOrNull(item["triage_reason"]),
    status: oneOfOrNull<ApplicationStatus>(APPLICATION_STATUSES, item["status"]),
    isNew: flag(item["is_new"]),
  };
}

function readJob(body: unknown): Job {
  if (!isRecord(body)) {
    throw new JobsUnavailableError(CONTRACT);
  }
  return {
    id: integer(body["job_id"]),
    source: text(body["source"]),
    url: textOrNull(body["url"]),
    title: textOrNull(body["title"]),
    company: textOrNull(body["company"]),
    location: textOrNull(body["location"]),
    text: textOrNull(body["text"]),
    createdAt: text(body["created_at"]),
    needsText: flag(body["needs_text"]),
    dismissedAt: textOrNull(body["dismissed_at"]),
    dismissReason: textOrNull(body["dismiss_reason"]),
    triage: readTriage(body["triage"]),
  };
}

function readTriage(value: unknown): Triage | null {
  if (value === null) {
    return null;
  }
  if (!isRecord(value)) {
    throw new JobsUnavailableError(CONTRACT);
  }
  return {
    score: integer(value["score"]),
    verdict: oneOf<TriageVerdict>(VERDICTS, value["verdict"]),
    reason: text(value["reason"]),
    triagedAt: text(value["triaged_at"]),
    source: oneOf<TriageSource>(TRIAGE_SOURCES, value["source"]),
  };
}

function readAnalysis(body: unknown): JobAnalysis {
  if (!isRecord(body)) {
    throw new JobsUnavailableError(CONTRACT);
  }
  return {
    id: integer(body["job_id"]),
    score: integer(body["score"]),
    summary: text(body["summary"]),
    mustHave: texts(body["must_have"]),
    niceToHave: texts(body["nice_to_have"]),
    keywords: texts(body["keywords"]),
    seniority: oneOfOrNull<Seniority>(SENIORITIES, body["seniority"]),
    workMode: oneOfOrNull<WorkMode>(WORK_MODES, body["work_mode"]),
    location: textOrNull(body["location"]),
    languages: texts(body["languages"]),
    salaryMinEur: integerOrNull(body["salary_min_eur"]),
    salaryMaxEur: integerOrNull(body["salary_max_eur"]),
    relocation: flagOrNull(body["relocation"]),
    reasons: texts(body["reasons"]),
    gaps: gaps(body["gaps"]),
    filtersPassed: flag(body["filters_passed"]),
    flags: texts(body["flags"]),
    updatedAt: text(body["updated_at"]),
    staleSince: textOrNull(body["stale_since"]),
  };
}
