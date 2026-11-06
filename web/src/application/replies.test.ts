import { describe, expect, test } from "vitest";

import type { ReplyBoard, ReplyDetail, ReplyQuery, ReviewEffect } from "../domain/replies";
import { RepliesNotFoundError, RepliesUnauthorizedError, RepliesUnavailableError, RepliesValidationError } from "../domain/repliesErrors";
import type { RepliesApi } from "../ports/repliesApi";
import { createRepliesServices } from "./replies";

const QUERY: ReplyQuery = { queue: "matched", q: "", page: 1, perPage: 20 };
const BOARD: ReplyBoard = {
  items: [],
  page: { number: 1, size: 20, total: 0, first: 1, last: 0, hasNewer: false, hasOlder: false },
  counts: { matched: 0, unmatched: 0, reviewed: 0 },
};
const DETAIL: ReplyDetail = {
  reply: {
    id: 1,
    fromAddress: "a@b.c",
    fromName: "",
    subject: "s",
    receivedAt: "2026-10-24T13:40:00Z",
    senderAuth: "verified",
    job: null,
    confidence: null,
    matchedBy: null,
    suggestedType: "other",
    type: null,
    reviewedAt: null,
    manualForward: null,
  },
  text: "hi",
  applications: [],
};
const EFFECT: ReviewEffect = { current: "applied", after: "interview", changes: true };

function succeeding(): RepliesApi {
  return {
    board: () => Promise.resolve(BOARD),
    get: () => Promise.resolve(DETAIL),
    preview: () => Promise.resolve(EFFECT),
    review: () => Promise.resolve(),
  };
}

function failing(error: Error): RepliesApi {
  const fail = () => Promise.reject(error);
  return { board: fail, get: fail, preview: fail, review: fail };
}

describe("успіх", () => {
  test("кожна операція повертає дані порту", async () => {
    const services = createRepliesServices(succeeding());

    expect(await services.board(QUERY)).toEqual({ ok: true, board: BOARD });
    expect(await services.get(1)).toEqual({ ok: true, detail: DETAIL });
    expect(await services.preview(1, "invitation", 104)).toEqual({ ok: true, effect: EFFECT });
    expect(await services.review(1, { type: "invitation", jobId: 104 })).toEqual({ ok: true });
  });

  test("порт отримує ті самі аргументи", async () => {
    const calls: unknown[][] = [];
    const api: RepliesApi = {
      board: (query) => (calls.push(["board", query]), Promise.resolve(BOARD)),
      get: (id) => (calls.push(["get", id]), Promise.resolve(DETAIL)),
      preview: (id, type, jobId) => (calls.push(["preview", id, type, jobId]), Promise.resolve(EFFECT)),
      review: (id, input) => (calls.push(["review", id, input]), Promise.resolve()),
    };
    const services = createRepliesServices(api);

    await services.board(QUERY);
    await services.get(5);
    await services.preview(5, "rejection", 108);
    await services.review(5, { type: "other", jobId: null });

    expect(calls).toEqual([["board", QUERY], ["get", 5], ["preview", 5, "rejection", 108], ["review", 5, { type: "other", jobId: null }]]);
  });
});

describe("помилки", () => {
  test("401 і збій сервера — результат із причиною, а не виняток", async () => {
    for (const [error, kind] of [
      [new RepliesUnauthorizedError(), "unauthorized"],
      [new RepliesUnavailableError("x"), "unavailable"],
    ] as const) {
      const services = createRepliesServices(failing(error));

      expect(await services.board(QUERY)).toEqual({ ok: false, kind });
      expect(await services.get(1)).toEqual({ ok: false, kind });
      expect(await services.preview(1, "other", 1)).toEqual({ ok: false, kind });
      expect(await services.review(1, { type: "other", jobId: null })).toEqual({ ok: false, kind });
    }
  });

  test("404 — not-found для деталей, превʼю і розбору", async () => {
    const services = createRepliesServices(failing(new RepliesNotFoundError()));

    expect(await services.get(1)).toEqual({ ok: false, kind: "not-found" });
    expect(await services.preview(1, "other", 1)).toEqual({ ok: false, kind: "not-found" });
    expect(await services.review(1, { type: "other", jobId: null })).toEqual({ ok: false, kind: "not-found" });
  });

  test("422 розбору — invalid з текстами біля полів", async () => {
    const services = createRepliesServices(failing(new RepliesValidationError({ type: "Погано" })));

    expect(await services.review(1, { type: "other", jobId: null })).toEqual({ ok: false, kind: "invalid", fieldErrors: { type: "Погано" } });
  });

  test("незнана помилка не ковтається", async () => {
    const services = createRepliesServices(failing(new TypeError("bug")));

    await expect(services.board(QUERY)).rejects.toThrow("bug");
    await expect(services.get(1)).rejects.toThrow("bug");
    await expect(services.preview(1, "other", 1)).rejects.toThrow("bug");
    await expect(services.review(1, { type: "other", jobId: null })).rejects.toThrow("bug");
  });
});
