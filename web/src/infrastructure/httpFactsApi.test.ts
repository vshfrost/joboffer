import { describe, expect, test, vi } from "vitest";

import { FactNotFoundError, FactsConflictError, FactsUnavailableError, FactsValidationError } from "../domain/factsErrors";
import { createApiClient } from "./apiClient";
import { createHttpFactsApi } from "./httpFactsApi";

const FACT = {
  fact_id: 7,
  kind: "skill",
  text: "Python",
  confirmed: false,
  source: "chat",
  job_id: 12,
  created_at: "2026-10-20T10:00:00Z",
  updated_at: "2026-10-21T10:00:00Z",
};
const KINDS = ["experience", "achievement", "project", "skill", "education", "language"].map((kind) => ({
  kind,
  total: 0,
  confirmed: 0,
  unconfirmed: 0,
}));
const LIBRARY = { facts: [FACT], counts: { total: 1, confirmed: 0, unconfirmed: 1, kinds: KINDS } };

/** Межа — fetch: відповідь або збій мережі. */
function apiWith(respond: (input: string, init: RequestInit | undefined) => Response | Promise<Response>) {
  const fetchFn = vi.fn<typeof fetch>((input, init) => Promise.resolve(respond(String(input), init)));
  const client = createApiClient(fetchFn, "/api");
  client.setCsrfToken("csrf-1");
  return { api: createHttpFactsApi(client), fetchFn };
}

const reply = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status });
const errors = (message: string, fields: [string, string][]) => ({
  code: "invalid_value",
  message,
  field_errors: fields.map(([field, text]) => ({ field, message: text })),
});

describe("list", () => {
  test("GET /api/facts і розбір фактів у модель клієнта", async () => {
    const { api, fetchFn } = apiWith(() => reply(200, LIBRARY));
    expect(await api.list()).toEqual([
      { id: 7, kind: "skill", text: "Python", confirmed: false, source: "chat", jobId: 12, createdAt: "2026-10-20T10:00:00Z", updatedAt: "2026-10-21T10:00:00Z" },
    ]);
    expect(fetchFn.mock.calls[0]?.[0]).toBe("/api/facts");
    expect(fetchFn.mock.calls[0]?.[1]?.method).toBe("GET");
  });

  test("відповідь не за контрактом чи не 200 — FactsUnavailableError", async () => {
    await expect(apiWith(() => reply(500)).api.list()).rejects.toBeInstanceOf(FactsUnavailableError);
    await expect(apiWith(() => reply(200, { facts: "ні" })).api.list()).rejects.toBeInstanceOf(FactsUnavailableError);
    await expect(apiWith(() => reply(200, { facts: [{ ...FACT, kind: "hobby" }] })).api.list()).rejects.toBeInstanceOf(FactsUnavailableError);
    await expect(apiWith(() => reply(200, { facts: [{ ...FACT, fact_id: "7" }] })).api.list()).rejects.toBeInstanceOf(FactsUnavailableError);
  });

  test("збій мережі — FactsUnavailableError", async () => {
    const api = apiWith(() => Promise.reject(new Error("offline"))).api;
    await expect(api.list()).rejects.toBeInstanceOf(FactsUnavailableError);
  });
});

describe("originalCv", () => {
  test("GET /api/facts/original-cv у модель клієнта", async () => {
    const body = { file_name: "cv.pdf", text: "Текст CV", saved_at: "2026-10-20T08:00:00Z" };
    const { api, fetchFn } = apiWith(() => reply(200, body));
    expect(await api.originalCv()).toEqual({ fileName: "cv.pdf", text: "Текст CV", savedAt: "2026-10-20T08:00:00Z" });
    expect(fetchFn.mock.calls[0]?.[0]).toBe("/api/facts/original-cv");
  });

  test("файл без назви — fileName null", async () => {
    const { api } = apiWith(() => reply(200, { file_name: null, text: "x", saved_at: "2026-10-20T08:00:00Z" }));
    expect((await api.originalCv())?.fileName).toBeNull();
  });

  test("404 — оригіналу ще нема: null, а не помилка", async () => {
    expect(await apiWith(() => reply(404, { code: "not_found" })).api.originalCv()).toBeNull();
  });

  test("інша відповідь чи сміття — FactsUnavailableError", async () => {
    await expect(apiWith(() => reply(500)).api.originalCv()).rejects.toBeInstanceOf(FactsUnavailableError);
    await expect(apiWith(() => reply(200, { text: 1 })).api.originalCv()).rejects.toBeInstanceOf(FactsUnavailableError);
  });
});

describe("confirm", () => {
  test("POST /api/facts/confirm з fact_ids, CSRF, повертає підтверджені", async () => {
    const { api, fetchFn } = apiWith(() => reply(200, { facts: [{ ...FACT, confirmed: true }] }));
    const confirmed = await api.confirm([7, 9]);
    expect(confirmed.map((fact) => [fact.id, fact.confirmed])).toEqual([[7, true]]);
    const [path, init] = fetchFn.mock.calls[0] ?? [];
    expect([path, init?.method, init?.body]).toEqual(["/api/facts/confirm", "POST", JSON.stringify({ fact_ids: [7, 9] })]);
    expect((init?.headers as Record<string, string>)["X-CSRF-Token"]).toBe("csrf-1");
  });

  test("422 — FactsValidationError із текстом сервера; 404 — FactNotFoundError", async () => {
    const invalid = apiWith(() => reply(422, errors("Не вибрано жодного факту.", [["fact_ids", "Не вибрано жодного факту."]]))).api;
    await expect(invalid.confirm([])).rejects.toMatchObject({ message: "Не вибрано жодного факту." });
    await expect(invalid.confirm([])).rejects.toBeInstanceOf(FactsValidationError);
    await expect(apiWith(() => reply(404, { code: "not_found" })).api.confirm([99])).rejects.toBeInstanceOf(FactNotFoundError);
  });

  test("інший статус — FactsUnavailableError", async () => {
    await expect(apiWith(() => reply(500)).api.confirm([1])).rejects.toBeInstanceOf(FactsUnavailableError);
  });
});

describe("create", () => {
  test("POST /api/facts з видом і текстом, повертає створений факт із джерелом", async () => {
    const { api, fetchFn } = apiWith(() => reply(201, { ...FACT, kind: "project", text: "Нове", confirmed: true, source: "manual", job_id: null }));
    const fact = await api.create({ kind: "project", text: "Нове" });
    expect([fact.id, fact.kind, fact.text, fact.confirmed, fact.source, fact.jobId]).toEqual([7, "project", "Нове", true, "manual", null]);
    const [path, init] = fetchFn.mock.calls[0] ?? [];
    expect([path, init?.method, init?.body]).toEqual(["/api/facts", "POST", JSON.stringify({ kind: "project", text: "Нове" })]);
  });

  test("422 — FactsValidationError з текстами біля полів", async () => {
    const { api } = apiWith(() => reply(422, errors("Факт не може бути порожнім.", [["text", "Факт не може бути порожнім."]])));
    const error = await api.create({ kind: "skill", text: "" }).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(FactsValidationError);
    expect((error as FactsValidationError).fieldErrors).toEqual({ text: "Факт не може бути порожнім." });
  });

  test("409 — FactsConflictError з текстом сервера", async () => {
    const { api } = apiWith(() => reply(409, { code: "duplicate_fact", message: "Такий факт уже є: #1.", field_errors: [] }));
    const error = await api.create({ kind: "skill", text: "Python" }).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(FactsConflictError);
    expect((error as FactsConflictError).message).toBe("Такий факт уже є: #1.");
  });

  test("інший статус — FactsUnavailableError", async () => {
    await expect(apiWith(() => reply(500)).api.create({ kind: "skill", text: "x" })).rejects.toBeInstanceOf(FactsUnavailableError);
  });
});

describe("source і job_id у фактах", () => {
  test("невідоме джерело чи job_id не числом — FactsUnavailableError (збій контракту)", async () => {
    await expect(apiWith(() => reply(200, { facts: [{ ...FACT, source: "email" }] })).api.list()).rejects.toBeInstanceOf(FactsUnavailableError);
    await expect(apiWith(() => reply(200, { facts: [{ ...FACT, job_id: "12" }] })).api.list()).rejects.toBeInstanceOf(FactsUnavailableError);
    await expect(apiWith(() => reply(200, { facts: [{ ...FACT, job_id: undefined }] })).api.list()).rejects.toBeInstanceOf(FactsUnavailableError);
  });
});

describe("update", () => {
  test("PUT /api/facts/{id} з видом і текстом, повертає факт", async () => {
    const { api, fetchFn } = apiWith(() => reply(200, { ...FACT, kind: "project", text: "Нове" }));
    const fact = await api.update(7, { kind: "project", text: "Нове" });
    expect([fact.id, fact.kind, fact.text, fact.confirmed]).toEqual([7, "project", "Нове", false]);
    const [path, init] = fetchFn.mock.calls[0] ?? [];
    expect([path, init?.method, init?.body]).toEqual(["/api/facts/7", "PUT", JSON.stringify({ kind: "project", text: "Нове" })]);
  });

  test("422 — FactsValidationError з текстами біля полів", async () => {
    const { api } = apiWith(() => reply(422, errors("Факт не може бути порожнім.", [["text", "Факт не може бути порожнім."]])));
    const error = await api.update(7, { kind: "skill", text: "" }).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(FactsValidationError);
    expect((error as FactsValidationError).fieldErrors).toEqual({ text: "Факт не може бути порожнім." });
    expect((error as FactsValidationError).message).toBe("Факт не може бути порожнім.");
  });

  test("422 без розпізнаних полів — FactsUnavailableError (збій контракту)", async () => {
    const { api } = apiWith(() => reply(422, { code: "invalid_request", message: "x", field_errors: [] }));
    await expect(api.update(7, { kind: "skill", text: "x" })).rejects.toBeInstanceOf(FactsUnavailableError);
  });

  test("409 — FactsConflictError з текстом сервера; 404 — FactNotFoundError", async () => {
    const conflict = apiWith(() => reply(409, { code: "duplicate_fact", message: "Такий факт уже є: #1.", field_errors: [] })).api;
    await expect(conflict.update(2, { kind: "skill", text: "Python" })).rejects.toMatchObject({ message: "Такий факт уже є: #1." });
    await expect(conflict.update(2, { kind: "skill", text: "Python" })).rejects.toBeInstanceOf(FactsConflictError);
    await expect(apiWith(() => reply(404, {})).api.update(2, { kind: "skill", text: "x" })).rejects.toBeInstanceOf(FactNotFoundError);
  });

  test("інший статус — FactsUnavailableError", async () => {
    await expect(apiWith(() => reply(500)).api.update(1, { kind: "skill", text: "x" })).rejects.toBeInstanceOf(FactsUnavailableError);
  });
});

describe("remove", () => {
  test("DELETE /api/facts/{id}, 204", async () => {
    const { api, fetchFn } = apiWith(() => reply(204));
    await api.remove(7);
    const [path, init] = fetchFn.mock.calls[0] ?? [];
    expect([path, init?.method]).toEqual(["/api/facts/7", "DELETE"]);
    expect((init?.headers as Record<string, string>)["X-CSRF-Token"]).toBe("csrf-1");
  });

  test("404 — FactNotFoundError; інший статус — FactsUnavailableError", async () => {
    await expect(apiWith(() => reply(404, {})).api.remove(7)).rejects.toBeInstanceOf(FactNotFoundError);
    await expect(apiWith(() => reply(500)).api.remove(7)).rejects.toBeInstanceOf(FactsUnavailableError);
  });
});
