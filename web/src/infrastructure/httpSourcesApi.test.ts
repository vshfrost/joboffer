import { describe, expect, test, vi } from "vitest";

import {
  SourcesFilteredChangedError,
  SourcesNotFoundError,
  SourcesRefreshLimitError,
  SourcesUnauthorizedError,
  SourcesUnavailableError,
  SourcesValidationError,
} from "../domain/sourcesErrors";
import { createApiClient } from "./apiClient";
import { createHttpSourcesApi } from "./httpSourcesApi";

const RUN = { ran_at: "2026-07-01T10:05:00Z", found: 160, imported: 3, filtered: 146, duplicate: 10, completed: 1, error: null };
const COMPANY = { id: "c-1", platform: "greenhouse", slug: "northstar-eng", name: "Northstar", enabled: true, last_run: RUN };
const FEED = { id: "f-1", source: "dou", query: "category=Python&remote", enabled: false, last_run: { ...RUN, error: "timeout" } };
const REFRESH = { limit: 2, remaining: 1, next_at: "2026-07-01T10:30:00Z", last_run_at: "2026-07-01T10:05:00Z" };
const OVERVIEW = { companies: [COMPANY], feeds: [FEED], refresh: REFRESH, filtered_out_count: 4 };

/** Межа — fetch: відповідь або збій мережі. */
function apiWith(respond: (input: string, init: RequestInit | undefined) => Response | Promise<Response>) {
  const fetchFn = vi.fn<typeof fetch>((input, init) => Promise.resolve(respond(String(input), init)));
  const client = createApiClient(fetchFn, "/api");
  client.setCsrfToken("csrf-1");
  return { api: createHttpSourcesApi(client), fetchFn };
}

const json = (status: number, body: unknown, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });

describe("огляд джерел", () => {
  test("GET /sources: компанії, стрічки, ліміт і лічильник «не проходять фільтр»", async () => {
    const { api, fetchFn } = apiWith(() => json(200, OVERVIEW));

    const overview = await api.overview();

    expect(fetchFn.mock.calls[0]?.[0]).toBe("/api/sources");
    expect(fetchFn.mock.calls[0]?.[1]?.method).toBe("GET");
    expect(overview.companies).toEqual([
      {
        kind: "company",
        id: "c-1",
        platform: "greenhouse",
        name: "Northstar",
        key: "northstar-eng",
        enabled: true,
        lastRun: { ranAt: "2026-07-01T10:05:00Z", found: 160, imported: 3, filtered: 146, duplicate: 10, completed: 1, error: null },
      },
    ]);
    expect(overview.feeds).toEqual([
      {
        kind: "feed",
        id: "f-1",
        platform: "dou",
        name: "DOU · category=Python&remote",
        key: "category=Python&remote",
        enabled: false,
        lastRun: { ranAt: "2026-07-01T10:05:00Z", found: 160, imported: 3, filtered: 146, duplicate: 10, completed: 1, error: "timeout" },
      },
    ]);
    expect(overview.refresh).toEqual({ limit: 2, remaining: 1, nextAt: "2026-07-01T10:30:00Z", lastRunAt: "2026-07-01T10:05:00Z" });
    expect(overview.filteredOutCount).toBe(4);
  });

  test("last_run, next_at і last_run_at можуть бути null", async () => {
    const { api } = apiWith(() =>
      json(200, { ...OVERVIEW, companies: [{ ...COMPANY, last_run: null }], feeds: [], refresh: { limit: 2, remaining: 2, next_at: null, last_run_at: null } }),
    );

    const overview = await api.overview();

    expect(overview.companies[0]?.lastRun).toBeNull();
    expect(overview.refresh).toEqual({ limit: 2, remaining: 2, nextAt: null, lastRunAt: null });
  });

  test.each(["timeout", "not_found", "rate_limited", "unavailable", "rejected", "invalid", "unsupported"])("код помилки прогону %s приймається", async (error) => {
    const { api } = apiWith(() => json(200, { ...OVERVIEW, companies: [{ ...COMPANY, last_run: { ...RUN, error } }] }));

    expect((await api.overview()).companies[0]?.lastRun?.error).toBe(error);
  });

  test.each([
    ["тіло не обʼєкт", []],
    ["companies не масив", { ...OVERVIEW, companies: "oops" }],
    ["feeds не масив", { ...OVERVIEW, feeds: {} }],
    ["рядок компанії не обʼєкт", { ...OVERVIEW, companies: [1] }],
    ["невідома платформа", { ...OVERVIEW, companies: [{ ...COMPANY, platform: "workday" }] }],
    ["невідоме джерело стрічки", { ...OVERVIEW, feeds: [{ ...FEED, source: "linkedin" }] }],
    ["id не рядок", { ...OVERVIEW, companies: [{ ...COMPANY, id: 1 }] }],
    ["enabled не булеве", { ...OVERVIEW, companies: [{ ...COMPANY, enabled: "yes" }] }],
    ["last_run не обʼєкт", { ...OVERVIEW, companies: [{ ...COMPANY, last_run: "x" }] }],
    ["лічильник прогону не число", { ...OVERVIEW, companies: [{ ...COMPANY, last_run: { ...RUN, found: "160" } }] }],
    ["невідомий код помилки прогону", { ...OVERVIEW, companies: [{ ...COMPANY, last_run: { ...RUN, error: "boom" } }] }],
    ["код помилки не рядок", { ...OVERVIEW, companies: [{ ...COMPANY, last_run: { ...RUN, error: 5 } }] }],
    ["refresh відсутній", { ...OVERVIEW, refresh: undefined }],
    ["remaining не число", { ...OVERVIEW, refresh: { ...REFRESH, remaining: "1" } }],
    ["next_at не рядок", { ...OVERVIEW, refresh: { ...REFRESH, next_at: 5 } }],
    ["filtered_out_count не число", { ...OVERVIEW, filtered_out_count: "4" }],
  ])("відповідь не за контрактом (%s) → SourcesUnavailableError", async (_, body) => {
    const { api } = apiWith(() => json(200, body));

    await expect(api.overview()).rejects.toThrow(new SourcesUnavailableError("Відповідь сервера не за контрактом"));
  });

  test("401 → SourcesUnauthorizedError", async () => {
    const { api } = apiWith(() => json(401, { code: "not_authenticated" }));

    await expect(api.overview()).rejects.toBeInstanceOf(SourcesUnauthorizedError);
  });

  test("інший статус → SourcesUnavailableError зі статусом", async () => {
    const { api } = apiWith(() => json(500, {}));

    await expect(api.overview()).rejects.toThrow(new SourcesUnavailableError("Джерела: відповідь 500"));
  });

  test("збій мережі → SourcesUnavailableError", async () => {
    const { api } = apiWith(() => Promise.reject(new Error("offline")));

    await expect(api.overview()).rejects.toBeInstanceOf(SourcesUnavailableError);
  });
});

describe("додати джерело", () => {
  test("компанія: POST /sources/companies {platform, slug, name} → 201 з новим джерелом", async () => {
    const { api, fetchFn } = apiWith(() => json(201, { ...COMPANY, id: "c-9", last_run: null }));

    const source = await api.add({ kind: "company", platform: "ashby", slug: "acme", name: "Acme" });

    expect(fetchFn.mock.calls[0]?.[0]).toBe("/api/sources/companies");
    expect(fetchFn.mock.calls[0]?.[1]?.method).toBe("POST");
    expect(JSON.parse(String(fetchFn.mock.calls[0]?.[1]?.body))).toEqual({ platform: "ashby", slug: "acme", name: "Acme" });
    expect(source).toMatchObject({ kind: "company", id: "c-9", lastRun: null });
  });

  test("стрічка: POST /sources/feeds {source, query}", async () => {
    const { api, fetchFn } = apiWith(() => json(201, { ...FEED, last_run: null }));

    const source = await api.add({ kind: "feed", source: "dou", query: "category=Python" });

    expect(fetchFn.mock.calls[0]?.[0]).toBe("/api/sources/feeds");
    expect(JSON.parse(String(fetchFn.mock.calls[0]?.[1]?.body))).toEqual({ source: "dou", query: "category=Python" });
    expect(source).toMatchObject({ kind: "feed", platform: "dou" });
  });

  test("422 → SourcesValidationError: перший текст кожного поля й загальне повідомлення", async () => {
    const { api } = apiWith(() =>
      json(422, {
        code: "invalid_value",
        message: "Слаг компанії — літери.",
        field_errors: [
          { field: "slug", message: "Слаг компанії — літери." },
          { field: "slug", message: "Другий текст" },
          { field: "name", message: "Назва задовга." },
        ],
        correlation_id: "x",
      }),
    );

    const error: unknown = await api.add({ kind: "company", platform: "ashby", slug: "!", name: "" }).catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(SourcesValidationError);
    expect((error as SourcesValidationError).message).toBe("Слаг компанії — літери.");
    expect((error as SourcesValidationError).fieldErrors).toEqual({ slug: "Слаг компанії — літери.", name: "Назва задовга." });
  });

  test.each([
    ["field_errors відсутнє", { message: "x" }],
    ["field_errors не масив", { message: "x", field_errors: "x" }],
    ["field_errors порожнє", { message: "x", field_errors: [] }],
    ["елемент без тексту", { message: "x", field_errors: [{ field: "slug" }] }],
    ["тіло не обʼєкт", []],
  ])("422 без розпізнаних полів (%s) — збій контракту", async (_, body) => {
    const { api } = apiWith(() => json(422, body));

    await expect(api.add({ kind: "feed", source: "dou", query: "q" })).rejects.toBeInstanceOf(SourcesUnavailableError);
  });

  test("422 без загального повідомлення — повідомлення за замовчуванням", async () => {
    const { api } = apiWith(() => json(422, { field_errors: [{ field: "query", message: "Погано" }] }));

    const error: unknown = await api.add({ kind: "feed", source: "dou", query: "q" }).catch((caught: unknown) => caught);

    expect((error as SourcesValidationError).message).toBe("Джерело не пройшло перевірку");
  });

  test("401 → SourcesUnauthorizedError; 200 замість 201 → SourcesUnavailableError", async () => {
    await expect(apiWith(() => json(401, {})).api.add({ kind: "feed", source: "dou", query: "q" })).rejects.toBeInstanceOf(SourcesUnauthorizedError);
    await expect(apiWith(() => json(200, FEED)).api.add({ kind: "feed", source: "dou", query: "q" })).rejects.toBeInstanceOf(SourcesUnavailableError);
  });
});

describe("вимкнути, увімкнути, видалити", () => {
  test("PATCH /sources/companies/<id> {enabled} → оновлене джерело", async () => {
    const { api, fetchFn } = apiWith(() => json(200, { ...COMPANY, enabled: false }));

    const source = await api.setEnabled("company", "c-1", false);

    expect(fetchFn.mock.calls[0]?.[0]).toBe("/api/sources/companies/c-1");
    expect(fetchFn.mock.calls[0]?.[1]?.method).toBe("PATCH");
    expect(JSON.parse(String(fetchFn.mock.calls[0]?.[1]?.body))).toEqual({ enabled: false });
    expect(source).toMatchObject({ id: "c-1", enabled: false });
  });

  test("стрічка: шлях /sources/feeds/<id>; id кодується для адреси", async () => {
    const { api, fetchFn } = apiWith(() => json(200, FEED));

    await api.setEnabled("feed", "a/b c", true);

    expect(fetchFn.mock.calls[0]?.[0]).toBe("/api/sources/feeds/a%2Fb%20c");
  });

  test("DELETE → 204; шлях за видом джерела", async () => {
    const { api, fetchFn } = apiWith(() => new Response(null, { status: 204 }));

    await api.remove("company", "c-1");
    await api.remove("feed", "f-1");

    expect(fetchFn.mock.calls.map((call) => [call[0], call[1]?.method])).toEqual([
      ["/api/sources/companies/c-1", "DELETE"],
      ["/api/sources/feeds/f-1", "DELETE"],
    ]);
  });

  test("404 → SourcesNotFoundError (PATCH і DELETE)", async () => {
    const { api } = apiWith(() => json(404, { code: "not_found" }));

    await expect(api.setEnabled("company", "c-1", true)).rejects.toBeInstanceOf(SourcesNotFoundError);
    await expect(api.remove("company", "c-1")).rejects.toBeInstanceOf(SourcesNotFoundError);
  });

  test("401 → SourcesUnauthorizedError; 500 → SourcesUnavailableError (PATCH і DELETE)", async () => {
    const unauthorized = apiWith(() => json(401, {}));
    await expect(unauthorized.api.setEnabled("company", "c-1", true)).rejects.toBeInstanceOf(SourcesUnauthorizedError);
    await expect(unauthorized.api.remove("company", "c-1")).rejects.toBeInstanceOf(SourcesUnauthorizedError);
    const broken = apiWith(() => json(500, {}));
    await expect(broken.api.setEnabled("company", "c-1", true)).rejects.toBeInstanceOf(SourcesUnavailableError);
    await expect(broken.api.remove("company", "c-1")).rejects.toThrow(new SourcesUnavailableError("Джерела: відповідь 500"));
  });
});

describe("«Оновити зараз»", () => {
  test("POST /sources/refresh → 202 зі станом ліміту", async () => {
    const { api, fetchFn } = apiWith(() => json(202, REFRESH));

    const refresh = await api.requestRefresh();

    expect(fetchFn.mock.calls[0]?.[0]).toBe("/api/sources/refresh");
    expect(fetchFn.mock.calls[0]?.[1]?.method).toBe("POST");
    expect(refresh).toEqual({ limit: 2, remaining: 1, nextAt: "2026-07-01T10:30:00Z", lastRunAt: "2026-07-01T10:05:00Z" });
  });

  test("429 → SourcesRefreshLimitError із текстом сервера й секундами з Retry-After", async () => {
    const { api } = apiWith(() => json(429, { code: "refresh_limit", message: "Наступне о 12:25 (Мадрид)." }, { "Retry-After": "1500" }));

    const error: unknown = await api.requestRefresh().catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(SourcesRefreshLimitError);
    expect((error as SourcesRefreshLimitError).message).toBe("Наступне о 12:25 (Мадрид).");
    expect((error as SourcesRefreshLimitError).retryAfter).toBe(1500);
  });

  test.each([
    ["заголовка нема", {}],
    ["не число", { "Retry-After": "soon" }],
    ["нуль", { "Retry-After": "0" }],
    ["від'ємне", { "Retry-After": "-5" }],
    ["дробове", { "Retry-After": "1.5" }],
  ])("429 і Retry-After: %s → секунд нема", async (_, headers) => {
    const { api } = apiWith(() => json(429, { message: "Забагато" }, headers));

    const error: unknown = await api.requestRefresh().catch((caught: unknown) => caught);

    expect((error as SourcesRefreshLimitError).retryAfter).toBeNull();
  });

  test("429 без тексту — текст за замовчуванням", async () => {
    const { api } = apiWith(() => json(429, {}));

    const error: unknown = await api.requestRefresh().catch((caught: unknown) => caught);

    expect((error as SourcesRefreshLimitError).message).toBe("Оновлення вже запитано забагато разів. Спробуй пізніше.");
  });

  test("401 → SourcesUnauthorizedError; 500 → SourcesUnavailableError; 200 замість 202 → SourcesUnavailableError", async () => {
    await expect(apiWith(() => json(401, {})).api.requestRefresh()).rejects.toBeInstanceOf(SourcesUnauthorizedError);
    await expect(apiWith(() => json(500, {})).api.requestRefresh()).rejects.toBeInstanceOf(SourcesUnavailableError);
    await expect(apiWith(() => json(200, REFRESH)).api.requestRefresh()).rejects.toBeInstanceOf(SourcesUnavailableError);
  });
});

describe("вакансії, що не проходять фільтр", () => {
  const JOBS = [
    { number: 204, title: "Junior Backend Engineer", company: "Cedar", reason: "excluded" },
    { number: 7, title: null, company: null, reason: "location" },
  ];

  test("GET /sources/filtered → перелік", async () => {
    const { api, fetchFn } = apiWith(() => json(200, JOBS));

    expect(await api.filtered()).toEqual(JOBS);
    expect(fetchFn.mock.calls[0]?.[0]).toBe("/api/sources/filtered");
  });

  test.each([
    ["тіло не масив", {}],
    ["елемент не обʼєкт", [1]],
    ["номер не число", [{ ...JOBS[0], number: "204" }]],
    ["посада не рядок", [{ ...JOBS[0], title: 5 }]],
    ["невідома причина", [{ ...JOBS[0], reason: "empty" }]],
  ])("перелік не за контрактом (%s) → SourcesUnavailableError", async (_, body) => {
    const { api } = apiWith(() => json(200, body));

    await expect(api.filtered()).rejects.toBeInstanceOf(SourcesUnavailableError);
  });

  test("401 і 500", async () => {
    await expect(apiWith(() => json(401, {})).api.filtered()).rejects.toBeInstanceOf(SourcesUnauthorizedError);
    await expect(apiWith(() => json(500, {})).api.filtered()).rejects.toBeInstanceOf(SourcesUnavailableError);
  });

  test("POST /sources/filtered/dismiss {numbers} → скільки сховано", async () => {
    const { api, fetchFn } = apiWith(() => json(200, { dismissed: 2 }));

    expect(await api.dismiss([204, 218])).toBe(2);
    expect(fetchFn.mock.calls[0]?.[0]).toBe("/api/sources/filtered/dismiss");
    expect(fetchFn.mock.calls[0]?.[1]?.method).toBe("POST");
    expect(JSON.parse(String(fetchFn.mock.calls[0]?.[1]?.body))).toEqual({ numbers: [204, 218] });
  });

  test("409 → SourcesFilteredChangedError", async () => {
    const { api } = apiWith(() => json(409, { code: "filtered_changed", message: "Список змінився" }));

    await expect(api.dismiss([204])).rejects.toBeInstanceOf(SourcesFilteredChangedError);
  });

  test("401, 422 (порожній вибір) і не за контрактом", async () => {
    await expect(apiWith(() => json(401, {})).api.dismiss([1])).rejects.toBeInstanceOf(SourcesUnauthorizedError);
    await expect(apiWith(() => json(422, { message: "Нема що ховати." })).api.dismiss([])).rejects.toThrow(new SourcesUnavailableError("Джерела: відповідь 422"));
    await expect(apiWith(() => json(200, { dismissed: "2" })).api.dismiss([1])).rejects.toBeInstanceOf(SourcesUnavailableError);
  });
});
