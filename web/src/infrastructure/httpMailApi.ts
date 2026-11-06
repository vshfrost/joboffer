import {
  mailQueryParams,
  type DropReason,
  type Forwarding,
  type MailCategory,
  type MailDetail,
  type MailItem,
  type MailList,
  type MailPage,
  type MailSettings,
  type ManualSync,
  type SenderAuth,
} from "../domain/mail";
import {
  MailNotConfiguredError,
  MailNotFoundError,
  MailSyncLimitError,
  MailUnauthorizedError,
  MailUnavailableError,
} from "../domain/mailErrors";
import type { MailApi } from "../ports/mailApi";
import type { ApiClient, ApiResponse } from "./apiClient";

const CONTRACT = "Відповідь сервера не за контрактом";
const CATEGORIES: readonly string[] = ["company", "linkedin_alert", "linkedin_application", "linkedin_message", "forwarding_confirmation", "suspicious", "other"];
const SENDER_AUTHS: readonly string[] = ["verified", "failed", "unknown"];
const DROP_REASONS: readonly string[] = ["daily_limit", "retired_tag"];
const SYNC_LIMIT_TEXT = "Синк уже запитано забагато разів. Спробуй пізніше.";

export function createHttpMailApi(client: ApiClient): MailApi {
  return {
    async list(query) {
      const search = mailQueryParams(query).toString();
      const response = await requestOrUnavailable(() => client.request("GET", search === "" ? "/mail" : `/mail?${search}`));
      return readList(okBody(response));
    },

    async get(id) {
      const response = await requestOrUnavailable(() => client.request("GET", `/mail/${id}`));
      if (response.status === 404) {
        throw new MailNotFoundError();
      }
      return readDetail(okBody(response));
    },

    async settings() {
      const response = await requestOrUnavailable(() => client.request("GET", "/mail/settings"));
      return readSettings(okBody(response));
    },

    async requestSync() {
      const response = await requestOrUnavailable(() => client.request("POST", "/mail/sync"));
      if (response.status === 429) {
        throw new MailSyncLimitError(messageOf(response.body) ?? SYNC_LIMIT_TEXT);
      }
      return readManual(okBody(response));
    },

    async rotate() {
      const response = await requestOrUnavailable(() => client.request("POST", "/mail/address/rotate"));
      return readSettings(okBody(response));
    },
  };
}

/** Тіло успішної (200) відповіді; решта статусів — окремі помилки. */
function okBody(response: ApiResponse): unknown {
  if (response.status === 401) {
    throw new MailUnauthorizedError();
  }
  if (response.status === 503) {
    throw new MailNotConfiguredError();
  }
  if (response.status !== 200) {
    throw new MailUnavailableError(`Пошта: відповідь ${response.status}`);
  }
  return response.body;
}

async function requestOrUnavailable<T>(call: () => Promise<T>): Promise<T> {
  try {
    return await call();
  } catch (error) {
    throw new MailUnavailableError(error instanceof Error ? error.message : "Мережа недоступна");
  }
}

function messageOf(body: unknown): string | null {
  return isRecord(body) && typeof body["message"] === "string" && body["message"] !== "" ? body["message"] : null;
}

function readList(body: unknown): MailList {
  const record = asRecord(body);
  const items = record["items"];
  if (!Array.isArray(items)) {
    throw contract();
  }
  return { items: items.map(readItem), page: readPage(record["page"]) };
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

function readItem(value: unknown): MailItem {
  const row = asRecord(value);
  const item: MailItem = {
    id: numberOf(row, "id"),
    dropped: booleanOf(row, "dropped"),
    fromAddress: stringOf(row, "untrusted_from_address"),
    fromName: stringOf(row, "untrusted_from_name"),
    subject: stringOf(row, "untrusted_subject"),
    receivedAt: stringOf(row, "received_at"),
    category: oneOfOrNull<MailCategory>(row, "category", CATEGORIES),
    senderAuth: oneOfOrNull<SenderAuth>(row, "sender_auth", SENDER_AUTHS),
    reason: oneOfOrNull<DropReason>(row, "reason", DROP_REASONS),
  };
  // Відкинутий лист без причини не пояснити користувачу: такий рядок — збій контракту.
  if (item.dropped && item.reason === null) {
    throw contract();
  }
  return item;
}

function readDetail(body: unknown): MailDetail {
  const record = asRecord(body);
  return {
    item: readItem(record),
    text: stringOf(record, "untrusted_text"),
    forwarding: record["forwarding"] === null ? null : readForwarding(record["forwarding"]),
  };
}

function readForwarding(value: unknown): Forwarding {
  const forwarding = asRecord(value);
  return {
    code: stringOf(forwarding, "code"),
    linkOnly: booleanOf(forwarding, "link_only"),
    requestedBy: stringOf(forwarding, "untrusted_requested_by"),
    receivedAt: stringOf(forwarding, "received_at"),
    current: booleanOf(forwarding, "current"),
  };
}

function readSettings(body: unknown): MailSettings {
  const record = asRecord(body);
  return {
    address: stringOf(record, "address"),
    rotatedAt: stringOrNull(record, "rotated_at"),
    syncedAt: stringOrNull(record, "synced_at"),
    syncFailed: booleanOf(record, "sync_failed"),
    syncError: stringOf(record, "sync_error"),
    manual: readManual(record["manual"]),
  };
}

function readManual(value: unknown): ManualSync {
  const manual = asRecord(value);
  return { limit: numberOf(manual, "limit"), remaining: numberOf(manual, "remaining"), nextAt: stringOrNull(manual, "next_at") };
}

function contract(): MailUnavailableError {
  return new MailUnavailableError(CONTRACT);
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

function oneOfOrNull<T extends string>(record: Record<string, unknown>, key: string, allowed: readonly string[]): T | null {
  const value = record[key];
  if (value === null) {
    return null;
  }
  if (typeof value !== "string" || !allowed.includes(value)) {
    throw contract();
  }
  return value as T;
}
