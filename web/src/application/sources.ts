import { nextRequestAt, type FilteredJob, type NewSource, type RefreshState, type Source, type SourceKind, type SourcesOverview } from "../domain/sources";
import {
  SourcesFilteredChangedError,
  SourcesNotFoundError,
  SourcesRefreshLimitError,
  SourcesUnauthorizedError,
  SourcesUnavailableError,
  SourcesValidationError,
} from "../domain/sourcesErrors";
import type { SourcesApi } from "../ports/sourcesApi";

export type SourcesProblem = "unauthorized" | "unavailable";

export type LoadSourcesOutcome = { ok: true; overview: SourcesOverview } | { ok: false; kind: SourcesProblem };
/** `invalid` — сервер відхилив значення: тексти біля полів (`slug`, `query`…) і загальний текст. */
export type AddSourceOutcome =
  | { ok: true; source: Source }
  | { ok: false; kind: "invalid"; message: string; fieldErrors: Readonly<Record<string, string>> }
  | { ok: false; kind: SourcesProblem };
export type ChangeSourceOutcome = { ok: true; source: Source } | { ok: false; kind: SourcesProblem | "not-found" };
export type RemoveSourceOutcome = { ok: true } | { ok: false; kind: SourcesProblem | "not-found" };
/** `limit` — ліміт вичерпано: текст сервера й момент, коли звільниться запит (з `Retry-After`; `null`, якщо його нема). */
export type RefreshOutcome =
  | { ok: true; refresh: RefreshState }
  | { ok: false; kind: "limit"; message: string; nextAt: string | null }
  | { ok: false; kind: SourcesProblem };
export type FilteredOutcome = { ok: true; jobs: FilteredJob[] } | { ok: false; kind: SourcesProblem };
/** `changed` — список змінився: нічого не сховано. */
export type DismissOutcome = { ok: true; dismissed: number } | { ok: false; kind: "changed" } | { ok: false; kind: SourcesProblem };

export interface SourcesServices {
  overview(): Promise<LoadSourcesOutcome>;
  add(input: NewSource): Promise<AddSourceOutcome>;
  setEnabled(kind: SourceKind, id: string, enabled: boolean): Promise<ChangeSourceOutcome>;
  remove(kind: SourceKind, id: string): Promise<RemoveSourceOutcome>;
  requestRefresh(): Promise<RefreshOutcome>;
  filtered(): Promise<FilteredOutcome>;
  dismiss(numbers: readonly number[]): Promise<DismissOutcome>;
}

export function createSourcesServices(api: SourcesApi): SourcesServices {
  return {
    async overview() {
      try {
        return { ok: true, overview: await api.overview() };
      } catch (error) {
        return problem(error);
      }
    },

    async add(input) {
      try {
        return { ok: true, source: await api.add(input) };
      } catch (error) {
        return error instanceof SourcesValidationError ? { ok: false, kind: "invalid", message: error.message, fieldErrors: error.fieldErrors } : problem(error);
      }
    },

    async setEnabled(kind, id, enabled) {
      try {
        return { ok: true, source: await api.setEnabled(kind, id, enabled) };
      } catch (error) {
        return withNotFound(error);
      }
    },

    async remove(kind, id) {
      try {
        await api.remove(kind, id);
        return { ok: true };
      } catch (error) {
        return withNotFound(error);
      }
    },

    async requestRefresh() {
      try {
        return { ok: true, refresh: await api.requestRefresh() };
      } catch (error) {
        if (error instanceof SourcesRefreshLimitError) {
          const nextAt = error.retryAfter === null ? null : nextRequestAt(Date.now(), error.retryAfter);
          return { ok: false, kind: "limit", message: error.message, nextAt };
        }
        return problem(error);
      }
    },

    async filtered() {
      try {
        return { ok: true, jobs: await api.filtered() };
      } catch (error) {
        return problem(error);
      }
    },

    async dismiss(numbers) {
      try {
        return { ok: true, dismissed: await api.dismiss(numbers) };
      } catch (error) {
        return error instanceof SourcesFilteredChangedError ? { ok: false, kind: "changed" } : problem(error);
      }
    },
  };
}

function withNotFound(error: unknown): { ok: false; kind: SourcesProblem | "not-found" } {
  return error instanceof SourcesNotFoundError ? { ok: false, kind: "not-found" } : problem(error);
}

function problem(error: unknown): { ok: false; kind: SourcesProblem } {
  if (error instanceof SourcesUnauthorizedError) {
    return { ok: false, kind: "unauthorized" };
  }
  if (error instanceof SourcesUnavailableError) {
    return { ok: false, kind: "unavailable" };
  }
  throw error;
}
