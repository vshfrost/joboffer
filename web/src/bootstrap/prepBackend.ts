/** Підроблений бекенд підготовки для тестів: `/api/prep…` і `/api/jobs/{n}/prep|interview-kit` над станом у памʼяті, решта запитів — профіль (сесія). Збігається з `app/infrastructure/http/prep.py`. */
import { vi } from "vitest";

import { FULL_PROFILE, profileBackend, type ApiProfile } from "./profileBackend";
import { json } from "./testClient";

export interface ApiQuiz {
  total: number;
  due: number;
}

export interface ApiTopicJob {
  job_id: number;
  title: string | null;
  company: string | null;
  score: number;
  gap: string;
}

export interface ApiResource {
  title: string;
  url: string;
}

export interface ApiStep {
  step_id: number;
  position: number;
  kind: string;
  title: string;
  minutes: number;
  details: string;
  resources: ApiResource[];
  done_at: string | null;
  done_on: string | null;
  note: string;
}

export interface ApiTopicRow {
  topic_id: number;
  slug: string;
  title: string;
  kind: string;
  summary: string;
  status: string;
  percent: number;
  steps_done: number;
  steps_total: number;
  minutes_left: number;
  deadline: string | null;
  priority: number;
  jobs: ApiTopicJob[];
  quiz: ApiQuiz;
}

export interface ApiTopic extends ApiTopicRow {
  next_step_id: number | null;
  steps: ApiStep[];
}

export interface ApiKit {
  kit_id: number;
  job_id: number;
  version: number;
  created_at: string;
  created_on: string;
  questions: { kind: string; question: string; topic_id: number | null }[];
  stories: { title: string; situation: string; task: string; action: string; result: string; fact_ids: number[] }[];
  company_questions: string[];
}

/** Момент виконання кроку в підробленому бекенді: 11:30 за Мадридом 2026-10-27. */
export const DONE_AT = "2026-10-27T10:30:00Z";
export const DONE_ON = "2026-10-27";
const NOTE_LIMIT = 2000;

export function apiJob(n: number, overrides: Partial<ApiTopicJob> = {}): ApiTopicJob {
  return { job_id: n, title: `Backend Engineer ${n}`, company: `Company ${n}`, score: 80, gap: `Прогалина вакансії ${n}.`, ...overrides };
}

export function apiStep(n: number, overrides: Partial<ApiStep> = {}): ApiStep {
  return {
    step_id: n,
    position: n,
    kind: "learn",
    title: `Крок ${n}`,
    minutes: 30,
    details: `Що зробити на кроці ${n}.`,
    resources: [],
    done_at: null,
    done_on: null,
    note: "",
    ...overrides,
  };
}

/** Крок, виконаний 2026-10-25 (за Мадридом) із нотаткою. */
export function doneStep(n: number, overrides: Partial<ApiStep> = {}): ApiStep {
  return apiStep(n, { done_at: "2026-10-25T08:00:00Z", done_on: "2026-10-25", note: `Нотатка до кроку ${n}.`, ...overrides });
}

/** Поля, що виводяться з кроків і ручної готовності (як `domain/prep/topic.py` на сервері). */
export function derive(topic: ApiTopic, ready: boolean): ApiTopic {
  const done = topic.steps.filter((step) => step.done_at !== null);
  const pending = topic.steps.filter((step) => step.done_at === null);
  const status = ready ? "ready" : topic.steps.length === 0 ? "new" : done.length === 0 ? "planned" : done.some((step) => step.kind === "practice") ? "practicing" : "learning";
  const percent = ready ? 100 : topic.steps.length === 0 ? 0 : Math.floor((done.length / topic.steps.length) * 100 + 0.5);
  return {
    ...topic,
    status,
    percent,
    steps_done: done.length,
    steps_total: topic.steps.length,
    minutes_left: pending.reduce((sum, step) => sum + step.minutes, 0),
    next_step_id: pending[0]?.step_id ?? null,
  };
}

export function apiTopic(n: number, overrides: Partial<ApiTopic> & { ready?: boolean } = {}): ApiTopic {
  const { ready = false, ...rest } = overrides;
  const base: ApiTopic = {
    topic_id: n,
    slug: `topic-${n}`,
    title: `Тема ${n}`,
    kind: "tech",
    summary: `Опис теми ${n}.`,
    status: "new",
    percent: 0,
    steps_done: 0,
    steps_total: 0,
    minutes_left: 0,
    deadline: null,
    priority: 80,
    jobs: [apiJob(24)],
    quiz: { total: 0, due: 0 },
    next_step_id: null,
    steps: [],
    ...rest,
  };
  return derive(base, ready);
}

export function apiKit(jobId: number, overrides: Partial<ApiKit> = {}): ApiKit {
  return {
    kit_id: 1,
    job_id: jobId,
    version: 2,
    created_at: "2026-10-27T09:00:00Z",
    created_on: "2026-10-27",
    questions: [{ kind: "technical", question: "How do you draw aggregate boundaries?", topic_id: 1 }],
    stories: [{ title: "Запуск сервісу", situation: "S", task: "T", action: "A", result: "R", fact_ids: [12, 18] }],
    company_questions: ["How does the team make architecture decisions?"],
    ...overrides,
  };
}

/** Тіло помилки сервера: `{code, message, field_errors, correlation_id}`. */
export function problem(status: number, code: string, message: string, fieldErrors: { field: string; message: string }[] = []): Response {
  return json(status, { code, message, field_errors: fieldErrors, correlation_id: "test-correlation" });
}

export interface PrepOverrides {
  /** Відповідь на `GET /api/prep/topics`; `undefined` — звичайна. */
  topics?: () => Response | Promise<Response> | undefined;
  /** Відповідь на `GET /api/prep/topics/{n}`; `undefined` — звичайна. */
  topic?: (id: number) => Response | Promise<Response> | undefined;
  /** Відповідь на `POST /api/prep/steps/{n}/done`; `undefined` — звичайна (перевірка як на сервері). */
  done?: (id: number, body: { note: string }) => Response | Promise<Response> | undefined;
  /** Відповідь на `PUT /api/prep/topics/{n}/ready`; `undefined` — звичайна. */
  ready?: (id: number, body: { ready: boolean }) => Response | Promise<Response> | undefined;
}

export interface PrepBackend {
  fetchFn: typeof fetch;
  topics: ApiTopic[];
  /** Загальні лічильники квізу; `undefined` — сума лічильників тем. */
  quiz: ApiQuiz | undefined;
  kits: Record<number, ApiKit>;
  /** Теми з ручною позначкою «готова» (спершу — ті, що в початкових даних мають статус ready). */
  ready: Set<number>;
  /** Усі запити до `/api/prep…`, `/api/jobs/{n}/prep|interview-kit` як «МЕТОД шлях». */
  requests: string[];
  /** Тіла POST/PUT за шляхом. */
  bodies: Record<string, unknown[]>;
}

function row(topic: ApiTopic): ApiTopicRow {
  const copy: Record<string, unknown> = { ...topic };
  delete copy["next_step_id"];
  delete copy["steps"];
  return copy as unknown as ApiTopicRow;
}

function readBody(init: RequestInit | undefined): Record<string, unknown> {
  return JSON.parse(String(init?.body)) as Record<string, unknown>;
}

export function prepBackend(
  initial: { topics?: ApiTopic[]; quiz?: ApiQuiz; kits?: ApiKit[] } = {},
  overrides: PrepOverrides = {},
  profile: ApiProfile = FULL_PROFILE,
): PrepBackend {
  const rest = profileBackend(profile);
  const backend: PrepBackend = {
    fetchFn: fetch,
    topics: structuredClone(initial.topics ?? []),
    quiz: initial.quiz,
    kits: Object.fromEntries((initial.kits ?? []).map((kit) => [kit.job_id, structuredClone(kit)])),
    ready: new Set((initial.topics ?? []).filter((topic) => topic.status === "ready").map((topic) => topic.topic_id)),
    requests: [],
    bodies: {},
  };
  const find = (id: number) => backend.topics.find((topic) => topic.topic_id === id);
  const refresh = (topic: ApiTopic) => {
    backend.topics[backend.topics.indexOf(topic)] = derive(topic, backend.ready.has(topic.topic_id));
    return find(topic.topic_id) as ApiTopic;
  };
  backend.fetchFn = vi.fn<typeof fetch>((input, init) => {
    const raw = typeof input === "string" ? input : input instanceof URL ? input.pathname + input.search : input.url;
    const url = new URL(raw, "https://app.test");
    const method = init?.method ?? "GET";
    const jobPart = /^\/api\/jobs\/(\d+)\/(prep|interview-kit)$/.exec(url.pathname);
    if (!url.pathname.startsWith("/api/prep") && jobPart === null) {
      return rest.fetchFn(input, init);
    }
    backend.requests.push(`${method} ${url.pathname}`);
    const record = (body: unknown) => (backend.bodies[`${method} ${url.pathname}`] ??= []).push(body);
    if (url.pathname === "/api/prep/topics" && method === "GET") {
      const quiz = backend.quiz ?? { total: backend.topics.reduce((sum, topic) => sum + topic.quiz.total, 0), due: backend.topics.reduce((sum, topic) => sum + topic.quiz.due, 0) };
      return Promise.resolve(overrides.topics?.() ?? json(200, { topics: backend.topics.map(row), quiz }));
    }
    const topicMatch = /^\/api\/prep\/topics\/([^/]+)$/.exec(url.pathname);
    if (topicMatch !== null && method === "GET") {
      const id = Number(topicMatch[1]);
      const custom = overrides.topic?.(id);
      if (custom !== undefined) {
        return Promise.resolve(custom);
      }
      const topic = find(id);
      return Promise.resolve(topic === undefined ? problem(404, "not_found", "Не знайдено") : json(200, topic));
    }
    const stepMatch = /^\/api\/prep\/steps\/([^/]+)\/done$/.exec(url.pathname);
    if (stepMatch !== null && method === "POST") {
      const id = Number(stepMatch[1]);
      const body = readBody(init) as { note: string };
      record(body);
      const custom = overrides.done?.(id, body);
      if (custom !== undefined) {
        return Promise.resolve(custom);
      }
      const topic = backend.topics.find((candidate) => candidate.steps.some((step) => step.step_id === id));
      const step = topic?.steps.find((candidate) => candidate.step_id === id);
      if (topic === undefined || step === undefined) {
        return Promise.resolve(problem(404, "not_found", "Не знайдено"));
      }
      const note = body.note.trim();
      if (note.length > NOTE_LIMIT) {
        const text = "Нотатка — до 2000 символів.";
        return Promise.resolve(problem(422, "invalid_value", text, [{ field: "note", message: text }]));
      }
      step.done_at ??= DONE_AT;
      step.done_on ??= DONE_ON;
      step.note = note === "" ? step.note : note;
      return Promise.resolve(json(200, refresh(topic)));
    }
    const readyMatch = /^\/api\/prep\/topics\/([^/]+)\/ready$/.exec(url.pathname);
    if (readyMatch !== null && method === "PUT") {
      const id = Number(readyMatch[1]);
      const body = readBody(init) as { ready: boolean };
      record(body);
      const custom = overrides.ready?.(id, body);
      if (custom !== undefined) {
        return Promise.resolve(custom);
      }
      const topic = find(id);
      if (topic === undefined) {
        return Promise.resolve(problem(404, "not_found", "Не знайдено"));
      }
      if (body.ready) {
        backend.ready.add(id);
      } else {
        backend.ready.delete(id);
      }
      return Promise.resolve(json(200, refresh(topic)));
    }
    if (jobPart !== null && method === "GET") {
      const jobId = Number(jobPart[1]);
      if (jobPart[2] === "interview-kit") {
        const kit = backend.kits[jobId];
        return Promise.resolve(kit === undefined ? problem(404, "not_found", "Не знайдено") : json(200, kit));
      }
      const own = backend.topics.filter((topic) => topic.jobs.some((job) => job.job_id === jobId));
      const readiness = own.length === 0 ? null : Math.floor(own.reduce((sum, topic) => sum + topic.percent, 0) / own.length + 0.5);
      return Promise.resolve(json(200, { readiness, topics: own.map(row) }));
    }
    return Promise.reject(new Error(`Непередбачений запит: ${method} ${url.pathname}`));
  });
  return backend;
}
