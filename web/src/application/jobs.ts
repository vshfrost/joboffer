import type { JobAnalysis } from "../domain/analysis";
import type { AddedJob, Job, JobList, JobsQuery, NewJobInput } from "../domain/jobs";
import { AnalysisNotFoundError, JobAppliedError, JobNotFoundError, JobsUnavailableError, JobsValidationError } from "../domain/jobsErrors";
import type { JobsApi } from "../ports/jobsApi";

export type ListOutcome = { ok: true; list: JobList } | { ok: false };

export type LoadJobOutcome = { ok: true; job: Job } | { ok: false; kind: "not-found" | "unavailable" };

/** `none` — аналізу ще нема (стан даних); `unavailable` — збій. */
export type LoadAnalysisOutcome = { ok: true; analysis: JobAnalysis } | { ok: false; kind: "none" | "unavailable" };

export type DismissOutcome =
  | { ok: true }
  /** Сервер відхилив пачку чи причину: загальний текст і тексти біля полів. */
  | { ok: false; kind: "invalid"; message: string; fieldErrors: Record<string, string> }
  /** На вакансію є подача: поданих не ховають. */
  | { ok: false; kind: "applied" }
  | { ok: false; kind: "unavailable" };

export type RestoreOutcome = { ok: true } | { ok: false; kind: "not-found" | "unavailable" };

export type AddOutcome =
  | { ok: true; added: AddedJob }
  /** Сервер відхилив значення: загальний текст і тексти біля полів. */
  | { ok: false; kind: "invalid"; message: string; fieldErrors: Record<string, string> }
  | { ok: false; kind: "unavailable" };

export interface JobsServices {
  list(query: JobsQuery): Promise<ListOutcome>;
  load(id: number): Promise<LoadJobOutcome>;
  loadAnalysis(id: number): Promise<LoadAnalysisOutcome>;
  dismiss(ids: readonly number[], reason: string): Promise<DismissOutcome>;
  restore(id: number): Promise<RestoreOutcome>;
  add(input: NewJobInput): Promise<AddOutcome>;
}

export function createJobsServices(api: JobsApi): JobsServices {
  return {
    async list(query) {
      try {
        return { ok: true, list: await api.list(query) };
      } catch (error) {
        if (error instanceof JobsUnavailableError) {
          return { ok: false };
        }
        throw error;
      }
    },

    async load(id) {
      try {
        return { ok: true, job: await api.get(id) };
      } catch (error) {
        if (error instanceof JobNotFoundError) {
          return { ok: false, kind: "not-found" };
        }
        if (error instanceof JobsUnavailableError) {
          return { ok: false, kind: "unavailable" };
        }
        throw error;
      }
    },

    async loadAnalysis(id) {
      try {
        return { ok: true, analysis: await api.getAnalysis(id) };
      } catch (error) {
        if (error instanceof AnalysisNotFoundError) {
          return { ok: false, kind: "none" };
        }
        if (error instanceof JobsUnavailableError) {
          return { ok: false, kind: "unavailable" };
        }
        throw error;
      }
    },

    async dismiss(ids, reason) {
      try {
        await api.dismiss(ids, reason);
        return { ok: true };
      } catch (error) {
        if (error instanceof JobAppliedError) {
          return { ok: false, kind: "applied" };
        }
        if (error instanceof JobsValidationError) {
          const fieldErrors = { ...error.fieldErrors };
          return { ok: false, kind: "invalid", message: Object.values(fieldErrors).join(" "), fieldErrors };
        }
        if (error instanceof JobsUnavailableError) {
          return { ok: false, kind: "unavailable" };
        }
        throw error;
      }
    },

    async restore(id) {
      try {
        await api.restore(id);
        return { ok: true };
      } catch (error) {
        if (error instanceof JobNotFoundError) {
          return { ok: false, kind: "not-found" };
        }
        if (error instanceof JobsUnavailableError) {
          return { ok: false, kind: "unavailable" };
        }
        throw error;
      }
    },

    async add(input) {
      try {
        return { ok: true, added: await api.add(input) };
      } catch (error) {
        if (error instanceof JobsValidationError) {
          const fieldErrors = { ...error.fieldErrors };
          return { ok: false, kind: "invalid", message: Object.values(fieldErrors).join(" "), fieldErrors };
        }
        if (error instanceof JobsUnavailableError) {
          return { ok: false, kind: "unavailable" };
        }
        throw error;
      }
    },
  };
}
