import type { ReplyBoard, ReplyDetail, ReplyQuery, ReplyType, ReviewEffect, ReviewInput } from "../domain/replies";

/** API відповідей на подачі. Помилки — з `domain/repliesErrors`. */
export interface RepliesApi {
  /** Черга з лічильниками всіх трьох черг. Кидає RepliesUnauthorizedError або RepliesUnavailableError. */
  board(query: ReplyQuery): Promise<ReplyBoard>;
  /** Лист із текстом і подачами власника. Кидає RepliesNotFoundError, RepliesUnauthorizedError або RepliesUnavailableError. */
  get(id: number): Promise<ReplyDetail>;
  /** Що розбір зробить зі статусом подачі `jobId`. Кидає RepliesNotFoundError, RepliesUnauthorizedError або RepliesUnavailableError. */
  preview(id: number, type: ReplyType, jobId: number): Promise<ReviewEffect>;
  /** Розбір листа. Кидає RepliesValidationError (422), RepliesNotFoundError, RepliesUnauthorizedError або RepliesUnavailableError. */
  review(id: number, input: ReviewInput): Promise<void>;
}
