/** Підроблений бекенд пошти для тестів: `/api/mail` над станом у памʼяті, решта запитів — профіль (хаб його вантажить). */
import { vi } from "vitest";

import { FULL_PROFILE, profileBackend, type ApiProfile } from "./profileBackend";
import { json } from "./testClient";

export interface ApiMailRow {
  id: number;
  dropped: boolean;
  untrusted_from_address: string;
  untrusted_from_name: string;
  untrusted_subject: string;
  received_at: string;
  category: string | null;
  sender_auth: string | null;
  reason: string | null;
}

export function apiMail(id: number, overrides: Partial<ApiMailRow> = {}): ApiMailRow {
  return {
    id,
    dropped: false,
    untrusted_from_address: "talent@acme.example",
    untrusted_from_name: "María López",
    untrusted_subject: `Re: next steps ${id}`,
    received_at: "2026-10-24T13:45:00Z",
    category: "company",
    sender_auth: "verified",
    reason: null,
    ...overrides,
  };
}

export function apiDropped(id: number, overrides: Partial<ApiMailRow> = {}): ApiMailRow {
  return apiMail(id, {
    dropped: true,
    untrusted_from_name: "",
    untrusted_from_address: "spam@flood.example",
    untrusted_subject: "Win a prize",
    category: null,
    sender_auth: null,
    reason: "daily_limit",
    ...overrides,
  });
}

export interface ApiForwarding {
  code: string;
  link_only: boolean;
  untrusted_requested_by: string;
  received_at: string;
  current: boolean;
}

export type ApiDetail = ApiMailRow & { untrusted_text: string; forwarding: ApiForwarding | null };

export function apiDetail(row: ApiMailRow, overrides: Partial<ApiDetail> = {}): ApiDetail {
  return { ...row, untrusted_text: "Hi Taras,\n\nCould we schedule a call this week?\n\nBest,\nMaría", forwarding: null, ...overrides };
}

export interface ApiSettings {
  address: string;
  rotated_at: string | null;
  synced_at: string | null;
  sync_failed: boolean;
  sync_error: string;
  manual: { limit: number; remaining: number; next_at: string | null };
}

export function apiSettings(overrides: Partial<ApiSettings> = {}): ApiSettings {
  return {
    address: "mailroom+abcdefghijkl@example.com",
    rotated_at: null,
    synced_at: "2026-10-24T13:45:00Z",
    sync_failed: false,
    sync_error: "",
    manual: { limit: 2, remaining: 2, next_at: null },
    ...overrides,
  };
}

const KIND_CATEGORIES: Record<string, string[]> = {
  company: ["company"],
  linkedin_alert: ["linkedin_alert"],
  linkedin_message: ["linkedin_message", "linkedin_application"],
  forwarding_confirmation: ["forwarding_confirmation"],
  other: ["other", "suspicious"],
};

export interface MailOverrides {
  /** Відповідь на `GET /api/mail?…`; `undefined` — звичайна (фільтр і сторінки над `rows`). */
  list?: (url: URL) => Response | Promise<Response> | undefined;
  /** Відповідь на `GET /api/mail/<id>`; `undefined` — звичайна. */
  get?: (id: number) => Response | Promise<Response> | undefined;
  /** Відповідь на `GET /api/mail/settings`; `undefined` — звичайна. */
  settings?: () => Response | Promise<Response> | undefined;
  /** Відповідь на `POST /api/mail/sync`; `undefined` — звичайна (лічильник зменшується). */
  sync?: () => Response | Promise<Response> | undefined;
  /** Відповідь на `POST /api/mail/address/rotate`; `undefined` — звичайна (адреса змінюється). */
  rotate?: () => Response | Promise<Response> | undefined;
}

export interface MailBackend {
  fetchFn: typeof fetch;
  rows: ApiMailRow[];
  details: Record<number, ApiDetail>;
  settings: ApiSettings;
  /** Повні адреси всіх запитів списку. */
  listUrls: string[];
  /** Номери листів, які відкривали. */
  getIds: number[];
  syncRequests: number;
  rotateRequests: number;
}

/** Відповідь за замовчуванням: фільтр за видом і підрядком, сторінки — як на сервері. */
function defaultList(backend: MailBackend, url: URL): Response {
  const kind = url.searchParams.get("kind") ?? "";
  const needle = (url.searchParams.get("q") ?? "").toLowerCase();
  const size = Number(url.searchParams.get("per_page") ?? "20");
  const number = Number(url.searchParams.get("page") ?? "1");
  const matching = backend.rows.filter((row) => {
    const kindOk = kind === "" ? true : kind === "dropped" ? row.dropped : !row.dropped && (KIND_CATEGORIES[kind] ?? []).includes(row.category ?? "");
    const text = [row.untrusted_from_address, row.untrusted_from_name, row.untrusted_subject, row.dropped ? "" : (backend.details[row.id]?.untrusted_text ?? "")];
    return kindOk && text.some((part) => part.toLowerCase().includes(needle));
  });
  const offset = (number - 1) * size;
  const items = matching.slice(offset, offset + size);
  const total = matching.length;
  return json(200, {
    items,
    page: { number, size, total, first: offset + 1, last: Math.min(offset + size, total), has_newer: number > 1, has_older: offset + size < total },
  });
}

export function mailBackend(
  rows: ApiMailRow[] = [],
  overrides: MailOverrides = {},
  extra: { details?: Record<number, ApiDetail>; settings?: ApiSettings } = {},
  profile: ApiProfile = FULL_PROFILE,
): MailBackend {
  const rest = profileBackend(profile);
  const backend: MailBackend = {
    fetchFn: fetch,
    rows: structuredClone(rows),
    details: structuredClone(extra.details ?? {}),
    settings: structuredClone(extra.settings ?? apiSettings()),
    listUrls: [],
    getIds: [],
    syncRequests: 0,
    rotateRequests: 0,
  };
  backend.fetchFn = vi.fn<typeof fetch>((input, init) => {
    const raw = typeof input === "string" ? input : input instanceof URL ? input.pathname + input.search : input.url;
    const url = new URL(raw, "https://app.test");
    const method = init?.method ?? "GET";
    if (url.pathname === "/api/mail" && method === "GET") {
      backend.listUrls.push(raw);
      return Promise.resolve(overrides.list?.(url) ?? defaultList(backend, url));
    }
    if (url.pathname === "/api/mail/settings" && method === "GET") {
      return Promise.resolve(overrides.settings?.() ?? json(200, backend.settings));
    }
    if (url.pathname === "/api/mail/sync" && method === "POST") {
      backend.syncRequests += 1;
      const custom = overrides.sync?.();
      if (custom !== undefined) {
        return Promise.resolve(custom);
      }
      const remaining = Math.max(0, backend.settings.manual.remaining - 1);
      backend.settings = { ...backend.settings, manual: { ...backend.settings.manual, remaining, next_at: remaining === 0 ? "2026-10-24T14:30:00Z" : null } };
      return Promise.resolve(json(200, backend.settings.manual));
    }
    if (url.pathname === "/api/mail/address/rotate" && method === "POST") {
      backend.rotateRequests += 1;
      const custom = overrides.rotate?.();
      if (custom !== undefined) {
        return Promise.resolve(custom);
      }
      backend.settings = { ...backend.settings, address: "mailroom+zyxwvutsrqpo@example.com", rotated_at: "2026-10-24T15:00:00Z" };
      return Promise.resolve(json(200, backend.settings));
    }
    const detail = /^\/api\/mail\/(\d+)$/.exec(url.pathname);
    if (detail !== null && method === "GET") {
      const id = Number(detail[1]);
      backend.getIds.push(id);
      const found = backend.details[id];
      const row = backend.rows.find((candidate) => candidate.id === id);
      return Promise.resolve(overrides.get?.(id) ?? (found !== undefined ? json(200, found) : row !== undefined ? json(200, apiDetail(row)) : json(404, { code: "not_found" })));
    }
    return rest.fetchFn(input, init);
  });
  return backend;
}
