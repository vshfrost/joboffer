import type { InterviewKit, JobPrep, PrepOverview, Topic } from "../domain/prep";
import { PrepNotFoundError, PrepUnauthorizedError, PrepUnavailableError, PrepValidationError } from "../domain/prepErrors";
import type { PrepApi } from "../ports/prepApi";

export type PrepProblem = "unauthorized" | "unavailable";

export type LoadOverviewOutcome = { ok: true; overview: PrepOverview } | { ok: false; kind: PrepProblem };
export type TopicOutcome = { ok: true; topic: Topic } | { ok: false; kind: PrepProblem | "not-found" };
/** `invalid` — сервер відхилив нотатку: тексти біля полів (`note`) і загальний текст. */
export type CompleteStepOutcome =
  | { ok: true; topic: Topic }
  | { ok: false; kind: "invalid"; message: string; fieldErrors: Readonly<Record<string, string>> }
  | { ok: false; kind: PrepProblem | "not-found" };
export type JobPrepOutcome = { ok: true; jobPrep: JobPrep } | { ok: false; kind: PrepProblem | "not-found" };
export type KitOutcome = { ok: true; kit: InterviewKit } | { ok: false; kind: PrepProblem | "not-found" };

export interface PrepServices {
  topics(): Promise<LoadOverviewOutcome>;
  topic(topicId: number): Promise<TopicOutcome>;
  completeStep(stepId: number, note: string): Promise<CompleteStepOutcome>;
  setReady(topicId: number, ready: boolean): Promise<TopicOutcome>;
  jobPrep(jobId: number): Promise<JobPrepOutcome>;
  interviewKit(jobId: number): Promise<KitOutcome>;
}

export function createPrepServices(api: PrepApi): PrepServices {
  return {
    async topics() {
      try {
        return { ok: true, overview: await api.topics() };
      } catch (error) {
        return problem(error);
      }
    },

    async topic(topicId) {
      try {
        return { ok: true, topic: await api.topic(topicId) };
      } catch (error) {
        return withNotFound(error);
      }
    },

    async completeStep(stepId, note) {
      try {
        return { ok: true, topic: await api.completeStep(stepId, note) };
      } catch (error) {
        return error instanceof PrepValidationError ? { ok: false, kind: "invalid", message: error.message, fieldErrors: error.fieldErrors } : withNotFound(error);
      }
    },

    async setReady(topicId, ready) {
      try {
        return { ok: true, topic: await api.setReady(topicId, ready) };
      } catch (error) {
        return withNotFound(error);
      }
    },

    async jobPrep(jobId) {
      try {
        return { ok: true, jobPrep: await api.jobPrep(jobId) };
      } catch (error) {
        return withNotFound(error);
      }
    },

    async interviewKit(jobId) {
      try {
        return { ok: true, kit: await api.interviewKit(jobId) };
      } catch (error) {
        return withNotFound(error);
      }
    },
  };
}

function withNotFound(error: unknown): { ok: false; kind: PrepProblem | "not-found" } {
  return error instanceof PrepNotFoundError ? { ok: false, kind: "not-found" } : problem(error);
}

function problem(error: unknown): { ok: false; kind: PrepProblem } {
  if (error instanceof PrepUnauthorizedError) {
    return { ok: false, kind: "unauthorized" };
  }
  if (error instanceof PrepUnavailableError) {
    return { ok: false, kind: "unavailable" };
  }
  throw error;
}
