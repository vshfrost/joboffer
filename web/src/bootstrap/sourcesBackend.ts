/** Підроблений бекенд джерел для тестів: `/api/sources` над станом у памʼяті, решта запитів — профіль (сесія). Збігається з `app/infrastructure/http/sources.py`. */
import { vi } from "vitest";

import { FULL_PROFILE, profileBackend, type ApiProfile } from "./profileBackend";
import { json } from "./testClient";

export interface ApiRun {
  ran_at: string;
  found: number;
  imported: number;
  filtered: number;
  duplicate: number;
  completed: number;
  error: string | null;
}

export interface ApiCompany {
  id: string;
  platform: string;
  slug: string;
  name: string;
  enabled: boolean;
  last_run: ApiRun | null;
}

export interface ApiFeed {
  id: string;
  source: string;
  query: string;
  enabled: boolean;
  last_run: ApiRun | null;
}

export interface ApiRefresh {
  limit: number;
  remaining: number;
  next_at: string | null;
  last_run_at: string | null;
}

export interface ApiFilteredJob {
  number: number;
  title: string | null;
  company: string | null;
  reason: string;
}

/** UUID-подібний id за номером: стабільний у тестах. */
export function sourceId(n: number): string {
  return `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`;
}

/** Успішний прогін 2026-07-01 10:05 UTC (12:05 за Мадридом). */
export function apiRun(overrides: Partial<ApiRun> = {}): ApiRun {
  return { ran_at: "2026-07-01T10:05:00Z", found: 160, imported: 3, filtered: 146, duplicate: 10, completed: 1, error: null, ...overrides };
}

export function apiCompany(n: number, overrides: Partial<ApiCompany> = {}): ApiCompany {
  return { id: sourceId(n), platform: "greenhouse", slug: `company-${n}`, name: `Company ${n}`, enabled: true, last_run: apiRun(), ...overrides };
}

export function apiFeed(n: number, overrides: Partial<ApiFeed> = {}): ApiFeed {
  return { id: sourceId(n), source: "dou", query: "category=Python&remote", enabled: true, last_run: apiRun(), ...overrides };
}

export function apiFiltered(number: number, overrides: Partial<ApiFilteredJob> = {}): ApiFilteredJob {
  return { number, title: `Backend Engineer ${number}`, company: "Cedar", reason: "excluded", ...overrides };
}

export function apiRefresh(overrides: Partial<ApiRefresh> = {}): ApiRefresh {
  return { limit: 2, remaining: 2, next_at: null, last_run_at: "2026-07-01T10:05:00Z", ...overrides };
}

/** Тіло помилки сервера: `{code, message, field_errors, correlation_id}`. */
export function problem(status: number, code: string, message: string, fieldErrors: { field: string; message: string }[] = [], headers: Record<string, string> = {}): Response {
  return json(status, { code, message, field_errors: fieldErrors, correlation_id: "test-correlation" }, headers);
}

export interface SourcesOverrides {
  /** Відповідь на `GET /api/sources`; `undefined` — звичайна. */
  overview?: () => Response | Promise<Response> | undefined;
  /** Відповідь на `POST /api/sources/companies|feeds`; `undefined` — звичайна (перевірка як на сервері). */
  add?: (kind: "companies" | "feeds", body: Record<string, string>) => Response | Promise<Response> | undefined;
  /** Відповідь на `PATCH /api/sources/<companies|feeds>/<id>`; `undefined` — звичайна. */
  toggle?: (id: string, body: { enabled: boolean }) => Response | Promise<Response> | undefined;
  /** Відповідь на `DELETE /api/sources/<companies|feeds>/<id>`; `undefined` — звичайна. */
  remove?: (id: string) => Response | Promise<Response> | undefined;
  /** Відповідь на `POST /api/sources/refresh`; `undefined` — звичайна (ліміт зменшується). */
  refresh?: () => Response | Promise<Response> | undefined;
  /** Відповідь на `GET /api/sources/filtered`; `undefined` — звичайна. */
  filtered?: () => Response | Promise<Response> | undefined;
  /** Відповідь на `POST /api/sources/filtered/dismiss`; `undefined` — звичайна. */
  dismiss?: (numbers: number[]) => Response | Promise<Response> | undefined;
}

export interface SourcesBackend {
  fetchFn: typeof fetch;
  companies: ApiCompany[];
  feeds: ApiFeed[];
  refresh: ApiRefresh;
  filtered: ApiFilteredJob[];
  /** Усі запити до `/api/sources…` як «МЕТОД шлях». */
  requests: string[];
  /** Тіла POST/PATCH за шляхом. */
  bodies: Record<string, unknown[]>;
  /** Тіла дозволених `dismiss`. */
  dismissed: number[][];
  refreshRequests: number;
}

const SLUG = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;
const QUERY_PARAM = "[A-Za-z0-9_]{1,30}(?:=[A-Za-z0-9._+-]{1,50})?";
const QUERY = new RegExp(`^${QUERY_PARAM}(?:&${QUERY_PARAM}){0,5}$`);
const REQUIRED = { dou: "category", djinni: "primary_keyword" } as const;

function addCompany(backend: SourcesBackend, body: Record<string, string>): Response {
  const { platform = "", slug = "", name = "" } = body;
  if (!["greenhouse", "ashby", "lever"].includes(platform)) {
    return problem(422, "invalid_value", "Невідома платформа.", [{ field: "platform", message: "Невідома платформа." }]);
  }
  if (!SLUG.test(slug)) {
    const text = "Слаг компанії — літери, цифри, крапка, дефіс і підкреслення.";
    return problem(422, "invalid_value", text, [{ field: "slug", message: text }]);
  }
  if (backend.companies.some((company) => company.platform === platform && company.slug === slug)) {
    return problem(422, "invalid_value", "Така компанія вже є в списку.", [{ field: "slug", message: "Така компанія вже є в списку." }]);
  }
  if (slug === "missing-co") {
    const text = `Компанії зі слагом «${slug}» на ${platform} не знайдено.`;
    return problem(422, "invalid_value", text, [{ field: "slug", message: text }]);
  }
  if (slug === "slow-co") {
    const text = "Не вдалося перевірити слаг (timeout) — спробуй пізніше.";
    return problem(422, "invalid_value", text, [{ field: "slug", message: text }]);
  }
  const created: ApiCompany = { id: sourceId(100 + backend.companies.length), platform, slug, name: name.trim() === "" ? slug : name.trim(), enabled: true, last_run: null };
  backend.companies.push(created);
  return json(201, created);
}

function addFeed(backend: SourcesBackend, body: Record<string, string>): Response {
  const { source = "", query = "" } = body;
  if (source !== "dou" && source !== "djinni") {
    return problem(422, "invalid_value", "Невідоме джерело стрічки.", [{ field: "source", message: "Невідоме джерело стрічки." }]);
  }
  const fieldProblem = (text: string) => problem(422, "invalid_value", text, [{ field: "query", message: text }]);
  if (!QUERY.test(query)) {
    return fieldProblem("Параметри стрічки — name=value через &, без пробілів (напр. category=Python&remote).");
  }
  const params = Object.fromEntries(query.split("&").map((param) => param.split("=") as [string, string | undefined]));
  if (!params[REQUIRED[source]]) {
    return fieldProblem(`Для стрічки ${source} потрібен параметр ${REQUIRED[source]}=…`);
  }
  if (backend.feeds.some((feed) => feed.source === source && feed.query === query)) {
    return fieldProblem("Така стрічка вже є в списку.");
  }
  const created: ApiFeed = { id: sourceId(200 + backend.feeds.length), source, query, enabled: true, last_run: null };
  backend.feeds.push(created);
  return json(201, created);
}

function readBody(init: RequestInit | undefined): Record<string, string> {
  return JSON.parse(String(init?.body)) as Record<string, string>;
}

export function sourcesBackend(
  initial: { companies?: ApiCompany[]; feeds?: ApiFeed[]; refresh?: ApiRefresh; filtered?: ApiFilteredJob[] } = {},
  overrides: SourcesOverrides = {},
  profile: ApiProfile = FULL_PROFILE,
): SourcesBackend {
  const rest = profileBackend(profile);
  const backend: SourcesBackend = {
    fetchFn: fetch,
    companies: structuredClone(initial.companies ?? []),
    feeds: structuredClone(initial.feeds ?? []),
    refresh: structuredClone(initial.refresh ?? apiRefresh()),
    filtered: structuredClone(initial.filtered ?? []),
    requests: [],
    bodies: {},
    dismissed: [],
    refreshRequests: 0,
  };
  backend.fetchFn = vi.fn<typeof fetch>((input, init) => {
    const raw = typeof input === "string" ? input : input instanceof URL ? input.pathname + input.search : input.url;
    const url = new URL(raw, "https://app.test");
    const method = init?.method ?? "GET";
    if (!url.pathname.startsWith("/api/sources")) {
      return rest.fetchFn(input, init);
    }
    backend.requests.push(`${method} ${url.pathname}`);
    const record = (body: unknown) => (backend.bodies[`${method} ${url.pathname}`] ??= []).push(body);
    if (url.pathname === "/api/sources" && method === "GET") {
      return Promise.resolve(
        overrides.overview?.() ??
          json(200, { companies: backend.companies, feeds: backend.feeds, refresh: backend.refresh, filtered_out_count: backend.filtered.length }),
      );
    }
    if (url.pathname === "/api/sources/refresh" && method === "POST") {
      backend.refreshRequests += 1;
      const custom = overrides.refresh?.();
      if (custom !== undefined) {
        return Promise.resolve(custom);
      }
      if (backend.refresh.remaining === 0) {
        return Promise.resolve(
          problem(429, "refresh_limit", "Оновлення джерел уже запитано 2 рази за 30 хв — наступне о 12:25 (Мадрид).", [], { "Retry-After": "1500" }),
        );
      }
      const remaining = backend.refresh.remaining - 1;
      backend.refresh = { ...backend.refresh, remaining, next_at: remaining === 0 ? "2026-07-01T10:30:00Z" : null };
      return Promise.resolve(json(202, backend.refresh));
    }
    if (url.pathname === "/api/sources/filtered" && method === "GET") {
      return Promise.resolve(overrides.filtered?.() ?? json(200, backend.filtered));
    }
    if (url.pathname === "/api/sources/filtered/dismiss" && method === "POST") {
      const { numbers } = JSON.parse(String(init?.body)) as { numbers: number[] };
      record({ numbers });
      const custom = overrides.dismiss?.(numbers);
      if (custom !== undefined) {
        return Promise.resolve(custom);
      }
      if (numbers.length === 0) {
        return Promise.resolve(problem(422, "invalid_value", "Нема що ховати.", [{ field: "numbers", message: "Нема що ховати." }]));
      }
      const current = new Set(backend.filtered.map((job) => job.number));
      const stale = numbers.filter((number) => !current.has(number));
      if (stale.length > 0) {
        return Promise.resolve(problem(409, "filtered_changed", `Список змінився: вакансії ${stale.join(", ")} уже не в ньому. Онови список і перевір його ще раз.`));
      }
      backend.filtered = backend.filtered.filter((job) => !numbers.includes(job.number));
      backend.dismissed.push(numbers);
      return Promise.resolve(json(200, { dismissed: new Set(numbers).size }));
    }
    const add = /^\/api\/sources\/(companies|feeds)$/.exec(url.pathname);
    if (add !== null && method === "POST") {
      const kind = add[1] as "companies" | "feeds";
      const body = readBody(init);
      record(body);
      return Promise.resolve(overrides.add?.(kind, body) ?? (kind === "companies" ? addCompany(backend, body) : addFeed(backend, body)));
    }
    const one = /^\/api\/sources\/(companies|feeds)\/([^/]+)$/.exec(url.pathname);
    if (one !== null && (method === "PATCH" || method === "DELETE")) {
      const kind = one[1] as "companies" | "feeds";
      const id = one[2] ?? "";
      const list: (ApiCompany | ApiFeed)[] = kind === "companies" ? backend.companies : backend.feeds;
      const found = list.find((item) => item.id === id);
      if (method === "PATCH") {
        const body = JSON.parse(String(init?.body)) as { enabled: boolean };
        record(body);
        const custom = overrides.toggle?.(id, body);
        if (custom !== undefined) {
          return Promise.resolve(custom);
        }
        if (found === undefined) {
          return Promise.resolve(problem(404, "not_found", "Не знайдено"));
        }
        found.enabled = body.enabled;
        return Promise.resolve(json(200, found));
      }
      backend.bodies[`${method} ${url.pathname}`] = [];
      const custom = overrides.remove?.(id);
      if (custom !== undefined) {
        return Promise.resolve(custom);
      }
      if (found === undefined) {
        return Promise.resolve(problem(404, "not_found", "Не знайдено"));
      }
      list.splice(list.indexOf(found), 1);
      return Promise.resolve(new Response(null, { status: 204 }));
    }
    return Promise.reject(new Error(`Непередбачений запит: ${method} ${url.pathname}`));
  });
  return backend;
}
