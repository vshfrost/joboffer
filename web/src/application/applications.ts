import type { Application, ApplicationInput, ApplicationStatus } from "../domain/applications";
import { ApplicationNotFoundError, ApplicationsUnavailableError, ApplicationsValidationError } from "../domain/applicationsErrors";
import type { ApplicationsApi } from "../ports/applicationsApi";

/** `application: null` — на вакансію не подавались (стан даних, не збій). */
export type LoadApplicationOutcome = { ok: true; application: Application | null } | { ok: false };

export type ChangeApplicationOutcome =
  | { ok: true; application: Application }
  /** Сервер відхилив значення чи перехід: загальний текст і тексти біля полів. */
  | { ok: false; kind: "invalid"; message: string; fieldErrors: Record<string, string> }
  | { ok: false; kind: "not-found" | "unavailable" };

export interface ApplicationsServices {
  load(jobId: number): Promise<LoadApplicationOutcome>;
  save(jobId: number, input: ApplicationInput): Promise<ChangeApplicationOutcome>;
  move(jobId: number, status: ApplicationStatus): Promise<ChangeApplicationOutcome>;
}

export function createApplicationsServices(api: ApplicationsApi): ApplicationsServices {
  async function change(call: () => Promise<Application>): Promise<ChangeApplicationOutcome> {
    try {
      return { ok: true, application: await call() };
    } catch (error) {
      if (error instanceof ApplicationsValidationError) {
        const fieldErrors = { ...error.fieldErrors };
        return { ok: false, kind: "invalid", message: Object.values(fieldErrors).join(" "), fieldErrors };
      }
      if (error instanceof ApplicationNotFoundError) {
        return { ok: false, kind: "not-found" };
      }
      if (error instanceof ApplicationsUnavailableError) {
        return { ok: false, kind: "unavailable" };
      }
      throw error;
    }
  }

  return {
    async load(jobId) {
      try {
        return { ok: true, application: await api.get(jobId) };
      } catch (error) {
        if (error instanceof ApplicationsUnavailableError) {
          return { ok: false };
        }
        throw error;
      }
    },

    save: (jobId, input) => change(() => api.save(jobId, input)),

    move: (jobId, status) => change(() => api.setStatus(jobId, status)),
  };
}
