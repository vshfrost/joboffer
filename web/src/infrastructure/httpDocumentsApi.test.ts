import { describe, expect, test, vi } from "vitest";

import {
  DocumentsForbiddenError,
  DocumentsNotFoundError,
  DocumentsUnauthorizedError,
  DocumentsUnavailableError,
} from "../domain/documentsErrors";
import { createApiClient } from "./apiClient";
import { createHttpDocumentsApi } from "./httpDocumentsApi";

const LINT = {
  passed: false,
  pages: 3,
  issues: [{ code: "pages", message: "3 сторінок, а можна до 2 — скороти." }],
  keywords: { covered: ["Python"], missing: ["Kafka", "Go"], percent: 33 },
};
const ITEM = {
  document_id: 3,
  job_id: 7,
  kind: "cv",
  version: 2,
  created_at: "2026-10-22T09:40:00Z",
  file_name: "Alex_Example_CV.pdf",
  pdf_available: true,
  photo_id: null,
  lint: LINT,
};

/** Межа — fetch: відповідь або збій мережі. */
function apiWith(respond: (input: string, init: RequestInit | undefined) => Response | Promise<Response>) {
  const fetchFn = vi.fn<typeof fetch>((input, init) => Promise.resolve(respond(String(input), init)));
  return { api: createHttpDocumentsApi(createApiClient(fetchFn, "/api"), "/api"), fetchFn };
}

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const listing = (items: unknown[]) => json(200, { items });

describe("список версій", () => {
  test("GET /jobs/{id}/documents, відповідь розкладається в модель клієнта", async () => {
    const { api, fetchFn } = apiWith(() => listing([ITEM]));

    const documents = await api.list(7);

    expect(fetchFn.mock.calls[0]?.[0]).toBe("/api/jobs/7/documents");
    expect(fetchFn.mock.calls[0]?.[1]?.method).toBe("GET");
    expect(documents).toEqual([
      {
        id: 3,
        jobId: 7,
        kind: "cv",
        version: 2,
        createdAt: "2026-10-22T09:40:00Z",
        fileName: "Alex_Example_CV.pdf",
        pdfAvailable: true,
        photoId: null,
        lint: { passed: false, pages: 3, issues: [{ code: "pages", message: "3 сторінок, а можна до 2 — скороти." }], keywords: { covered: ["Python"], missing: ["Kafka", "Go"], percent: 33 } },
      },
    ]);
  });

  test("порядок сервера зберігається", async () => {
    const { api } = apiWith(() => listing([{ ...ITEM, document_id: 5, kind: "cl", version: 1 }, ITEM]));

    expect((await api.list(7)).map((item) => [item.id, item.kind])).toEqual([[5, "cl"], [3, "cv"]]);
  });

  test("порожній список", async () => {
    const { api } = apiWith(() => listing([]));

    expect(await api.list(7)).toEqual([]);
  });

  test("версія без звіту: lint = null, а не нулі", async () => {
    const { api } = apiWith(() => listing([{ ...ITEM, lint: null }]));

    expect((await api.list(7))[0]?.lint).toBeNull();
  });

  test("звіт без покриття ключових слів: keywords = null", async () => {
    const { api } = apiWith(() => listing([{ ...ITEM, lint: { ...LINT, keywords: null } }]));

    expect((await api.list(7))[0]?.lint?.keywords).toBeNull();
  });

  test("номер фото в шапці CV", async () => {
    const { api } = apiWith(() => listing([{ ...ITEM, photo_id: 4 }, { ...ITEM, document_id: 2, photo_id: null }]));

    expect((await api.list(7)).map((item) => item.photoId)).toEqual([4, null]);
  });

  test("PDF версії недоступний", async () => {
    const { api } = apiWith(() => listing([{ ...ITEM, pdf_available: false }]));

    expect((await api.list(7))[0]?.pdfAvailable).toBe(false);
  });

  test.each([
    [401, DocumentsUnauthorizedError],
    [403, DocumentsForbiddenError],
    [404, DocumentsNotFoundError],
    [500, DocumentsUnavailableError],
    [502, DocumentsUnavailableError],
  ])("відповідь %i → %o", async (status, error) => {
    const { api } = apiWith(() => json(status, { code: "x", message: "y", field_errors: [] }));

    await expect(api.list(7)).rejects.toBeInstanceOf(error);
  });

  test("мережа недоступна", async () => {
    const fetchFn = vi.fn<typeof fetch>(() => Promise.reject(new TypeError("offline")));
    const api = createHttpDocumentsApi(createApiClient(fetchFn, "/api"), "/api");

    await expect(api.list(7)).rejects.toBeInstanceOf(DocumentsUnavailableError);
  });

  test.each([
    ["немає items", {}],
    ["items не масив", { items: "x" }],
    ["елемент не обʼєкт", { items: [1] }],
    ["document_id не ціле", { items: [{ ...ITEM, document_id: "3" }] }],
    ["невідомий kind", { items: [{ ...ITEM, kind: "pdf" }] }],
    ["created_at не рядок", { items: [{ ...ITEM, created_at: 5 }] }],
    ["pdf_available не булеве", { items: [{ ...ITEM, pdf_available: "yes" }] }],
    ["photo_id не ціле", { items: [{ ...ITEM, photo_id: "4" }] }],
    ["photo_id відсутній", { items: [{ ...ITEM, photo_id: undefined }] }],
    ["lint не обʼєкт", { items: [{ ...ITEM, lint: "ok" }] }],
    ["passed не булеве", { items: [{ ...ITEM, lint: { ...LINT, passed: "yes" } }] }],
    ["issues не масив", { items: [{ ...ITEM, lint: { ...LINT, issues: "x" } }] }],
    ["issue без message", { items: [{ ...ITEM, lint: { ...LINT, issues: [{ code: "pages" }] } }] }],
    ["issue не обʼєкт", { items: [{ ...ITEM, lint: { ...LINT, issues: ["x"] } }] }],
    ["keywords не обʼєкт", { items: [{ ...ITEM, lint: { ...LINT, keywords: "x" } }] }],
    ["covered не масив рядків", { items: [{ ...ITEM, lint: { ...LINT, keywords: { covered: [1], missing: [], percent: 0 } } }] }],
    ["percent не ціле", { items: [{ ...ITEM, lint: { ...LINT, keywords: { covered: [], missing: [], percent: "5" } } }] }],
  ])("не за контрактом: %s → недоступно", async (_, body) => {
    const { api } = apiWith(() => json(200, body));

    await expect(api.list(7)).rejects.toBeInstanceOf(DocumentsUnavailableError);
  });

  test("збій не з Error — теж «недоступно»", async () => {
    const client = { request: () => Promise.reject("boom"), setCsrfToken: () => {} };
    const api = createHttpDocumentsApi(client, "/api");

    await expect(api.list(7)).rejects.toThrow("Мережа недоступна");
  });

  test("тіло не JSON", async () => {
    const { api } = apiWith(() => new Response("<html>", { status: 200 }));

    await expect(api.list(7)).rejects.toBeInstanceOf(DocumentsUnavailableError);
  });
});

describe("адреса PDF", () => {
  test("конкретна версія за номером документа, від бази API", () => {
    const { api } = apiWith(() => json(200, {}));

    expect(api.pdfUrl(3)).toBe("/api/documents/3/pdf");
    expect(api.pdfUrl(12)).toBe("/api/documents/12/pdf");
  });
});
