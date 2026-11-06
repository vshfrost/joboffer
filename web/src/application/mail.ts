import type { MailDetail, MailList, MailQuery, MailSettings, ManualSync } from "../domain/mail";
import {
  MailNotConfiguredError,
  MailNotFoundError,
  MailSyncLimitError,
  MailUnauthorizedError,
  MailUnavailableError,
} from "../domain/mailErrors";
import type { MailApi } from "../ports/mailApi";

export type MailProblem = "unauthorized" | "unavailable" | "not-configured";

export type LoadMailOutcome = { ok: true; list: MailList } | { ok: false; kind: MailProblem };
export type MailDetailOutcome = { ok: true; detail: MailDetail } | { ok: false; kind: MailProblem | "not-found" };
export type MailSettingsOutcome = { ok: true; settings: MailSettings } | { ok: false; kind: MailProblem };
/** `limit` — ліміт синку вручну вичерпано (текст для користувача). */
export type RequestSyncOutcome = { ok: true; manual: ManualSync } | { ok: false; kind: "limit"; message: string } | { ok: false; kind: MailProblem };

export interface MailServices {
  list(query: MailQuery): Promise<LoadMailOutcome>;
  get(id: number): Promise<MailDetailOutcome>;
  settings(): Promise<MailSettingsOutcome>;
  requestSync(): Promise<RequestSyncOutcome>;
  rotate(): Promise<MailSettingsOutcome>;
}

export function createMailServices(api: MailApi): MailServices {
  return {
    async list(query) {
      try {
        return { ok: true, list: await api.list(query) };
      } catch (error) {
        return problem(error);
      }
    },

    async get(id) {
      try {
        return { ok: true, detail: await api.get(id) };
      } catch (error) {
        return error instanceof MailNotFoundError ? { ok: false, kind: "not-found" } : problem(error);
      }
    },

    async settings() {
      try {
        return { ok: true, settings: await api.settings() };
      } catch (error) {
        return problem(error);
      }
    },

    async requestSync() {
      try {
        return { ok: true, manual: await api.requestSync() };
      } catch (error) {
        return error instanceof MailSyncLimitError ? { ok: false, kind: "limit", message: error.message } : problem(error);
      }
    },

    async rotate() {
      try {
        return { ok: true, settings: await api.rotate() };
      } catch (error) {
        return problem(error);
      }
    },
  };
}

function problem(error: unknown): { ok: false; kind: MailProblem } {
  if (error instanceof MailUnauthorizedError) {
    return { ok: false, kind: "unauthorized" };
  }
  if (error instanceof MailNotConfiguredError) {
    return { ok: false, kind: "not-configured" };
  }
  if (error instanceof MailUnavailableError) {
    return { ok: false, kind: "unavailable" };
  }
  throw error;
}
