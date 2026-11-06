import type { Fact, FactDraft, OriginalCv } from "../domain/facts";
import { FactNotFoundError, FactsConflictError, FactsUnavailableError, FactsValidationError } from "../domain/factsErrors";
import type { FactsApi } from "../ports/factsApi";

export type LoadOutcome = { ok: true; facts: Fact[] } | { ok: false };

export type CvOutcome = { ok: true; cv: OriginalCv | null } | { ok: false };

export type ConfirmOutcome =
  | { ok: true; facts: Fact[] }
  | { ok: false; kind: "invalid"; message: string }
  | { ok: false; kind: "not-found" | "unavailable" };

export type UpdateOutcome =
  | { ok: true; fact: Fact }
  /** Сервер відхилив чернетку: загальний текст і тексти біля полів (`kind`, `text`). */
  | { ok: false; kind: "invalid"; message: string; fieldErrors: Record<string, string> }
  /** Такий текст уже є в іншому факті. */
  | { ok: false; kind: "conflict"; message: string }
  | { ok: false; kind: "not-found" | "unavailable" };

export type CreateOutcome =
  | { ok: true; fact: Fact }
  /** Сервер відхилив чернетку: загальний текст і тексти біля полів (`kind`, `text`). */
  | { ok: false; kind: "invalid"; message: string; fieldErrors: Record<string, string> }
  /** Такий текст уже є в іншому факті. */
  | { ok: false; kind: "conflict"; message: string }
  | { ok: false; kind: "unavailable" };

export type RemoveOutcome = { ok: true } | { ok: false; kind: "not-found" | "unavailable" };

export interface FactsServices {
  load(): Promise<LoadOutcome>;
  originalCv(): Promise<CvOutcome>;
  confirm(ids: readonly number[]): Promise<ConfirmOutcome>;
  create(draft: FactDraft): Promise<CreateOutcome>;
  update(id: number, draft: FactDraft): Promise<UpdateOutcome>;
  remove(id: number): Promise<RemoveOutcome>;
}

export function createFactsServices(api: FactsApi): FactsServices {
  return {
    async load() {
      try {
        return { ok: true, facts: await api.list() };
      } catch (error) {
        if (error instanceof FactsUnavailableError) {
          return { ok: false };
        }
        throw error;
      }
    },

    async originalCv() {
      try {
        return { ok: true, cv: await api.originalCv() };
      } catch (error) {
        if (error instanceof FactsUnavailableError) {
          return { ok: false };
        }
        throw error;
      }
    },

    async confirm(ids) {
      try {
        return { ok: true, facts: await api.confirm(ids) };
      } catch (error) {
        if (error instanceof FactsValidationError) {
          return { ok: false, kind: "invalid", message: error.message };
        }
        if (error instanceof FactNotFoundError) {
          return { ok: false, kind: "not-found" };
        }
        if (error instanceof FactsUnavailableError) {
          return { ok: false, kind: "unavailable" };
        }
        throw error;
      }
    },

    async create(draft) {
      try {
        return { ok: true, fact: await api.create(draft) };
      } catch (error) {
        if (error instanceof FactsValidationError) {
          return { ok: false, kind: "invalid", message: error.message, fieldErrors: { ...error.fieldErrors } };
        }
        if (error instanceof FactsConflictError) {
          return { ok: false, kind: "conflict", message: error.message };
        }
        if (error instanceof FactsUnavailableError) {
          return { ok: false, kind: "unavailable" };
        }
        throw error;
      }
    },

    async update(id, draft) {
      try {
        return { ok: true, fact: await api.update(id, draft) };
      } catch (error) {
        if (error instanceof FactsValidationError) {
          return { ok: false, kind: "invalid", message: error.message, fieldErrors: { ...error.fieldErrors } };
        }
        if (error instanceof FactsConflictError) {
          return { ok: false, kind: "conflict", message: error.message };
        }
        if (error instanceof FactNotFoundError) {
          return { ok: false, kind: "not-found" };
        }
        if (error instanceof FactsUnavailableError) {
          return { ok: false, kind: "unavailable" };
        }
        throw error;
      }
    },

    async remove(id) {
      try {
        await api.remove(id);
        return { ok: true };
      } catch (error) {
        if (error instanceof FactNotFoundError) {
          return { ok: false, kind: "not-found" };
        }
        if (error instanceof FactsUnavailableError) {
          return { ok: false, kind: "unavailable" };
        }
        throw error;
      }
    },
  };
}
