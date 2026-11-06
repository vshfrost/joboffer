import { describe, expect, test, vi } from "vitest";

import type { JobsQuery } from "../domain/jobs";
import { AnalysisNotFoundError, JobAppliedError, JobNotFoundError, JobsUnavailableError, JobsValidationError } from "../domain/jobsErrors";
import { createApiClient } from "./apiClient";
import { createHttpJobsApi } from "./httpJobsApi";

const QUERY: JobsQuery = { query: "", days: "", source: "", needsText: false, dismissed: false, triageVerdict: "", workMode: "", status: "", stage: "", limit: 200 };
const COUNTS = { in_progress: 0, applied_unreviewed: 0, needs_text: false };

const ITEM = {
  job_id: 7,
  source: "manual",
  url: "https://acme.com/j/7",
  title: "Backend",
  company: "Acme",
  created_at: "2026-10-20T10:00:00Z",
  needs_text: false,
  dismissed: false,
  score: null,
  filters_passed: null,
  work_mode: null,
  triage_score: null,
  triage_verdict: null,
  triage_reason: null,
  status: null,
  is_new: false,
};
const JOB = {
  job_id: 7,
  source: "manual",
  url: "https://acme.com/j/7",
  title: "Backend",
  company: "Acme",
  location: "Valencia",
  text: "Опис <b>жирний</b>",
  created_at: "2026-10-20T10:00:00Z",
  needs_text: false,
  dismissed_at: null,
  dismiss_reason: null,
  triage: null,
};
const ANALYSIS = {
  job_id: 7,
  score: 78,
  summary: "Бекенд-роль.",
  must_have: ["Python"],
  nice_to_have: ["Go"],
  keywords: ["asyncio"],
  seniority: "senior",
  work_mode: "remote",
  location: "Madrid",
  languages: ["English"],
  salary_min_eur: 60000,
  salary_max_eur: 80000,
  relocation: false,
  reasons: ["Збігається стек"],
  gaps: [{ number: 1, gap: "Kubernetes", question: "Чи працювали з Kubernetes? Де, скільки?", status: "open", fact_ids: [] }],
  filters_passed: false,
  flags: ["Формат remote — не з профілю."],
  updated_at: "2026-10-22T09:00:00Z",
  stale_since: "2026-10-23T08:00:00Z",
};

/** Межа — fetch: відповідь або збій мережі. */
function apiWith(respond: (input: string, init: RequestInit | undefined) => Response | Promise<Response>) {
  const fetchFn = vi.fn<typeof fetch>((input, init) => Promise.resolve(respond(String(input), init)));
  const client = createApiClient(fetchFn, "/api");
  client.setCsrfToken("csrf-1");
  return { api: createHttpJobsApi(client), fetchFn };
}

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

describe("GET /jobs", () => {
  test("розбирає список і джерела в доменні типи", async () => {
    const { api } = apiWith(() => json(200, { items: [ITEM], sources: ["manual"], counts: COUNTS }));
    expect(await api.list(QUERY)).toEqual({
      items: [
        {
          id: 7,
          source: "manual",
          url: "https://acme.com/j/7",
          title: "Backend",
          company: "Acme",
          createdAt: "2026-10-20T10:00:00Z",
          needsText: false,
          dismissed: false,
          score: null,
          filtersPassed: null,
          workMode: null,
          triageScore: null,
          triageVerdict: null,
          triageReason: null,
          status: null,
          isNew: false,
        },
      ],
      sources: ["manual"],
      counts: { inProgress: 0, appliedUnreviewed: 0, needsText: false },
    });
  });

  test("applied_unreviewed читається числом, нуль лишається нулем", async () => {
    const counts = { in_progress: 0, applied_unreviewed: 0, needs_text: false };
    const { api } = apiWith(() => json(200, { items: [], sources: [], counts }));
    expect((await api.list(QUERY)).counts.appliedUnreviewed).toBe(0);
  });

  test("лічильники табів з відповіді стають inProgress, appliedUnreviewed, needsText", async () => {
    const counts = { in_progress: 18, applied_unreviewed: 2, needs_text: true };
    const { api } = apiWith(() => json(200, { items: [], sources: [], counts }));
    expect((await api.list(QUERY)).counts).toEqual({ inProgress: 18, appliedUnreviewed: 2, needsText: true });
  });

  test("етап іде параметром stage", async () => {
    const { api, fetchFn } = apiWith(() => json(200, { items: [], sources: [], counts: COUNTS }));
    await api.list({ ...QUERY, stage: "in_progress" });
    const url = new URL(String(fetchFn.mock.calls[0]?.[0]), "http://x");
    expect(Object.fromEntries(url.searchParams)).toEqual({ stage: "in_progress", limit: "200" });
  });

  test("is_new з відповіді стає isNew", async () => {
    const { api } = apiWith(() => json(200, { items: [{ ...ITEM, source: "ats:greenhouse", is_new: true }], sources: ["ats:greenhouse"], counts: COUNTS }));
    expect((await api.list(QUERY)).items[0]).toMatchObject({ source: "ats:greenhouse", isNew: true });
  });

  test("проаналізована й протріажована вакансія несе обидва скори окремо (нуль — оцінка)", async () => {
    const item = { ...ITEM, score: 0, filters_passed: false, work_mode: "hybrid", triage_score: 86, triage_verdict: "analyse", triage_reason: "Стек збігається" };
    const { api } = apiWith(() => json(200, { items: [item], sources: [], counts: COUNTS }));
    expect((await api.list(QUERY)).items[0]).toMatchObject({
      score: 0,
      filtersPassed: false,
      workMode: "hybrid",
      triageScore: 86,
      triageVerdict: "analyse",
      triageReason: "Стек збігається",
    });
  });

  test("статус подачі в рядку списку", async () => {
    const { api } = apiWith(() => json(200, { items: [{ ...ITEM, status: "interview" }], sources: [], counts: COUNTS }));
    expect((await api.list(QUERY)).items[0]).toMatchObject({ status: "interview" });
  });

  test("статус чи група йдуть параметром status", async () => {
    const { api, fetchFn } = apiWith(() => json(200, { items: [], sources: [], counts: COUNTS }));
    await api.list({ ...QUERY, status: "active" });
    const url = new URL(String(fetchFn.mock.calls[0]?.[0]), "http://x");
    expect(Object.fromEntries(url.searchParams)).toEqual({ status: "active", limit: "200" });
  });

  test("вердикт і формат йдуть параметрами triage_verdict і work_mode", async () => {
    const { api, fetchFn } = apiWith(() => json(200, { items: [], sources: [], counts: COUNTS }));
    await api.list({ ...QUERY, triageVerdict: "skip", workMode: "onsite" });
    const url = new URL(String(fetchFn.mock.calls[0]?.[0]), "http://x");
    expect(Object.fromEntries(url.searchParams)).toEqual({ triage_verdict: "skip", work_mode: "onsite", limit: "200" });
  });

  test("порожні фільтри не потрапляють в адресу, лише ліміт", async () => {
    const { api, fetchFn } = apiWith(() => json(200, { items: [], sources: [], counts: COUNTS }));
    await api.list(QUERY);
    expect(fetchFn.mock.calls[0]?.[0]).toBe("/api/jobs?limit=200");
  });

  test("фільтри йдуть параметрами; прапорці — лише коли вони true", async () => {
    const { api, fetchFn } = apiWith(() => json(200, { items: [], sources: [], counts: COUNTS }));
    await api.list({ query: "rust & go", days: "7", source: "manual", needsText: true, dismissed: true, triageVerdict: "", workMode: "", status: "", stage: "", limit: 200 });
    const url = new URL(String(fetchFn.mock.calls[0]?.[0]), "http://x");
    expect(url.pathname).toBe("/api/jobs");
    expect(Object.fromEntries(url.searchParams)).toEqual({
      query: "rust & go",
      days: "7",
      source: "manual",
      needs_text: "true",
      dismissed: "true",
      limit: "200",
    });
  });

  test.each([401, 422, 500])("відповідь %i — JobsUnavailableError", async (status) => {
    const { api } = apiWith(() => json(status, { code: "x" }));
    await expect(api.list(QUERY)).rejects.toBeInstanceOf(JobsUnavailableError);
  });

  test("збій мережі — JobsUnavailableError", async () => {
    const { api } = apiWith(() => Promise.reject(new TypeError("offline")));
    await expect(api.list(QUERY)).rejects.toBeInstanceOf(JobsUnavailableError);
  });

  test.each([
    ["не об'єкт", []],
    ["items не масив", { items: {}, sources: [], counts: COUNTS }],
    ["sources не рядки", { items: [], sources: [1], counts: COUNTS }],
    ["елемент без job_id", { items: [{ ...ITEM, job_id: "7" }], sources: [], counts: COUNTS }],
    ["елемент без прапорця", { items: [{ ...ITEM, needs_text: "no" }], sources: [], counts: COUNTS }],
    ["is_new не прапорець", { items: [{ ...ITEM, is_new: "yes" }], sources: [], counts: COUNTS }],
    ["елемент не об'єкт", { items: [1], sources: [], counts: COUNTS }],
    ["назва не рядок", { items: [{ ...ITEM, title: 5 }], sources: [], counts: COUNTS }],
    ["скор аналізу не число", { items: [{ ...ITEM, score: "78" }], sources: [], counts: COUNTS }],
    ["filters_passed не прапорець", { items: [{ ...ITEM, filters_passed: "yes" }], sources: [], counts: COUNTS }],
    ["невідомий формат", { items: [{ ...ITEM, work_mode: "office" }], sources: [], counts: COUNTS }],
    ["невідомий вердикт", { items: [{ ...ITEM, triage_verdict: "great" }], sources: [], counts: COUNTS }],
    ["скор тріажу не ціле", { items: [{ ...ITEM, triage_score: 1.5 }], sources: [], counts: COUNTS }],
    ["причина тріажу не рядок", { items: [{ ...ITEM, triage_reason: 5 }], sources: [], counts: COUNTS }],
    ["невідомий статус подачі", { items: [{ ...ITEM, status: "hired" }], sources: [], counts: COUNTS }],
    ["без лічильників", { items: [], sources: [] }],
    ["лічильники не об'єкт", { items: [], sources: [], counts: 5 }],
    ["in_progress не ціле", { items: [], sources: [], counts: { ...COUNTS, in_progress: "3" } }],
    ["in_progress дробове", { items: [], sources: [], counts: { ...COUNTS, in_progress: 1.5 } }],
    ["applied_unreviewed не ціле", { items: [], sources: [], counts: { ...COUNTS, applied_unreviewed: true } }],
    ["needs_text не прапорець", { items: [], sources: [], counts: { ...COUNTS, needs_text: "yes" } }],
  ])("%s — не за контрактом", async (_name, body) => {
    const { api } = apiWith(() => json(200, body));
    await expect(api.list(QUERY)).rejects.toBeInstanceOf(JobsUnavailableError);
  });
});

describe("GET /jobs/{id}", () => {
  test("розбирає вакансію; текст лишається рядком", async () => {
    const { api, fetchFn } = apiWith(() => json(200, JOB));
    const job = await api.get(7);
    expect(fetchFn.mock.calls[0]?.[0]).toBe("/api/jobs/7");
    expect(job).toEqual({
      id: 7,
      source: "manual",
      url: "https://acme.com/j/7",
      title: "Backend",
      company: "Acme",
      location: "Valencia",
      text: "Опис <b>жирний</b>",
      createdAt: "2026-10-20T10:00:00Z",
      needsText: false,
      dismissedAt: null,
      dismissReason: null,
      triage: null,
    });
  });

  test("тріаж у деталях — окремий об'єкт", async () => {
    const triage = { score: 86, verdict: "maybe", reason: "Коротко", triaged_at: "2026-10-21T09:00:00Z", source: "agent" };
    const { api } = apiWith(() => json(200, { ...JOB, triage }));
    expect((await api.get(7)).triage).toEqual({ score: 86, verdict: "maybe", reason: "Коротко", triagedAt: "2026-10-21T09:00:00Z", source: "agent" });
  });

  test("тріаж правил сервера — source rules", async () => {
    const triage = { score: 45, verdict: "maybe", reason: "Невпевнено", triaged_at: "2026-10-21T09:00:00Z", source: "rules" };
    const { api } = apiWith(() => json(200, { ...JOB, triage }));
    expect((await api.get(7)).triage).toMatchObject({ source: "rules" });
  });

  test("вакансія без тексту — text null", async () => {
    const { api } = apiWith(() => json(200, { ...JOB, text: null, needs_text: true }));
    expect(await api.get(7)).toMatchObject({ text: null, needsText: true });
  });

  test("схована — час і причина", async () => {
    const { api } = apiWith(() => json(200, { ...JOB, dismissed_at: "2026-10-21T08:00:00Z", dismiss_reason: "не цікаво" }));
    expect(await api.get(7)).toMatchObject({ dismissedAt: "2026-10-21T08:00:00Z", dismissReason: "не цікаво" });
  });

  test("404 — JobNotFoundError", async () => {
    const { api } = apiWith(() => json(404, { code: "not_found" }));
    await expect(api.get(7)).rejects.toBeInstanceOf(JobNotFoundError);
  });

  test.each([401, 500])("відповідь %i — JobsUnavailableError", async (status) => {
    const { api } = apiWith(() => json(status, {}));
    await expect(api.get(7)).rejects.toBeInstanceOf(JobsUnavailableError);
  });

  test.each([
    ["не об'єкт", "text"],
    ["поле не за типом", { ...JOB, needs_text: 1 }],
    ["час схову не рядок", { ...JOB, dismissed_at: 5 }],
    ["локація не рядок", { ...JOB, location: 5 }],
    ["тріаж не об'єкт", { ...JOB, triage: "x" }],
    ["вердикт тріажу невідомий", { ...JOB, triage: { score: 1, verdict: "great", reason: "r", triaged_at: "2026-10-21T09:00:00Z", source: "agent" } }],
    ["скор тріажу не число", { ...JOB, triage: { score: "1", verdict: "skip", reason: "r", triaged_at: "2026-10-21T09:00:00Z", source: "agent" } }],
    ["автор тріажу невідомий", { ...JOB, triage: { score: 1, verdict: "skip", reason: "r", triaged_at: "2026-10-21T09:00:00Z", source: "human" } }],
    ["автора тріажу нема", { ...JOB, triage: { score: 1, verdict: "skip", reason: "r", triaged_at: "2026-10-21T09:00:00Z" } }],
  ])("%s — не за контрактом", async (_name, body) => {
    const { api } = apiWith(() => json(200, body));
    await expect(api.get(7)).rejects.toBeInstanceOf(JobsUnavailableError);
  });
});

describe("422 з тілом не за контрактом", () => {
  test("тіло не об'єкт — JobsUnavailableError", async () => {
    const { api } = apiWith(() => json(422, []));
    await expect(api.dismiss([1], "x")).rejects.toBeInstanceOf(JobsUnavailableError);
  });
});

describe("клієнт кинув не Error", () => {
  test("будь-яке значення стає JobsUnavailableError зі стандартним текстом", async () => {
    const api = createHttpJobsApi({ request: () => Promise.reject("offline"), setCsrfToken: () => {} });
    await expect(api.getAnalysis(7)).rejects.toMatchObject({ message: "Мережа недоступна" });
  });
});

describe("GET /jobs/{id}/analysis", () => {
  test("розбирає аналіз, flags і знак застарілості", async () => {
    const { api, fetchFn } = apiWith(() => json(200, ANALYSIS));
    const analysis = await api.getAnalysis(7);
    expect(fetchFn.mock.calls[0]?.[0]).toBe("/api/jobs/7/analysis");
    expect(analysis).toEqual({
      id: 7,
      score: 78,
      summary: "Бекенд-роль.",
      mustHave: ["Python"],
      niceToHave: ["Go"],
      keywords: ["asyncio"],
      seniority: "senior",
      workMode: "remote",
      location: "Madrid",
      languages: ["English"],
      salaryMinEur: 60000,
      salaryMaxEur: 80000,
      relocation: false,
      reasons: ["Збігається стек"],
      gaps: [{ number: 1, gap: "Kubernetes", question: "Чи працювали з Kubernetes? Де, скільки?", status: "open", factIds: [] }],
      filtersPassed: false,
      flags: ["Формат remote — не з профілю."],
      updatedAt: "2026-10-22T09:00:00Z",
      staleSince: "2026-10-23T08:00:00Z",
    });
  });

  test("прогалини: питання, статус і номери фактів, що її закривають", async () => {
    const gaps = [
      { number: 1, gap: "Kubernetes", question: "Чи працювали з Kubernetes?", status: "closed", fact_ids: [12, 15] },
      { number: 2, gap: "Kafka", question: null, status: "no_experience", fact_ids: [] },
      { number: 3, gap: "Go", question: "Чи писали на Go?", status: "open", fact_ids: [] },
    ];
    const { api } = apiWith(() => json(200, { ...ANALYSIS, gaps }));
    expect((await api.getAnalysis(7)).gaps).toEqual([
      { number: 1, gap: "Kubernetes", question: "Чи працювали з Kubernetes?", status: "closed", factIds: [12, 15] },
      { number: 2, gap: "Kafka", question: null, status: "no_experience", factIds: [] },
      { number: 3, gap: "Go", question: "Чи писали на Go?", status: "open", factIds: [] },
    ]);
  });

  test("нічого не сказано — null і порожні списки; оцінка 0 лишається нулем", async () => {
    const bare = {
      ...ANALYSIS,
      score: 0,
      seniority: null,
      work_mode: null,
      location: null,
      salary_min_eur: null,
      salary_max_eur: null,
      relocation: null,
      must_have: [],
      gaps: [],
      flags: [],
      filters_passed: true,
      stale_since: null,
    };
    const { api } = apiWith(() => json(200, bare));
    expect(await api.getAnalysis(7)).toMatchObject({
      score: 0,
      seniority: null,
      workMode: null,
      location: null,
      salaryMinEur: null,
      relocation: null,
      mustHave: [],
      gaps: [],
      staleSince: null,
    });
  });

  test("404 — AnalysisNotFoundError: аналізу ще нема", async () => {
    const { api } = apiWith(() => json(404, { code: "not_found" }));
    await expect(api.getAnalysis(7)).rejects.toBeInstanceOf(AnalysisNotFoundError);
  });

  test.each([401, 500])("відповідь %i — JobsUnavailableError", async (status) => {
    const { api } = apiWith(() => json(status, {}));
    await expect(api.getAnalysis(7)).rejects.toBeInstanceOf(JobsUnavailableError);
  });

  test("збій мережі — JobsUnavailableError", async () => {
    const { api } = apiWith(() => Promise.reject(new TypeError("offline")));
    await expect(api.getAnalysis(7)).rejects.toBeInstanceOf(JobsUnavailableError);
  });

  test.each([
    ["не об'єкт", []],
    ["скор не число", { ...ANALYSIS, score: "78" }],
    ["список не масив", { ...ANALYSIS, must_have: "Python" }],
    ["прогалини не масив", { ...ANALYSIS, gaps: "Kubernetes" }],
    ["прогалина не об'єкт", { ...ANALYSIS, gaps: ["Kubernetes"] }],
    ["прогалина без тексту", { ...ANALYSIS, gaps: [{ number: 1, question: null, status: "open", fact_ids: [] }] }],
    ["прогалина без номера", { ...ANALYSIS, gaps: [{ gap: "Kubernetes", question: null, status: "open", fact_ids: [] }] }],
    ["питання прогалини не рядок", { ...ANALYSIS, gaps: [{ number: 1, gap: "Kubernetes", question: 5, status: "open", fact_ids: [] }] }],
    ["прогалина без статусу", { ...ANALYSIS, gaps: [{ number: 1, gap: "Kubernetes", question: null, fact_ids: [] }] }],
    ["невідомий статус прогалини", { ...ANALYSIS, gaps: [{ number: 1, gap: "Kubernetes", question: null, status: "done", fact_ids: [] }] }],
    ["номери фактів не масив", { ...ANALYSIS, gaps: [{ number: 1, gap: "Kubernetes", question: null, status: "closed", fact_ids: 12 }] }],
    ["номер факту не ціле", { ...ANALYSIS, gaps: [{ number: 1, gap: "Kubernetes", question: null, status: "closed", fact_ids: ["12"] }] }],
    ["елемент списку не рядок", { ...ANALYSIS, must_have: [1] }],
    ["невідомий рівень", { ...ANALYSIS, seniority: "guru" }],
    ["невідомий формат", { ...ANALYSIS, work_mode: "office" }],
    ["локація не рядок", { ...ANALYSIS, location: 5 }],
    ["вилка не ціле", { ...ANALYSIS, salary_max_eur: 1.5 }],
    ["переїзд не прапорець", { ...ANALYSIS, relocation: "no" }],
    ["filters_passed не прапорець", { ...ANALYSIS, filters_passed: 1 }],
    ["час не рядок", { ...ANALYSIS, updated_at: 5 }],
    ["stale_since не рядок", { ...ANALYSIS, stale_since: 5 }],
  ])("%s — не за контрактом", async (_name, body) => {
    const { api } = apiWith(() => json(200, body));
    await expect(api.getAnalysis(7)).rejects.toBeInstanceOf(JobsUnavailableError);
  });
});

describe("POST /jobs/dismiss", () => {
  test("шле номери й причину з CSRF-токеном", async () => {
    const { api, fetchFn } = apiWith(() => new Response(null, { status: 204 }));
    await api.dismiss([3, 4], "не цікаво");
    const [url, init] = fetchFn.mock.calls[0] ?? [];
    expect(url).toBe("/api/jobs/dismiss");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ job_ids: [3, 4], reason: "не цікаво" });
    expect((init?.headers as Record<string, string>)["X-CSRF-Token"]).toBe("csrf-1");
  });

  test("422 — тексти біля полів", async () => {
    const body = { code: "invalid_value", field_errors: [{ field: "reason", message: "Вкажи причину приховування." }] };
    const { api } = apiWith(() => json(422, body));
    const failure = await api.dismiss([1], "").catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(JobsValidationError);
    expect((failure as JobsValidationError).fieldErrors).toEqual({ reason: "Вкажи причину приховування." });
  });

  test("409 — на вакансію є подача: JobAppliedError", async () => {
    const { api } = apiWith(() => json(409, { code: "job_has_application", message: "На вакансію 1 уже є подача — поданих вакансій не ховають." }));
    await expect(api.dismiss([1], "x")).rejects.toBeInstanceOf(JobAppliedError);
  });

  test("422 без розпізнаних полів — JobsUnavailableError", async () => {
    const { api } = apiWith(() => json(422, { code: "invalid_request" }));
    await expect(api.dismiss([1], "x")).rejects.toBeInstanceOf(JobsUnavailableError);
  });

  test("422 з порожнім переліком полів — JobsUnavailableError", async () => {
    const { api } = apiWith(() => json(422, { field_errors: [] }));
    await expect(api.dismiss([1], "x")).rejects.toBeInstanceOf(JobsUnavailableError);
  });

  test("422 зі зламаним елементом поля — JobsUnavailableError", async () => {
    const { api } = apiWith(() => json(422, { field_errors: [{ field: "reason" }] }));
    await expect(api.dismiss([1], "x")).rejects.toBeInstanceOf(JobsUnavailableError);
  });

  test("перший текст на поле лишається", async () => {
    const body = {
      field_errors: [
        { field: "job_ids", message: "Перший." },
        { field: "job_ids", message: "Другий." },
      ],
    };
    const { api } = apiWith(() => json(422, body));
    const failure = await api.dismiss([1], "x").catch((error: unknown) => error);
    expect((failure as JobsValidationError).fieldErrors).toEqual({ job_ids: "Перший." });
  });

  test.each([401, 403, 500])("відповідь %i — JobsUnavailableError", async (status) => {
    const { api } = apiWith(() => json(status, {}));
    await expect(api.dismiss([1], "x")).rejects.toBeInstanceOf(JobsUnavailableError);
  });
});

describe("POST /jobs/{id}/restore", () => {
  test("204 — успіх із CSRF-токеном", async () => {
    const { api, fetchFn } = apiWith(() => new Response(null, { status: 204 }));
    await api.restore(7);
    const [url, init] = fetchFn.mock.calls[0] ?? [];
    expect(url).toBe("/api/jobs/7/restore");
    expect(init?.method).toBe("POST");
    expect((init?.headers as Record<string, string>)["X-CSRF-Token"]).toBe("csrf-1");
  });

  test("404 — JobNotFoundError", async () => {
    const { api } = apiWith(() => json(404, {}));
    await expect(api.restore(7)).rejects.toBeInstanceOf(JobNotFoundError);
  });

  test.each([403, 500])("відповідь %i — JobsUnavailableError", async (status) => {
    const { api } = apiWith(() => json(status, {}));
    await expect(api.restore(7)).rejects.toBeInstanceOf(JobsUnavailableError);
  });
});

describe("POST /jobs", () => {
  const INPUT = { text: "Опис", url: "https://acme.com/j/1", title: "Dev", company: "Acme" };

  test("шле поля форми з CSRF-токеном", async () => {
    const { api, fetchFn } = apiWith(() => json(201, { job_id: 8, duplicate: false, outcome: "created" }));
    await api.add(INPUT);
    const [url, init] = fetchFn.mock.calls[0] ?? [];
    expect(url).toBe("/api/jobs");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual(INPUT);
    expect((init?.headers as Record<string, string>)["X-CSRF-Token"]).toBe("csrf-1");
  });

  test("201 — нова вакансія", async () => {
    const { api } = apiWith(() => json(201, { job_id: 8, duplicate: false, outcome: "created" }));
    expect(await api.add(INPUT)).toEqual({ id: 8, outcome: "created" });
  });

  test("200 — дубль наявної", async () => {
    const { api } = apiWith(() => json(200, { job_id: 3, duplicate: true, outcome: "duplicate" }));
    expect(await api.add(INPUT)).toEqual({ id: 3, outcome: "duplicate" });
  });

  test("200 — текст дописано у вакансію з алерту", async () => {
    const { api } = apiWith(() => json(200, { job_id: 4, duplicate: false, outcome: "text_added" }));
    expect(await api.add(INPUT)).toEqual({ id: 4, outcome: "text_added" });
  });

  test("422 — тексти біля полів", async () => {
    const body = {
      code: "invalid_fields",
      field_errors: [
        { field: "text", message: "Встав текст опису вакансії." },
        { field: "url", message: "Посилання має починатися з http:// або https://." },
      ],
    };
    const { api } = apiWith(() => json(422, body));
    const failure = await api.add(INPUT).catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(JobsValidationError);
    expect((failure as JobsValidationError).fieldErrors).toEqual({
      text: "Встав текст опису вакансії.",
      url: "Посилання має починатися з http:// або https://.",
    });
  });

  test("422 без розпізнаних полів — JobsUnavailableError", async () => {
    const { api } = apiWith(() => json(422, { code: "invalid_request" }));
    await expect(api.add(INPUT)).rejects.toBeInstanceOf(JobsUnavailableError);
  });

  test.each([401, 403, 500])("відповідь %i — JobsUnavailableError", async (status) => {
    const { api } = apiWith(() => json(status, {}));
    await expect(api.add(INPUT)).rejects.toBeInstanceOf(JobsUnavailableError);
  });

  test("збій мережі — JobsUnavailableError", async () => {
    const { api } = apiWith(() => Promise.reject(new TypeError("offline")));
    await expect(api.add(INPUT)).rejects.toBeInstanceOf(JobsUnavailableError);
  });

  test.each([
    ["не об'єкт", []],
    ["job_id не число", { job_id: "8", duplicate: false, outcome: "created" }],
    ["невідомий outcome", { job_id: 8, duplicate: false, outcome: "merged" }],
    ["outcome відсутній", { job_id: 8, duplicate: false }],
  ])("%s — не за контрактом", async (_name, body) => {
    const { api } = apiWith(() => json(201, body));
    await expect(api.add(INPUT)).rejects.toBeInstanceOf(JobsUnavailableError);
  });
});
