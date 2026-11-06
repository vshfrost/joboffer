import { describe, expect, test, vi } from "vitest";

import { PrepNotFoundError, PrepUnauthorizedError, PrepUnavailableError, PrepValidationError } from "../domain/prepErrors";
import type { PrepApi } from "../ports/prepApi";
import { createApiClient } from "./apiClient";
import { createHttpPrepApi } from "./httpPrepApi";

const JOB = { job_id: 24, title: "Senior Backend Engineer", company: "Northstar", score: 86, gap: "Потрібна практика DDD." };
const ROW = {
  topic_id: 7,
  slug: "ddd-symfony",
  title: "DDD у Symfony",
  kind: "tech",
  summary: "Межі агрегатів.",
  status: "practicing",
  percent: 40,
  steps_done: 2,
  steps_total: 5,
  minutes_left: 180,
  deadline: "2026-11-03",
  priority: 165,
  jobs: [JOB],
  quiz: { total: 10, due: 4 },
};
const STEP = {
  step_id: 31,
  position: 1,
  kind: "learn",
  title: "Межі контекстів",
  minutes: 45,
  details: "Опиши bounded contexts.",
  resources: [{ title: "Bounded Context", url: "https://martinfowler.com/bliki/BoundedContext.html" }],
  done_at: "2026-10-25T08:00:00Z",
  done_on: "2026-10-25",
  note: "Склав карту контекстів.",
};
const PENDING = { ...STEP, step_id: 32, position: 2, kind: "check", resources: [], done_at: null, done_on: null, note: "" };
const TOPIC = { ...ROW, next_step_id: 32, steps: [STEP, PENDING] };
const KIT = {
  kit_id: 3,
  job_id: 24,
  version: 2,
  created_at: "2026-10-27T09:00:00Z",
  created_on: "2026-10-27",
  questions: [
    { kind: "technical", question: "How do you draw aggregate boundaries?", topic_id: 7 },
    { kind: "behavioral", question: "Tell me about a risk you raised.", topic_id: null },
  ],
  stories: [{ title: "Запуск сервісу", situation: "S", task: "T", action: "A", result: "R", fact_ids: [12, 18] }],
  company_questions: ["How does the team make architecture decisions?"],
};

/** Межа — fetch: відповідь або збій мережі. */
function apiWith(respond: (input: string, init: RequestInit | undefined) => Response | Promise<Response>) {
  const fetchFn = vi.fn<typeof fetch>((input, init) => Promise.resolve(respond(String(input), init)));
  const client = createApiClient(fetchFn, "/api");
  client.setCsrfToken("csrf-1");
  return { api: createHttpPrepApi(client), fetchFn };
}

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const PARSED_ROW = {
  id: 7,
  slug: "ddd-symfony",
  title: "DDD у Symfony",
  kind: "tech",
  summary: "Межі агрегатів.",
  status: "practicing",
  percent: 40,
  stepsDone: 2,
  stepsTotal: 5,
  minutesLeft: 180,
  deadline: "2026-11-03",
  priority: 165,
  jobs: [{ jobId: 24, title: "Senior Backend Engineer", company: "Northstar", score: 86, gap: "Потрібна практика DDD." }],
  quiz: { total: 10, due: 4 },
};

describe("реєстр тем", () => {
  test("GET /prep/topics: теми зі скором і прогалинами вакансій та загальні лічильники квізу", async () => {
    const { api, fetchFn } = apiWith(() => json(200, { topics: [ROW], quiz: { total: 12, due: 5 } }));

    const overview = await api.topics();

    expect(fetchFn.mock.calls[0]?.[0]).toBe("/api/prep/topics");
    expect(fetchFn.mock.calls[0]?.[1]?.method).toBe("GET");
    expect(overview).toEqual({ topics: [PARSED_ROW], quiz: { total: 12, due: 5 } });
  });

  test("тема без дедлайну, а вакансія без назви й компанії зберігають null", async () => {
    const row = { ...ROW, deadline: null, jobs: [{ ...JOB, title: null, company: null }] };
    const { api } = apiWith(() => json(200, { topics: [row], quiz: { total: 0, due: 0 } }));

    const [topic] = (await api.topics()).topics;

    expect(topic?.deadline).toBeNull();
    expect(topic?.jobs[0]).toMatchObject({ title: null, company: null });
  });
});

describe("тема", () => {
  test("GET /prep/topics/7: кроки з ресурсами, днем виконання за Мадридом і нотаткою", async () => {
    const { api, fetchFn } = apiWith(() => json(200, TOPIC));

    const topic = await api.topic(7);

    expect(fetchFn.mock.calls[0]?.[0]).toBe("/api/prep/topics/7");
    expect(topic).toEqual({
      ...PARSED_ROW,
      nextStepId: 32,
      steps: [
        {
          id: 31,
          position: 1,
          kind: "learn",
          title: "Межі контекстів",
          minutes: 45,
          details: "Опиши bounded contexts.",
          resources: [{ title: "Bounded Context", url: "https://martinfowler.com/bliki/BoundedContext.html" }],
          doneOn: "2026-10-25",
          note: "Склав карту контекстів.",
        },
        { id: 32, position: 2, kind: "check", title: "Межі контекстів", minutes: 45, details: "Опиши bounded contexts.", resources: [], doneOn: null, note: "" },
      ],
    });
  });

  test("усі кроки виконано — next_step_id null", async () => {
    const { api } = apiWith(() => json(200, { ...TOPIC, next_step_id: null }));

    expect((await api.topic(7)).nextStepId).toBeNull();
  });

  test("теми нема чи вона чужа (404) — PrepNotFoundError", async () => {
    const { api } = apiWith(() => json(404, { code: "not_found", message: "Не знайдено", field_errors: [], correlation_id: "x" }));

    await expect(api.topic(99)).rejects.toBeInstanceOf(PrepNotFoundError);
  });
});

describe("«виконано» з нотаткою", () => {
  test("POST /prep/steps/32/done з нотаткою і CSRF-токеном повертає тему", async () => {
    const { api, fetchFn } = apiWith(() => json(200, TOPIC));

    const topic = await api.completeStep(32, "Зробив");

    const [path, init] = fetchFn.mock.calls[0] ?? [];
    expect(path).toBe("/api/prep/steps/32/done");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(JSON.stringify({ note: "Зробив" }));
    expect((init?.headers as Record<string, string>)["X-CSRF-Token"]).toBe("csrf-1");
    expect(topic.id).toBe(7);
  });

  test("нотатка задовга (422) — PrepValidationError із текстом біля поля note", async () => {
    const field_errors = [{ field: "note", message: "Нотатка — до 2000 символів." }];
    const { api } = apiWith(() => json(422, { code: "invalid_value", message: "Нотатка задовга.", field_errors, correlation_id: "x" }));

    const error = await api.completeStep(32, "x").catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(PrepValidationError);
    expect((error as PrepValidationError).message).toBe("Нотатка задовга.");
    expect((error as PrepValidationError).fieldErrors).toEqual({ note: "Нотатка — до 2000 символів." });
  });

  test("422 без повідомлення дає загальний текст, а перший текст поля переважає", async () => {
    const field_errors = [
      { field: "note", message: "Перший." },
      { field: "note", message: "Другий." },
    ];
    const { api } = apiWith(() => json(422, { code: "invalid_value", field_errors }));

    const error = (await api.completeStep(32, "x").catch((caught: unknown) => caught)) as PrepValidationError;

    expect(error.message).toBe("Нотатка не пройшла перевірку");
    expect(error.fieldErrors).toEqual({ note: "Перший." });
  });

  test.each([
    ["без field_errors", { code: "invalid_request", message: "Крива форма." }],
    ["порожні field_errors", { code: "invalid_request", message: "Крива форма.", field_errors: [] }],
    ["крива помилка поля", { code: "invalid_request", message: "Крива форма.", field_errors: [{ field: "note" }] }],
    ["помилка поля — не обʼєкт", { code: "invalid_request", message: "Крива форма.", field_errors: ["note"] }],
    ["тіло — не обʼєкт", "Крива форма."],
  ])("422, у якому %s, — збій контракту, а не помилка поля", async (_name, body) => {
    const { api } = apiWith(() => json(422, body));

    await expect(api.completeStep(32, "x")).rejects.toBeInstanceOf(PrepUnavailableError);
  });

  test("кроку нема (404) — PrepNotFoundError", async () => {
    const { api } = apiWith(() => json(404, { code: "not_found" }));

    await expect(api.completeStep(99, "")).rejects.toBeInstanceOf(PrepNotFoundError);
  });
});

describe("«тема готова»", () => {
  test("PUT /prep/topics/7/ready з прапорцем повертає тему", async () => {
    const { api, fetchFn } = apiWith(() => json(200, { ...TOPIC, status: "ready", percent: 100 }));

    const topic = await api.setReady(7, true);

    const [path, init] = fetchFn.mock.calls[0] ?? [];
    expect(path).toBe("/api/prep/topics/7/ready");
    expect(init?.method).toBe("PUT");
    expect(init?.body).toBe(JSON.stringify({ ready: true }));
    expect((init?.headers as Record<string, string>)["X-CSRF-Token"]).toBe("csrf-1");
    expect(topic).toMatchObject({ status: "ready", percent: 100 });
  });

  test("теми нема (404) — PrepNotFoundError", async () => {
    const { api } = apiWith(() => json(404, { code: "not_found" }));

    await expect(api.setReady(99, false)).rejects.toBeInstanceOf(PrepNotFoundError);
  });
});

describe("підготовка до вакансії і пакет до інтерв'ю (для блоків вакансії)", () => {
  test("GET /jobs/24/prep: готовність і теми вакансії", async () => {
    const { api, fetchFn } = apiWith(() => json(200, { readiness: 40, topics: [ROW] }));

    const prep = await api.jobPrep(24);

    expect(fetchFn.mock.calls[0]?.[0]).toBe("/api/jobs/24/prep");
    expect(prep).toEqual({ readiness: 40, topics: [PARSED_ROW] });
  });

  test("без тем готовність null — не нуль", async () => {
    const { api } = apiWith(() => json(200, { readiness: null, topics: [] }));

    expect(await api.jobPrep(24)).toEqual({ readiness: null, topics: [] });
  });

  test("вакансії нема (404) — PrepNotFoundError", async () => {
    const { api } = apiWith(() => json(404, { code: "not_found" }));

    await expect(api.jobPrep(99)).rejects.toBeInstanceOf(PrepNotFoundError);
  });

  test("GET /jobs/24/interview-kit: остання версія з питаннями, історіями й питаннями до компанії", async () => {
    const { api, fetchFn } = apiWith(() => json(200, KIT));

    const kit = await api.interviewKit(24);

    expect(fetchFn.mock.calls[0]?.[0]).toBe("/api/jobs/24/interview-kit");
    expect(kit).toEqual({
      id: 3,
      jobId: 24,
      version: 2,
      createdOn: "2026-10-27",
      questions: [
        { kind: "technical", question: "How do you draw aggregate boundaries?", topicId: 7 },
        { kind: "behavioral", question: "Tell me about a risk you raised.", topicId: null },
      ],
      stories: [{ title: "Запуск сервісу", situation: "S", task: "T", action: "A", result: "R", factIds: [12, 18] }],
      companyQuestions: ["How does the team make architecture decisions?"],
    });
  });

  test("пакета нема (404) — PrepNotFoundError", async () => {
    const { api } = apiWith(() => json(404, { code: "not_found" }));

    await expect(api.interviewKit(24)).rejects.toBeInstanceOf(PrepNotFoundError);
  });
});

describe("збої", () => {
  const CALLS: [string, (api: PrepApi) => Promise<unknown>][] = [
    ["topics", (api) => api.topics()],
    ["topic", (api) => api.topic(7)],
    ["completeStep", (api) => api.completeStep(32, "")],
    ["setReady", (api) => api.setReady(7, true)],
    ["jobPrep", (api) => api.jobPrep(24)],
    ["interviewKit", (api) => api.interviewKit(24)],
  ];

  test.each(CALLS)("%s: без сесії (401) — PrepUnauthorizedError", async (_name, call) => {
    const { api } = apiWith(() => json(401, { code: "not_authenticated" }));

    await expect(call(api)).rejects.toBeInstanceOf(PrepUnauthorizedError);
  });

  test.each(CALLS)("%s: помилка сервера (500) — PrepUnavailableError", async (_name, call) => {
    const { api } = apiWith(() => json(500, { code: "internal" }));

    await expect(call(api)).rejects.toBeInstanceOf(PrepUnavailableError);
  });

  test.each(CALLS)("%s: збій мережі — PrepUnavailableError", async (_name, call) => {
    const { api } = apiWith(() => Promise.reject(new TypeError("network")));

    await expect(call(api)).rejects.toBeInstanceOf(PrepUnavailableError);
  });

  test("реєстр: 404 — не «нема», а збій (реєстр завжди існує)", async () => {
    const { api } = apiWith(() => json(404, { code: "not_found" }));

    await expect(api.topics()).rejects.toBeInstanceOf(PrepUnavailableError);
  });
});

describe("відповідь не за контрактом — PrepUnavailableError", () => {
  const overview = (row: unknown) => ({ topics: [row], quiz: { total: 0, due: 0 } });
  const topicWith = (patch: Record<string, unknown>) => ({ ...TOPIC, ...patch });
  const stepWith = (patch: Record<string, unknown>) => topicWith({ steps: [{ ...STEP, ...patch }] });
  const kitWith = (patch: Record<string, unknown>) => ({ ...KIT, ...patch });

  test.each([
    ["тіло — не обʼєкт", [], "topics"],
    ["тіла нема", undefined, "topics"],
    ["topics — не масив", { topics: {}, quiz: { total: 0, due: 0 } }, "topics"],
    ["quiz нема", { topics: [] }, "topics"],
    ["quiz.total — рядок", { topics: [], quiz: { total: "0", due: 0 } }, "topics"],
    ["рядок теми — не обʼєкт", overview("тема"), "topics"],
    ["title — число", overview({ ...ROW, title: 5 }), "topics"],
    ["невідомий вид теми", overview({ ...ROW, kind: "other" }), "topics"],
    ["невідомий статус", overview({ ...ROW, status: "done" }), "topics"],
    ["percent — рядок", overview({ ...ROW, percent: "40" }), "topics"],
    ["deadline — число", overview({ ...ROW, deadline: 20261103 }), "topics"],
    ["jobs — не масив", overview({ ...ROW, jobs: {} }), "topics"],
    ["score вакансії — рядок", overview({ ...ROW, jobs: [{ ...JOB, score: "86" }] }), "topics"],
    ["title вакансії — число", overview({ ...ROW, jobs: [{ ...JOB, title: 5 }] }), "topics"],
    ["quiz теми нема", overview({ ...ROW, quiz: null }), "topics"],
    ["steps — не масив", topicWith({ steps: {} }), "topic"],
    ["невідомий вид кроку", stepWith({ kind: "other" }), "topic"],
    ["resources — не масив", stepWith({ resources: {} }), "topic"],
    ["ресурс без url", stepWith({ resources: [{ title: "Без посилання" }] }), "topic"],
    ["done_on — число", stepWith({ done_on: 20261025 }), "topic"],
    ["note — null", stepWith({ note: null }), "topic"],
    ["next_step_id — рядок", topicWith({ next_step_id: "32" }), "topic"],
    ["readiness — рядок", { readiness: "40", topics: [] }, "jobPrep"],
    ["topics вакансії — не масив", { readiness: null, topics: {} }, "jobPrep"],
    ["questions — не масив", kitWith({ questions: {} }), "kit"],
    ["невідомий вид питання", kitWith({ questions: [{ kind: "other", question: "Q", topic_id: null }] }), "kit"],
    ["topic_id питання — рядок", kitWith({ questions: [{ kind: "technical", question: "Q", topic_id: "7" }] }), "kit"],
    ["stories — не масив", kitWith({ stories: {} }), "kit"],
    ["fact_ids — не масив", kitWith({ stories: [{ ...KIT.stories[0], fact_ids: {} }] }), "kit"],
    ["номер факту — рядок", kitWith({ stories: [{ ...KIT.stories[0], fact_ids: ["12"] }] }), "kit"],
    ["company_questions — не масив", kitWith({ company_questions: {} }), "kit"],
    ["питання до компанії — число", kitWith({ company_questions: [5] }), "kit"],
    ["version — рядок", kitWith({ version: "2" }), "kit"],
  ])("%s", async (_name, body, which) => {
    const { api } = apiWith(() => json(200, body));
    const call = { topics: () => api.topics(), topic: () => api.topic(7), jobPrep: () => api.jobPrep(24), kit: () => api.interviewKit(24) }[which as "topics" | "topic" | "jobPrep" | "kit"];

    await expect(call()).rejects.toBeInstanceOf(PrepUnavailableError);
  });

  test("відповідь без JSON-тіла — теж збій контракту", async () => {
    const { api } = apiWith(() => new Response("<html>", { status: 200 }));

    await expect(api.topic(7)).rejects.toBeInstanceOf(PrepUnavailableError);
  });
});
