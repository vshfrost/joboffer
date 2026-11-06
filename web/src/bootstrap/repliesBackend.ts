/** Підроблений бекенд відповідей для тестів: `/api/replies` над станом у памʼяті, решта запитів — профіль (сесія). */
import { vi } from "vitest";

import { FULL_PROFILE, profileBackend, type ApiProfile } from "./profileBackend";
import { json } from "./testClient";

export interface ApiReplyJob {
  job_id: number;
  title: string | null;
  company: string | null;
  status: string | null;
}

export interface ApiReply {
  id: number;
  untrusted_from_address: string;
  untrusted_from_name: string;
  untrusted_subject: string;
  received_at: string;
  sender_auth: string;
  job: ApiReplyJob | null;
  confidence: string | null;
  matched_by: string | null;
  suggested_type: string;
  type: string | null;
  reviewed_at: string | null;
  manual_forward: { untrusted_from_address: string; untrusted_from_name: string; untrusted_subject: string } | null;
}

export interface ApiApplicationRef {
  job_id: number;
  title: string | null;
  company: string | null;
  status: string;
}

export const NORTHSTAR: ApiApplicationRef = { job_id: 104, title: "Senior Backend Engineer", company: "Northstar", status: "applied" };
export const LUMAPAY: ApiApplicationRef = { job_id: 108, title: "Senior Platform Engineer", company: "LumaPay", status: "replied" };

/** Лист зі збігом з подачею Northstar: черга «До розбору». */
export function apiReply(id: number, overrides: Partial<ApiReply> = {}): ApiReply {
  return {
    id,
    untrusted_from_address: "elena@northstar.example",
    untrusted_from_name: "Elena Talent",
    untrusted_subject: `Let's talk ${id}`,
    received_at: "2026-10-24T13:40:00Z",
    sender_auth: "verified",
    job: { job_id: 104, title: "Senior Backend Engineer", company: "Northstar", status: "applied" },
    confidence: "high",
    matched_by: "email",
    suggested_type: "invitation",
    type: null,
    reviewed_at: null,
    manual_forward: null,
    ...overrides,
  };
}

/** Лист без збігу: черга «Без вакансії». */
export function apiUnmatched(id: number, overrides: Partial<ApiReply> = {}): ApiReply {
  return apiReply(id, {
    untrusted_from_address: "jobs@unknown.example",
    untrusted_from_name: "Unknown Co",
    job: null,
    confidence: null,
    matched_by: null,
    suggested_type: "other",
    ...overrides,
  });
}

/** Розібраний лист: черга «Розібрані». */
export function apiReviewed(id: number, overrides: Partial<ApiReply> = {}): ApiReply {
  return apiReply(id, { type: "invitation", reviewed_at: "2026-10-25T09:00:00Z", ...overrides });
}

export function queueOf(reply: ApiReply): "matched" | "unmatched" | "reviewed" {
  return reply.reviewed_at !== null ? "reviewed" : reply.job !== null ? "matched" : "unmatched";
}

/** Своя відповідь; `undefined` (зараз чи після очікування) — звичайна. */
type Answer = Response | undefined | Promise<Response | undefined>;

export interface RepliesOverrides {
  /** Відповідь на `GET /api/replies?…`; `undefined` — звичайна (черга, пошук і сторінки над `replies`). */
  board?: (url: URL) => Answer;
  /** Відповідь на `GET /api/replies/<id>`; `undefined` — звичайна. */
  get?: (id: number) => Answer;
  /** Відповідь на `GET /api/replies/<id>/preview?…`; `undefined` — звичайна. */
  preview?: (id: number, url: URL) => Answer;
  /** Відповідь на `POST /api/replies/<id>/review`; `undefined` — звичайна (лист стає розібраним). */
  review?: (id: number, body: { type: string; job_id: number | null }) => Answer;
}

export interface RepliesBackend {
  fetchFn: typeof fetch;
  replies: ApiReply[];
  texts: Record<number, string>;
  applications: ApiApplicationRef[];
  /** Повні адреси всіх запитів черги. */
  boardUrls: string[];
  getIds: number[];
  /** Повні адреси всіх запитів превʼю. */
  previewUrls: string[];
  /** Усі тіла розбору, що дійшли до сервера. */
  reviews: { id: number; body: { type: string; job_id: number | null } }[];
}

const TARGETS: Record<string, string | null> = { auto_confirmation: null, rejection: "rejected", invitation: "interview", assignment: "interview", other: "replied" };

function answer(custom: Answer, fallback: () => Response): Promise<Response> {
  return Promise.resolve(custom).then((response) => response ?? fallback());
}

function defaultBoard(backend: RepliesBackend, url: URL): Response {
  const queue = url.searchParams.get("queue") ?? "matched";
  const needle = (url.searchParams.get("q") ?? "").toLowerCase();
  const size = Number(url.searchParams.get("per_page") ?? "20");
  const number = Number(url.searchParams.get("page") ?? "1");
  const counts = { matched: 0, unmatched: 0, reviewed: 0 };
  for (const reply of backend.replies) {
    counts[queueOf(reply)] += 1;
  }
  const matching = backend.replies.filter((reply) => {
    const text = [reply.untrusted_from_address, reply.untrusted_from_name, reply.untrusted_subject, reply.job?.company ?? "", backend.texts[reply.id] ?? ""];
    return queueOf(reply) === queue && text.some((part) => part.toLowerCase().includes(needle));
  });
  const offset = (number - 1) * size;
  const total = matching.length;
  return json(200, {
    queue,
    items: matching.slice(offset, offset + size),
    page: { number, size, total, first: offset + 1, last: Math.min(offset + size, total), has_newer: number > 1, has_older: offset + size < total },
    counts,
  });
}

function defaultPreview(backend: RepliesBackend, url: URL): Response {
  const type = url.searchParams.get("type") ?? "";
  const jobId = url.searchParams.get("job_id");
  const application = backend.applications.find((candidate) => String(candidate.job_id) === jobId);
  if (application === undefined) {
    return json(404, { code: "not_found" });
  }
  const after = TARGETS[type] ?? application.status;
  const status_after = after === null ? application.status : application.status === "applied" || application.status === "replied" ? after : application.status;
  return json(200, { job_id: application.job_id, current_status: application.status, status_after, changes: status_after !== application.status });
}

function defaultReview(backend: RepliesBackend, id: number, body: { type: string; job_id: number | null }): Response {
  const reply = backend.replies.find((candidate) => candidate.id === id);
  if (reply === undefined) {
    return json(404, { code: "not_found" });
  }
  if (!(body.type in TARGETS)) {
    return json(422, { code: "invalid_value", message: "Розбір не пройшов перевірку", field_errors: [{ field: "type", message: "Тип — один з: invitation, assignment, rejection, auto_confirmation, other." }] });
  }
  const application = body.job_id === null ? undefined : backend.applications.find((candidate) => candidate.job_id === body.job_id);
  if (body.job_id !== null && application === undefined) {
    return json(404, { code: "not_found" });
  }
  reply.type = body.type;
  reply.reviewed_at = "2026-10-26T10:00:00Z";
  reply.job = application === undefined ? null : { job_id: application.job_id, title: application.title, company: application.company, status: application.status };
  return json(200, { reply, application: null });
}

export function repliesBackend(
  replies: ApiReply[] = [],
  overrides: RepliesOverrides = {},
  extra: { texts?: Record<number, string>; applications?: ApiApplicationRef[] } = {},
  profile: ApiProfile = FULL_PROFILE,
): RepliesBackend {
  const rest = profileBackend(profile);
  const backend: RepliesBackend = {
    fetchFn: fetch,
    replies: structuredClone(replies),
    texts: structuredClone(extra.texts ?? {}),
    applications: structuredClone(extra.applications ?? [NORTHSTAR, LUMAPAY]),
    boardUrls: [],
    getIds: [],
    previewUrls: [],
    reviews: [],
  };
  backend.fetchFn = vi.fn<typeof fetch>((input, init) => {
    const raw = typeof input === "string" ? input : input instanceof URL ? input.pathname + input.search : input.url;
    const url = new URL(raw, "https://app.test");
    const method = init?.method ?? "GET";
    if (url.pathname === "/api/replies" && method === "GET") {
      backend.boardUrls.push(raw);
      return answer(overrides.board?.(url), () => defaultBoard(backend, url));
    }
    const preview = /^\/api\/replies\/(\d+)\/preview$/.exec(url.pathname);
    if (preview !== null && method === "GET") {
      const id = Number(preview[1]);
      backend.previewUrls.push(raw);
      return answer(overrides.preview?.(id, url), () => defaultPreview(backend, url));
    }
    const review = /^\/api\/replies\/(\d+)\/review$/.exec(url.pathname);
    if (review !== null && method === "POST") {
      const id = Number(review[1]);
      const body = JSON.parse(String(init?.body)) as { type: string; job_id: number | null };
      backend.reviews.push({ id, body });
      return answer(overrides.review?.(id, body), () => defaultReview(backend, id, body));
    }
    const detail = /^\/api\/replies\/(\d+)$/.exec(url.pathname);
    if (detail !== null && method === "GET") {
      const id = Number(detail[1]);
      backend.getIds.push(id);
      const reply = backend.replies.find((candidate) => candidate.id === id);
      return answer(overrides.get?.(id), () =>
        reply === undefined ? json(404, { code: "not_found" }) : json(200, { ...reply, untrusted_text: backend.texts[id] ?? "Hi Alex,\n\nCould we schedule a call?\n\nElena", applications: backend.applications }),
      );
    }
    return rest.fetchFn(input, init);
  });
  return backend;
}
