import {
  COMPANY_PLATFORMS,
  FAILURE_CODES,
  feedName,
  FEED_SOURCES,
  FILTERED_REASONS,
  type CompanyPlatform,
  type FailureCode,
  type FeedSource,
  type FilteredJob,
  type FilteredReason,
  type LastRun,
  type RefreshState,
  type Source,
  type SourceKind,
  type SourcesOverview,
} from "../domain/sources";
import {
  SourcesFilteredChangedError,
  SourcesNotFoundError,
  SourcesRefreshLimitError,
  SourcesUnauthorizedError,
  SourcesUnavailableError,
  SourcesValidationError,
} from "../domain/sourcesErrors";
import type { SourcesApi } from "../ports/sourcesApi";
import type { ApiClient, ApiResponse } from "./apiClient";

const CONTRACT = "Відповідь сервера не за контрактом";
const INVALID_SOURCE = "Джерело не пройшло перевірку";
const REFRESH_LIMIT_TEXT = "Оновлення вже запитано забагато разів. Спробуй пізніше.";
const POSITIVE_INTEGER = /^[1-9]\d*$/;
const COLLECTIONS: Record<SourceKind, string> = { company: "companies", feed: "feeds" };

export function createHttpSourcesApi(client: ApiClient): SourcesApi {
  return {
    async overview() {
      const response = await requestOrUnavailable(() => client.request("GET", "/sources"));
      return readOverview(okBody(response, 200));
    },

    async add(input) {
      const path = input.kind === "company" ? "/sources/companies" : "/sources/feeds";
      const body = input.kind === "company" ? { platform: input.platform, slug: input.slug, name: input.name } : { source: input.source, query: input.query };
      const response = await requestOrUnavailable(() => client.request("POST", path, body));
      if (response.status === 422) {
        throw readValidation(response);
      }
      return readSource(input.kind, okBody(response, 201));
    },

    async setEnabled(kind, id, enabled) {
      const response = await requestOrUnavailable(() => client.request("PATCH", sourcePath(kind, id), { enabled }));
      return readSource(kind, okBody(response, 200, true));
    },

    async remove(kind, id) {
      const response = await requestOrUnavailable(() => client.request("DELETE", sourcePath(kind, id)));
      okBody(response, 204, true);
    },

    async requestRefresh() {
      const response = await requestOrUnavailable(() => client.request("POST", "/sources/refresh"));
      if (response.status === 429) {
        throw new SourcesRefreshLimitError(messageOf(response.body) ?? REFRESH_LIMIT_TEXT, retryAfterOf(response));
      }
      return readRefresh(okBody(response, 202));
    },

    async filtered() {
      const response = await requestOrUnavailable(() => client.request("GET", "/sources/filtered"));
      const body = okBody(response, 200);
      if (!Array.isArray(body)) {
        throw contract();
      }
      return body.map(readFiltered);
    },

    async dismiss(numbers) {
      const response = await requestOrUnavailable(() => client.request("POST", "/sources/filtered/dismiss", { numbers }));
      if (response.status === 409) {
        throw new SourcesFilteredChangedError();
      }
      return numberOf(asRecord(okBody(response, 200)), "dismissed");
    },
  };
}

function sourcePath(kind: SourceKind, id: string): string {
  return `/sources/${COLLECTIONS[kind]}/${encodeURIComponent(id)}`;
}

/** Тіло відповіді з очікуваним статусом; решта статусів — окремі помилки. */
function okBody(response: ApiResponse, expected: number, notFound = false): unknown {
  if (response.status === 401) {
    throw new SourcesUnauthorizedError();
  }
  if (notFound && response.status === 404) {
    throw new SourcesNotFoundError();
  }
  if (response.status !== expected) {
    throw new SourcesUnavailableError(`Джерела: відповідь ${response.status}`);
  }
  return response.body;
}

async function requestOrUnavailable<T>(call: () => Promise<T>): Promise<T> {
  try {
    return await call();
  } catch {
    // API-клієнт кидає лише збій мережі.
    throw new SourcesUnavailableError("Мережа недоступна");
  }
}

function messageOf(body: unknown): string | null {
  return isRecord(body) && typeof body["message"] === "string" && body["message"] !== "" ? body["message"] : null;
}

/** `Retry-After` у секундах (ціле додатне); усе інше — `null`. */
function retryAfterOf(response: ApiResponse): number | null {
  const value = response.headers.get("Retry-After") ?? "";
  return POSITIVE_INTEGER.test(value) ? Number(value) : null;
}

/** `{message, field_errors: [{field, message}]}` → помилка перевірки; без розпізнаних полів — збій контракту. */
function readValidation(response: ApiResponse): SourcesValidationError | SourcesUnavailableError {
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
  return Object.keys(fieldErrors).length === 0 ? contract() : new SourcesValidationError(messageOf(response.body) ?? INVALID_SOURCE, fieldErrors);
}

function readOverview(body: unknown): SourcesOverview {
  const record = asRecord(body);
  const companies = record["companies"];
  const feeds = record["feeds"];
  if (!Array.isArray(companies) || !Array.isArray(feeds)) {
    throw contract();
  }
  return {
    companies: companies.map((row) => readSource("company", row)),
    feeds: feeds.map((row) => readSource("feed", row)),
    refresh: readRefresh(record["refresh"]),
    filteredOutCount: numberOf(record, "filtered_out_count"),
  };
}

function readSource(kind: SourceKind, value: unknown): Source {
  const row = asRecord(value);
  const common = { kind, id: stringOf(row, "id"), enabled: booleanOf(row, "enabled"), lastRun: row["last_run"] === null ? null : readRun(row["last_run"]) };
  if (kind === "company") {
    const platform = oneOf<CompanyPlatform>(row, "platform", COMPANY_PLATFORMS);
    return { ...common, platform, name: stringOf(row, "name"), key: stringOf(row, "slug") };
  }
  const platform = oneOf<FeedSource>(row, "source", FEED_SOURCES);
  const query = stringOf(row, "query");
  return { ...common, platform, name: feedName(platform, query), key: query };
}

function readRun(value: unknown): LastRun {
  const run = asRecord(value);
  return {
    ranAt: stringOf(run, "ran_at"),
    found: numberOf(run, "found"),
    imported: numberOf(run, "imported"),
    filtered: numberOf(run, "filtered"),
    duplicate: numberOf(run, "duplicate"),
    completed: numberOf(run, "completed"),
    error: run["error"] === null ? null : oneOf<FailureCode>(run, "error", FAILURE_CODES),
  };
}

function readRefresh(value: unknown): RefreshState {
  const refresh = asRecord(value);
  return {
    limit: numberOf(refresh, "limit"),
    remaining: numberOf(refresh, "remaining"),
    nextAt: stringOrNull(refresh, "next_at"),
    lastRunAt: stringOrNull(refresh, "last_run_at"),
  };
}

function readFiltered(value: unknown): FilteredJob {
  const job = asRecord(value);
  return {
    number: numberOf(job, "number"),
    title: stringOrNull(job, "title"),
    company: stringOrNull(job, "company"),
    reason: oneOf<FilteredReason>(job, "reason", FILTERED_REASONS),
  };
}

function contract(): SourcesUnavailableError {
  return new SourcesUnavailableError(CONTRACT);
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
