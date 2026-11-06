import type { ReplyBoard, ReplyDetail, ReplyQuery, ReplyType, ReviewEffect, ReviewInput } from "../domain/replies";
import { RepliesNotFoundError, RepliesUnauthorizedError, RepliesUnavailableError, RepliesValidationError } from "../domain/repliesErrors";
import type { RepliesApi } from "../ports/repliesApi";

export type RepliesProblem = "unauthorized" | "unavailable";

export type LoadBoardOutcome = { ok: true; board: ReplyBoard } | { ok: false; kind: RepliesProblem };
export type ReplyDetailOutcome = { ok: true; detail: ReplyDetail } | { ok: false; kind: RepliesProblem | "not-found" };
export type PreviewOutcome = { ok: true; effect: ReviewEffect } | { ok: false; kind: RepliesProblem | "not-found" };
/** `invalid` — сервер відхилив значення: тексти біля полів `type` і `job_id`. */
export type ReviewOutcome =
  | { ok: true }
  | { ok: false; kind: "invalid"; fieldErrors: Readonly<Record<string, string>> }
  | { ok: false; kind: RepliesProblem | "not-found" };

export interface RepliesServices {
  board(query: ReplyQuery): Promise<LoadBoardOutcome>;
  get(id: number): Promise<ReplyDetailOutcome>;
  preview(id: number, type: ReplyType, jobId: number): Promise<PreviewOutcome>;
  review(id: number, input: ReviewInput): Promise<ReviewOutcome>;
}

export function createRepliesServices(api: RepliesApi): RepliesServices {
  return {
    async board(query) {
      try {
        return { ok: true, board: await api.board(query) };
      } catch (error) {
        return problem(error);
      }
    },

    async get(id) {
      try {
        return { ok: true, detail: await api.get(id) };
      } catch (error) {
        return withNotFound(error);
      }
    },

    async preview(id, type, jobId) {
      try {
        return { ok: true, effect: await api.preview(id, type, jobId) };
      } catch (error) {
        return withNotFound(error);
      }
    },

    async review(id, input) {
      try {
        await api.review(id, input);
        return { ok: true };
      } catch (error) {
        return error instanceof RepliesValidationError ? { ok: false, kind: "invalid", fieldErrors: error.fieldErrors } : withNotFound(error);
      }
    },
  };
}

function withNotFound(error: unknown): { ok: false; kind: RepliesProblem | "not-found" } {
  return error instanceof RepliesNotFoundError ? { ok: false, kind: "not-found" } : problem(error);
}

function problem(error: unknown): { ok: false; kind: RepliesProblem } {
  if (error instanceof RepliesUnauthorizedError) {
    return { ok: false, kind: "unauthorized" };
  }
  if (error instanceof RepliesUnavailableError) {
    return { ok: false, kind: "unavailable" };
  }
  throw error;
}
