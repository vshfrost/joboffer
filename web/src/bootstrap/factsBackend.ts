/** Підроблений бекенд фактів для тестів: `/api/facts…` над станом у памʼяті, правила як на сервері (спрощено). */

import { json, MEANS_LOGGED_IN, noContent } from "./testClient";

export interface ApiFact {
  fact_id: number;
  kind: string;
  text: string;
  confirmed: boolean;
  source: string;
  job_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface ApiCv {
  file_name: string | null;
  text: string;
  saved_at: string;
}

const KINDS = ["experience", "achievement", "project", "skill", "education", "language"];
const MAX_FACT = 500;

export function apiFact(fact_id: number, kind: string, text: string, confirmed = false, source = "cv", job_id: number | null = null): ApiFact {
  return { fact_id, kind, text, confirmed, source, job_id, created_at: "2026-10-20T10:00:00Z", updated_at: "2026-10-20T10:00:00Z" };
}

export type Action = "list" | "cv" | "confirm" | "update" | "remove" | "create";

export interface FactsBackend {
  fetchFn: typeof fetch;
  facts: ApiFact[];
  cv: ApiCv | null;
  /** Рядки «МЕТОД /шлях» усіх запитів до `/api/facts…` у порядку надходження. */
  requests: string[];
  /** Тіла запитів із тілом у порядку надходження. */
  bodies: unknown[];
  /** Наступна відповідь на дію — помилка зі статусом (500 за замовчуванням) і тілом. */
  failNext(action: Action, status?: number, body?: unknown): void;
  /** Затримує відповіді списку, доки не викличуть `release()` (стан завантаження). */
  hold(): { release(): void };
}

const fingerprint = (text: string) => text.split(/\s+/).filter(Boolean).join(" ").toLowerCase();
const problem = (field: string, message: string) => json(422, { code: "invalid_value", message, field_errors: [{ field, message }] });
const notFound = () => json(404, { code: "not_found", message: "Не знайдено", field_errors: [] });

function ordered(facts: ApiFact[]): ApiFact[] {
  return [...facts].sort((a, b) => KINDS.indexOf(a.kind) - KINDS.indexOf(b.kind) || a.fact_id - b.fact_id);
}

function library(facts: ApiFact[]): Response {
  const kinds = KINDS.map((kind) => {
    const own = facts.filter((fact) => fact.kind === kind);
    const confirmed = own.filter((fact) => fact.confirmed).length;
    return { kind, total: own.length, confirmed, unconfirmed: own.length - confirmed };
  });
  const confirmed = facts.filter((fact) => fact.confirmed).length;
  return json(200, { facts: ordered(facts), counts: { total: facts.length, confirmed, unconfirmed: facts.length - confirmed, kinds } });
}

function update(facts: ApiFact[], id: number, body: { kind: string; text: string }): Response {
  const fact = facts.find((candidate) => candidate.fact_id === id);
  if (fact === undefined) {
    return notFound();
  }
  const text = body.text.split(/\s+/).filter(Boolean).join(" ");
  if (!KINDS.includes(body.kind)) {
    return problem("kind", `Невідомий вид факту: '${body.kind}'.`);
  }
  if (text === "") {
    return problem("text", "Факт не може бути порожнім.");
  }
  if (text.length > MAX_FACT) {
    return problem("text", `Факт задовгий: більше ${MAX_FACT} символів — розбий на кілька.`);
  }
  const same = facts.find((other) => other.fact_id !== id && fingerprint(other.text) === fingerprint(text));
  if (same !== undefined) {
    const message = `Такий факт уже є: #${same.fact_id}.`;
    return json(409, { code: "duplicate_fact", message, field_errors: [] });
  }
  Object.assign(fact, { kind: body.kind, text, confirmed: false, updated_at: new Date().toISOString() });
  return json(200, fact);
}

function create(facts: ApiFact[], body: { kind: string; text: string }): Response {
  const text = body.text.split(/\s+/).filter(Boolean).join(" ");
  if (!KINDS.includes(body.kind)) {
    return problem("kind", `Невідомий вид факту: '${body.kind}'.`);
  }
  if (text === "") {
    return problem("text", "Факт не може бути порожнім.");
  }
  if (text.length > MAX_FACT) {
    return problem("text", `Факт задовгий: більше ${MAX_FACT} символів — розбий на кілька.`);
  }
  const same = facts.find((other) => fingerprint(other.text) === fingerprint(text));
  if (same !== undefined) {
    return json(409, { code: "duplicate_fact", message: `Такий факт уже є: #${same.fact_id}.`, field_errors: [] });
  }
  const now = new Date().toISOString();
  const fact: ApiFact = { fact_id: Math.max(0, ...facts.map((other) => other.fact_id)) + 1, kind: body.kind, text, confirmed: true, source: "manual", job_id: null, created_at: now, updated_at: now };
  facts.push(fact);
  return json(201, fact);
}

export function factsBackend(initial: ApiFact[], cv: ApiCv | null = null): FactsBackend {
  const state: FactsBackend = {
    facts: structuredClone(initial),
    cv,
    requests: [],
    bodies: [],
    failNext(action, status = 500, body = { code: "internal_error", message: "Внутрішня помилка", field_errors: [] }) {
      queue.push({ action, status, body });
    },
    hold() {
      let release = () => {};
      held = new Promise<void>((resolve) => {
        release = resolve;
      });
      return { release };
    },
    fetchFn: undefined as unknown as typeof fetch,
  };
  let held: Promise<void> | null = null;
  const queue: { action: Action; status: number; body: unknown }[] = [];

  const failure = (action: Action): Response | null => {
    const index = queue.findIndex((item) => item.action === action);
    const item = index < 0 ? undefined : queue.splice(index, 1)[0];
    return item === undefined ? null : json(item.status, item.body);
  };

  state.fetchFn = (input, init) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url, "http://test");
    const method = init?.method ?? "GET";
    const path = url.pathname;
    if (method === "GET" && path === "/api/auth/me") {
      return Promise.resolve(MEANS_LOGGED_IN["GET /api/auth/me"]());
    }
    if (method === "GET" && path === "/api/jobs") {
      // Тести навігації з «Фактів» не дивляться на вакансії, але сторінка має де запитатись.
      return Promise.resolve(json(200, { items: [], sources: [] }));
    }
    if (!path.startsWith("/api/facts")) {
      return Promise.reject(new Error(`Непередбачений запит: ${method} ${path}`));
    }
    state.requests.push(`${method} ${path}`);
    const body: unknown = init?.body === undefined ? undefined : JSON.parse(String(init.body));
    if (body !== undefined) {
      state.bodies.push(body);
    }
    const respond = async (): Promise<Response> => {
      if (method === "GET" && path === "/api/facts") {
        if (held !== null) {
          await held;
        }
        return failure("list") ?? library(state.facts);
      }
      if (method === "GET" && path === "/api/facts/original-cv") {
        return failure("cv") ?? (state.cv === null ? notFound() : json(200, state.cv));
      }
      if (method === "POST" && path === "/api/facts/confirm") {
        const failed = failure("confirm");
        if (failed !== null) {
          return failed;
        }
        const { fact_ids } = body as { fact_ids: number[] };
        if (fact_ids.length === 0) {
          return problem("fact_ids", "Не вибрано жодного факту.");
        }
        const found = fact_ids.map((id) => state.facts.find((fact) => fact.fact_id === id));
        if (found.some((fact) => fact === undefined)) {
          return notFound();
        }
        const confirmed = (found as ApiFact[]).sort((a, b) => a.fact_id - b.fact_id);
        for (const fact of confirmed) {
          fact.confirmed = true;
        }
        return json(200, { facts: confirmed });
      }
      if (method === "POST" && path === "/api/facts") {
        return failure("create") ?? create(state.facts, body as { kind: string; text: string });
      }
      const one = /^\/api\/facts\/(\d+)$/.exec(path);
      if (method === "PUT" && one !== null) {
        return failure("update") ?? update(state.facts, Number(one[1]), body as { kind: string; text: string });
      }
      if (method === "DELETE" && one !== null) {
        const failed = failure("remove");
        if (failed !== null) {
          return failed;
        }
        const id = Number(one[1]);
        if (!state.facts.some((fact) => fact.fact_id === id)) {
          return notFound();
        }
        state.facts = state.facts.filter((fact) => fact.fact_id !== id);
        return noContent();
      }
      return Promise.reject(new Error(`Непередбачений запит: ${method} ${path}`));
    };
    return respond();
  };
  return state;
}
