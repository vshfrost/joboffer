import { describe, expect, test, vi } from "vitest";

import { RepliesNotFoundError, RepliesUnauthorizedError, RepliesUnavailableError, RepliesValidationError } from "../domain/repliesErrors";
import { createApiClient } from "./apiClient";
import { createHttpRepliesApi } from "./httpRepliesApi";

const JOB = { job_id: 104, title: "Senior Backend Engineer", company: "Northstar", status: "applied" };
const REPLY = {
  id: 7,
  untrusted_from_address: "elena@northstar.example",
  untrusted_from_name: "Elena",
  untrusted_subject: "Let's talk",
  received_at: "2026-10-24T13:40:00Z",
  sender_auth: "verified",
  job: JOB,
  confidence: "high",
  matched_by: "email",
  suggested_type: "invitation",
  type: null,
  reviewed_at: null,
  manual_forward: null,
};
const PAGE = { number: 2, size: 50, total: 120, first: 51, last: 100, has_newer: true, has_older: true };
const COUNTS = { matched: 5, unmatched: 2, reviewed: 9 };
const BOARD = { queue: "matched", items: [REPLY], page: PAGE, counts: COUNTS };

/** Межа — fetch: відповідь або збій мережі. */
function apiWith(respond: (input: string, init: RequestInit | undefined) => Response | Promise<Response>) {
  const fetchFn = vi.fn<typeof fetch>((input, init) => Promise.resolve(respond(String(input), init)));
  const client = createApiClient(fetchFn, "/api");
  client.setCsrfToken("csrf-1");
  return { api: createHttpRepliesApi(client), fetchFn };
}

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

describe("черга", () => {
  test("GET /replies з параметрами лише там, де вони не за замовчуванням", async () => {
    const { api, fetchFn } = apiWith(() => json(200, BOARD));

    await api.board({ queue: "reviewed", q: "acme corp", page: 2, perPage: 50 });
    await api.board({ queue: "matched", q: "", page: 1, perPage: 20 });

    expect(fetchFn.mock.calls[0]?.[0]).toBe("/api/replies?queue=reviewed&q=acme+corp&page=2&per_page=50");
    expect(fetchFn.mock.calls[1]?.[0]).toBe("/api/replies");
    expect(fetchFn.mock.calls[0]?.[1]?.method).toBe("GET");
  });

  test("рядки, сторінка й лічильники — у моделі клієнта; недовірені поля віддаються як є", async () => {
    const forwarded = { untrusted_from_address: "careers@orbit.example", untrusted_from_name: "Recruiting team", untrusted_subject: "Update" };
    const reviewed = { ...REPLY, id: 8, type: "rejection", reviewed_at: "2026-10-25T09:00:00Z", manual_forward: forwarded, job: { ...JOB, title: null, company: null, status: null }, confidence: null, matched_by: null };
    const { api } = apiWith(() => json(200, { ...BOARD, items: [REPLY, reviewed] }));

    const board = await api.board({ queue: "matched", q: "", page: 2, perPage: 50 });

    expect(board.page).toEqual({ number: 2, size: 50, total: 120, first: 51, last: 100, hasNewer: true, hasOlder: true });
    expect(board.counts).toEqual({ matched: 5, unmatched: 2, reviewed: 9 });
    expect(board.items[0]).toEqual({
      id: 7,
      fromAddress: "elena@northstar.example",
      fromName: "Elena",
      subject: "Let's talk",
      receivedAt: "2026-10-24T13:40:00Z",
      senderAuth: "verified",
      job: { jobId: 104, title: "Senior Backend Engineer", company: "Northstar", status: "applied" },
      confidence: "high",
      matchedBy: "email",
      suggestedType: "invitation",
      type: null,
      reviewedAt: null,
      manualForward: null,
    });
    expect(board.items[1]).toMatchObject({
      id: 8,
      type: "rejection",
      reviewedAt: "2026-10-25T09:00:00Z",
      job: { jobId: 104, title: null, company: null, status: null },
      confidence: null,
      matchedBy: null,
      manualForward: { fromAddress: "careers@orbit.example", fromName: "Recruiting team", subject: "Update" },
    });
  });

  test("порожня відповідь — порожній список", async () => {
    const { api } = apiWith(() => json(200, { ...BOARD, items: [] }));

    expect((await api.board({ queue: "matched", q: "", page: 1, perPage: 20 })).items).toEqual([]);
  });

  test("401 — RepliesUnauthorizedError", async () => {
    const { api } = apiWith(() => json(401, {}));

    await expect(api.board({ queue: "matched", q: "", page: 1, perPage: 20 })).rejects.toBeInstanceOf(RepliesUnauthorizedError);
  });

  test.each([500, 404, 422])("відповідь %i — RepliesUnavailableError з номером статусу", async (status) => {
    const { api } = apiWith(() => json(status, {}));

    await expect(api.board({ queue: "matched", q: "", page: 1, perPage: 20 })).rejects.toThrow(new RepliesUnavailableError(`Відповіді: відповідь ${status}`));
  });

  test("збій мережі — RepliesUnavailableError з причиною", async () => {
    const { api } = apiWith(() => Promise.reject(new Error("offline")));

    await expect(api.board({ queue: "matched", q: "", page: 1, perPage: 20 })).rejects.toBeInstanceOf(RepliesUnavailableError);
  });

  const BROKEN: [string, unknown][] = [
    ["тіло — не обʼєкт", "oops"],
    ["items — не масив", { ...BOARD, items: {} }],
    ["рядок — не обʼєкт", { ...BOARD, items: [1] }],
    ["id — не число", { ...BOARD, items: [{ ...REPLY, id: "7" }] }],
    ["тема — не рядок", { ...BOARD, items: [{ ...REPLY, untrusted_subject: null }] }],
    ["невідомий вердикт відправника", { ...BOARD, items: [{ ...REPLY, sender_auth: "trusted" }] }],
    ["невідомий тип", { ...BOARD, items: [{ ...REPLY, type: "nope" }] }],
    ["невідома підказка типу", { ...BOARD, items: [{ ...REPLY, suggested_type: "nope" }] }],
    ["невідома надійність", { ...BOARD, items: [{ ...REPLY, confidence: "certain" }] }],
    ["невідома ознака збігу", { ...BOARD, items: [{ ...REPLY, matched_by: 5 }] }],
    ["вакансія — не обʼєкт", { ...BOARD, items: [{ ...REPLY, job: "x" }] }],
    ["номер вакансії — не число", { ...BOARD, items: [{ ...REPLY, job: { ...JOB, job_id: "104" } }] }],
    ["невідомий статус подачі", { ...BOARD, items: [{ ...REPLY, job: { ...JOB, status: "hired" } }] }],
    ["посада — не рядок", { ...BOARD, items: [{ ...REPLY, job: { ...JOB, title: 5 } }] }],
    ["розбір без дати", { ...BOARD, items: [{ ...REPLY, reviewed_at: 5 }] }],
    ["тип розбору без дати розбору", { ...BOARD, items: [{ ...REPLY, type: "rejection", reviewed_at: null }] }],
    ["дата розбору без типу", { ...BOARD, items: [{ ...REPLY, type: null, reviewed_at: "2026-10-25T09:00:00Z" }] }],
    ["пересилання — не обʼєкт", { ...BOARD, items: [{ ...REPLY, manual_forward: 5 }] }],
    ["пересилання без теми", { ...BOARD, items: [{ ...REPLY, manual_forward: { untrusted_from_address: "a", untrusted_from_name: "b" } }] }],
    ["сторінка — не обʼєкт", { ...BOARD, page: null }],
    ["has_newer — не булеве", { ...BOARD, page: { ...PAGE, has_newer: "yes" } }],
    ["лічильники — не обʼєкт", { ...BOARD, counts: [] }],
    ["лічильник — не число", { ...BOARD, counts: { ...COUNTS, reviewed: "9" } }],
  ];

  test.each(BROKEN)("відповідь не за контрактом (%s) — RepliesUnavailableError", async (_name, body) => {
    const { api } = apiWith(() => json(200, body));

    await expect(api.board({ queue: "matched", q: "", page: 1, perPage: 20 })).rejects.toThrow(new RepliesUnavailableError("Відповідь сервера не за контрактом"));
  });
});

const APPLICATION = { job_id: 104, title: "Senior Backend Engineer", company: "Northstar", status: "applied" };
const DETAIL = { ...REPLY, untrusted_text: "Hi Taras,\n\nCould we talk?", applications: [APPLICATION, { ...APPLICATION, job_id: 108, title: null, company: null, status: "replied" }] };

describe("деталі", () => {
  test("GET /replies/{id}: відповідь, недовірений текст і подачі власника — у моделі клієнта", async () => {
    const { api, fetchFn } = apiWith(() => json(200, DETAIL));

    const detail = await api.get(7);

    expect(fetchFn.mock.calls[0]?.[0]).toBe("/api/replies/7");
    expect(fetchFn.mock.calls[0]?.[1]?.method).toBe("GET");
    expect(detail.reply).toMatchObject({ id: 7, subject: "Let's talk", suggestedType: "invitation", job: { jobId: 104 } });
    expect(detail.text).toBe("Hi Taras,\n\nCould we talk?");
    expect(detail.applications).toEqual([
      { jobId: 104, title: "Senior Backend Engineer", company: "Northstar", status: "applied" },
      { jobId: 108, title: null, company: null, status: "replied" },
    ]);
  });

  test("404 — RepliesNotFoundError, 401 — RepliesUnauthorizedError", async () => {
    await expect(apiWith(() => json(404, {})).api.get(7)).rejects.toBeInstanceOf(RepliesNotFoundError);
    await expect(apiWith(() => json(401, {})).api.get(7)).rejects.toBeInstanceOf(RepliesUnauthorizedError);
  });

  test("інший статус і збій мережі — RepliesUnavailableError", async () => {
    await expect(apiWith(() => json(500, {})).api.get(7)).rejects.toThrow(new RepliesUnavailableError("Відповіді: відповідь 500"));
    await expect(apiWith(() => Promise.reject(new Error("offline"))).api.get(7)).rejects.toBeInstanceOf(RepliesUnavailableError);
  });

  const BROKEN: [string, unknown][] = [
    ["текст — не рядок", { ...DETAIL, untrusted_text: null }],
    ["подачі — не масив", { ...DETAIL, applications: null }],
    ["подача — не обʼєкт", { ...DETAIL, applications: [1] }],
    ["номер подачі — не число", { ...DETAIL, applications: [{ ...APPLICATION, job_id: "104" }] }],
    ["статус подачі невідомий", { ...DETAIL, applications: [{ ...APPLICATION, status: "hired" }] }],
    ["статус подачі порожній", { ...DETAIL, applications: [{ ...APPLICATION, status: null }] }],
  ];

  test.each(BROKEN)("деталі не за контрактом (%s) — RepliesUnavailableError", async (_name, body) => {
    await expect(apiWith(() => json(200, body)).api.get(7)).rejects.toThrow(new RepliesUnavailableError("Відповідь сервера не за контрактом"));
  });
});

describe("превʼю", () => {
  test("GET /replies/{id}/preview?type=&job_id= → статус зараз і після", async () => {
    const { api, fetchFn } = apiWith(() => json(200, { job_id: 104, current_status: "applied", status_after: "interview", changes: true }));

    const effect = await api.preview(7, "invitation", 104);

    expect(fetchFn.mock.calls[0]?.[0]).toBe("/api/replies/7/preview?type=invitation&job_id=104");
    expect(fetchFn.mock.calls[0]?.[1]?.method).toBe("GET");
    expect(effect).toEqual({ current: "applied", after: "interview", changes: true });
  });

  test("без статусів (подачі нема) — null", async () => {
    const { api } = apiWith(() => json(200, { job_id: null, current_status: null, status_after: null, changes: false }));

    expect(await api.preview(7, "other", 104)).toEqual({ current: null, after: null, changes: false });
  });

  test("404 — RepliesNotFoundError, 401 — RepliesUnauthorizedError, 500 — RepliesUnavailableError", async () => {
    await expect(apiWith(() => json(404, {})).api.preview(7, "other", 104)).rejects.toBeInstanceOf(RepliesNotFoundError);
    await expect(apiWith(() => json(401, {})).api.preview(7, "other", 104)).rejects.toBeInstanceOf(RepliesUnauthorizedError);
    await expect(apiWith(() => json(500, {})).api.preview(7, "other", 104)).rejects.toBeInstanceOf(RepliesUnavailableError);
  });

  test.each<[string, unknown]>([
    ["статус невідомий", { current_status: "hired", status_after: "applied", changes: false }],
    ["changes — не булеве", { current_status: "applied", status_after: "applied", changes: "no" }],
    ["тіло — не обʼєкт", []],
  ])("превʼю не за контрактом (%s) — RepliesUnavailableError", async (_name, body) => {
    await expect(apiWith(() => json(200, body)).api.preview(7, "other", 104)).rejects.toThrow(new RepliesUnavailableError("Відповідь сервера не за контрактом"));
  });
});

describe("розбір", () => {
  test("POST /replies/{id}/review з типом і вакансією; токен CSRF іде в заголовку", async () => {
    const { api, fetchFn } = apiWith(() => json(200, { reply: REPLY, application: null }));

    await api.review(7, { type: "rejection", jobId: 104 });
    await api.review(7, { type: "other", jobId: null });

    expect(fetchFn.mock.calls[0]?.[0]).toBe("/api/replies/7/review");
    expect(fetchFn.mock.calls[0]?.[1]?.method).toBe("POST");
    expect(JSON.parse(String(fetchFn.mock.calls[0]?.[1]?.body))).toEqual({ type: "rejection", job_id: 104 });
    expect(JSON.parse(String(fetchFn.mock.calls[1]?.[1]?.body))).toEqual({ type: "other", job_id: null });
    expect(new Headers(fetchFn.mock.calls[0]?.[1]?.headers).get("X-CSRF-Token")).toBe("csrf-1");
  });

  test("422 — RepliesValidationError з текстами біля полів (перший текст поля)", async () => {
    const body = { code: "invalid_value", message: "m", field_errors: [{ field: "type", message: "Погано" }, { field: "type", message: "Другий" }, { field: "job_id", message: "Нема" }] };
    const { api } = apiWith(() => json(422, body));

    const error = await api.review(7, { type: "other", jobId: null }).catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(RepliesValidationError);
    expect((error as RepliesValidationError).fieldErrors).toEqual({ type: "Погано", job_id: "Нема" });
  });

  test.each<[string, unknown]>([
    ["без field_errors", {}],
    ["порожній список", { field_errors: [] }],
    ["елемент — не обʼєкт", { field_errors: [1] }],
    ["поле без тексту", { field_errors: [{ field: "type" }] }],
  ])("422 не за контрактом (%s) — RepliesUnavailableError", async (_name, body) => {
    await expect(apiWith(() => json(422, body)).api.review(7, { type: "other", jobId: null })).rejects.toThrow(new RepliesUnavailableError("Відповідь сервера не за контрактом"));
  });

  test("404, 401 і 500 — окремі помилки", async () => {
    const input = { type: "other", jobId: null } as const;
    await expect(apiWith(() => json(404, {})).api.review(7, input)).rejects.toBeInstanceOf(RepliesNotFoundError);
    await expect(apiWith(() => json(401, {})).api.review(7, input)).rejects.toBeInstanceOf(RepliesUnauthorizedError);
    await expect(apiWith(() => json(500, {})).api.review(7, input)).rejects.toThrow(new RepliesUnavailableError("Розбір: відповідь 500"));
    await expect(apiWith(() => Promise.reject(new Error("offline"))).api.review(7, input)).rejects.toBeInstanceOf(RepliesUnavailableError);
  });
});
