import { APPLICATION_STATUSES, type ApplicationStatus } from "../domain/applications";
import type { MailPage, SenderAuth } from "../domain/mail";
import {
  replyQueryParams,
  type AppliedJob,
  type Confidence,
  type ManualForward,
  type MatchedBy,
  type Reply,
  type ReplyBoard,
  type ReplyCounts,
  type ReplyDetail,
  type ReplyJob,
  type ReplyType,
  type ReviewEffect,
} from "../domain/replies";
import { RepliesNotFoundError, RepliesUnauthorizedError, RepliesUnavailableError, RepliesValidationError } from "../domain/repliesErrors";
import type { RepliesApi } from "../ports/repliesApi";
import type { ApiClient, ApiResponse } from "./apiClient";

const CONTRACT = "Відповідь сервера не за контрактом";
const SENDER_AUTHS: readonly string[] = ["verified", "failed", "unknown"];
const REPLY_TYPES: readonly string[] = ["auto_confirmation", "rejection", "invitation", "assignment", "other"];
const CONFIDENCES: readonly string[] = ["high", "medium", "low"];
const MATCHED_BY: readonly string[] = ["thread", "email", "domain", "ats", "name"];

export function createHttpRepliesApi(client: ApiClient): RepliesApi {
  return {
    async board(query) {
      const search = replyQueryParams(query).toString();
      const response = await requestOrUnavailable(() => client.request("GET", search === "" ? "/replies" : `/replies?${search}`));
      return readBoard(okBody(response));
    },

    async get(id) {
      const response = await requestOrUnavailable(() => client.request("GET", `/replies/${id}`));
      return readDetail(okBody(response, true));
    },

    async preview(id, type, jobId) {
      const search = new URLSearchParams({ type, job_id: String(jobId) }).toString();
      const response = await requestOrUnavailable(() => client.request("GET", `/replies/${id}/preview?${search}`));
      return readEffect(okBody(response, true));
    },

    async review(id, input) {
      const response = await requestOrUnavailable(() => client.request("POST", `/replies/${id}/review`, { type: input.type, job_id: input.jobId }));
      if (response.status === 422) {
        throw new RepliesValidationError(readFieldErrors(response));
      }
      okBody(response, true, "Розбір");
    },
  };
}

/** Тіло успішної (200) відповіді; решта статусів — окремі помилки. */
function okBody(response: ApiResponse, notFound = false, action = "Відповіді"): unknown {
  if (response.status === 401) {
    throw new RepliesUnauthorizedError();
  }
  if (notFound && response.status === 404) {
    throw new RepliesNotFoundError();
  }
  if (response.status !== 200) {
    throw new RepliesUnavailableError(`${action}: відповідь ${response.status}`);
  }
  return response.body;
}

async function requestOrUnavailable<T>(call: () => Promise<T>): Promise<T> {
  try {
    return await call();
  } catch {
    // API-клієнт кидає лише збій мережі.
    throw new RepliesUnavailableError("Мережа недоступна");
  }
}

/** `{field_errors: [{field, message}]}` → поле → перший текст; без розпізнаних полів — збій контракту. */
function readFieldErrors(response: ApiResponse): Record<string, string> {
  const items = asRecord(response.body)["field_errors"];
  if (!Array.isArray(items)) {
    throw contract();
  }
  const errors: Record<string, string> = {};
  for (const item of items) {
    const row = asRecord(item);
    errors[stringOf(row, "field")] ??= stringOf(row, "message");
  }
  if (Object.keys(errors).length === 0) {
    throw contract();
  }
  return errors;
}

function readBoard(body: unknown): ReplyBoard {
  const record = asRecord(body);
  const items = record["items"];
  if (!Array.isArray(items)) {
    throw contract();
  }
  return { items: items.map(readReply), page: readPage(record["page"]), counts: readCounts(record["counts"]) };
}

function readPage(value: unknown): MailPage {
  const page = asRecord(value);
  return {
    number: numberOf(page, "number"),
    size: numberOf(page, "size"),
    total: numberOf(page, "total"),
    first: numberOf(page, "first"),
    last: numberOf(page, "last"),
    hasNewer: booleanOf(page, "has_newer"),
    hasOlder: booleanOf(page, "has_older"),
  };
}

function readCounts(value: unknown): ReplyCounts {
  const counts = asRecord(value);
  return { matched: numberOf(counts, "matched"), unmatched: numberOf(counts, "unmatched"), reviewed: numberOf(counts, "reviewed") };
}

function readReply(value: unknown): Reply {
  const row = asRecord(value);
  const reply = readReplyFields(row);
  // Тип розбору і його дата приходять лише разом: половинчастий розбір не пояснити користувачу.
  if ((reply.type === null) !== (reply.reviewedAt === null)) {
    throw contract();
  }
  return reply;
}

function readReplyFields(row: Record<string, unknown>): Reply {
  return {
    id: numberOf(row, "id"),
    fromAddress: stringOf(row, "untrusted_from_address"),
    fromName: stringOf(row, "untrusted_from_name"),
    subject: stringOf(row, "untrusted_subject"),
    receivedAt: stringOf(row, "received_at"),
    senderAuth: oneOf<SenderAuth>(row, "sender_auth", SENDER_AUTHS),
    job: row["job"] === null ? null : readJob(row["job"]),
    confidence: oneOfOrNull<Confidence>(row, "confidence", CONFIDENCES),
    matchedBy: oneOfOrNull<MatchedBy>(row, "matched_by", MATCHED_BY),
    suggestedType: oneOf<ReplyType>(row, "suggested_type", REPLY_TYPES),
    type: oneOfOrNull<ReplyType>(row, "type", REPLY_TYPES),
    reviewedAt: stringOrNull(row, "reviewed_at"),
    manualForward: row["manual_forward"] === null ? null : readForward(row["manual_forward"]),
  };
}

function readJob(value: unknown): ReplyJob {
  const job = asRecord(value);
  return {
    jobId: numberOf(job, "job_id"),
    title: stringOrNull(job, "title"),
    company: stringOrNull(job, "company"),
    status: oneOfOrNull<ApplicationStatus>(job, "status", APPLICATION_STATUSES),
  };
}

function readForward(value: unknown): ManualForward {
  const forward = asRecord(value);
  return {
    fromAddress: stringOf(forward, "untrusted_from_address"),
    fromName: stringOf(forward, "untrusted_from_name"),
    subject: stringOf(forward, "untrusted_subject"),
  };
}

function readDetail(body: unknown): ReplyDetail {
  const record = asRecord(body);
  const applications = record["applications"];
  if (!Array.isArray(applications)) {
    throw contract();
  }
  return { reply: readReply(record), text: stringOf(record, "untrusted_text"), applications: applications.map(readApplication) };
}

function readApplication(value: unknown): AppliedJob {
  const application = asRecord(value);
  return {
    jobId: numberOf(application, "job_id"),
    title: stringOrNull(application, "title"),
    company: stringOrNull(application, "company"),
    status: oneOf<ApplicationStatus>(application, "status", APPLICATION_STATUSES),
  };
}

function readEffect(body: unknown): ReviewEffect {
  const record = asRecord(body);
  return {
    current: oneOfOrNull<ApplicationStatus>(record, "current_status", APPLICATION_STATUSES),
    after: oneOfOrNull<ApplicationStatus>(record, "status_after", APPLICATION_STATUSES),
    changes: booleanOf(record, "changes"),
  };
}

function contract(): RepliesUnavailableError {
  return new RepliesUnavailableError(CONTRACT);
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

function booleanOf(record: Record<string, unknown>, key: string): boolean {
  const value = record[key];
  if (typeof value !== "boolean") {
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

function oneOfOrNull<T extends string>(record: Record<string, unknown>, key: string, allowed: readonly string[]): T | null {
  return record[key] === null ? null : oneOf<T>(record, key, allowed);
}
