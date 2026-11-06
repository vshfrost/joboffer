/** Підроблений бекенд вакансій для тестів: `/api/jobs…` над станом у памʼяті, фільтри як на сервері. */

import { json, MEANS_LOGGED_IN, noContent } from "./testClient";

export interface ApiTriage {
  score: number;
  verdict: "analyse" | "maybe" | "skip";
  reason: string;
  triaged_at: string;
  source: "agent" | "rules";
}

/** Аналіз у відповіді `GET /api/jobs/{id}/analysis`. */
export interface ApiAnalysis {
  job_id: number;
  score: number;
  summary: string;
  must_have: string[];
  nice_to_have: string[];
  keywords: string[];
  seniority: "junior" | "middle" | "senior" | "lead" | "principal" | null;
  work_mode: "remote" | "hybrid" | "onsite" | null;
  location: string | null;
  languages: string[];
  salary_min_eur: number | null;
  salary_max_eur: number | null;
  relocation: boolean | null;
  reasons: string[];
  gaps: { number: number; gap: string; question: string | null; status: "open" | "closed" | "no_experience"; fact_ids: number[] }[];
  filters_passed: boolean;
  flags: string[];
  updated_at: string;
  stale_since: string | null;
}

export function apiAnalysis(job_id: number, overrides: Partial<ApiAnalysis> = {}): ApiAnalysis {
  const flags = overrides.flags ?? [];
  return {
    job_id,
    score: 78,
    summary: "Бекенд-роль на Python у платіжній команді.",
    must_have: ["Python", "PostgreSQL"],
    nice_to_have: ["Подієва архітектура"],
    keywords: ["Python", "FastAPI"],
    seniority: "senior",
    work_mode: "remote",
    location: "Іспанія",
    languages: ["English"],
    salary_min_eur: 60000,
    salary_max_eur: 80000,
    relocation: false,
    reasons: ["Основний стек збігається з профілем", "Формат роботи відповідає цілі"],
    gaps: [{ number: 1, gap: "Kubernetes у production", question: "Чи працювали з Kubernetes у production? Де і скільки?", status: "open", fact_ids: [] }],
    filters_passed: flags.length === 0,
    flags,
    updated_at: "2026-10-22T09:00:00Z",
    stale_since: null,
    ...overrides,
  };
}

/** Звіт у відповіді `GET /api/jobs/{id}/documents`. */
export interface ApiLint {
  passed: boolean;
  pages: number;
  issues: { code: string; message: string }[];
  keywords: { covered: string[]; missing: string[]; percent: number } | null;
}

export function apiLint(overrides: Partial<ApiLint> = {}): ApiLint {
  const issues = overrides.issues ?? [];
  return {
    passed: issues.length === 0,
    pages: 2,
    issues,
    keywords: { covered: ["Python", "FastAPI", "PostgreSQL"], missing: ["Kubernetes", "Kafka"], percent: 60 },
    ...overrides,
  };
}

/** Версія документа у відповіді `GET /api/jobs/{id}/documents`. */
export interface ApiDocument {
  document_id: number;
  job_id: number;
  kind: "cv" | "cl";
  version: number;
  created_at: string;
  file_name: string;
  pdf_available: boolean;
  /** Номер фото в шапці CV; `null` — без фото (листи фото не мають). */
  photo_id: number | null;
  lint: ApiLint | null;
}

export function apiDocument(document_id: number, kind: "cv" | "cl", version: number, overrides: Partial<ApiDocument> = {}): ApiDocument {
  return {
    document_id,
    job_id: 1,
    kind,
    version,
    created_at: "2026-10-22T09:40:00Z",
    file_name: kind === "cv" ? "Alex_Example_CV.pdf" : "Alex_Example_Cover_Letter.pdf",
    pdf_available: true,
    photo_id: null,
    lint: apiLint(),
    ...overrides,
  };
}

export function apiTriage(overrides: Partial<ApiTriage> = {}): ApiTriage {
  return { score: 86, verdict: "analyse", reason: "Senior Python, remote: стек збігається з профілем", triaged_at: "2026-10-21T09:00:00Z", source: "agent", ...overrides };
}

export interface ApiJob {
  job_id: number;
  source: string;
  url: string | null;
  title: string | null;
  company: string | null;
  location: string | null;
  text: string | null;
  created_at: string;
  needs_text: boolean;
  dismissed_at: string | null;
  dismiss_reason: string | null;
  triage: ApiTriage | null;
  /** Вакансія з джерела, яку ще не відкривали (як `is_new` в API). */
  is_new: boolean;
}

export function daysAgo(days: number, now = Date.now()): string {
  return new Date(now - days * 86_400_000).toISOString();
}

export function apiJob(job_id: number, overrides: Partial<ApiJob> = {}): ApiJob {
  const text = overrides.text === undefined ? `Опис вакансії ${job_id}` : overrides.text;
  return {
    job_id,
    source: "manual",
    url: null,
    title: `Посада ${job_id}`,
    company: `Компанія ${job_id}`,
    location: null,
    text,
    created_at: "2026-10-20T10:00:00Z",
    needs_text: text === null,
    dismissed_at: null,
    dismiss_reason: null,
    triage: null,
    is_new: false,
    ...overrides,
  };
}

/** Подача у відповіді `GET /api/jobs/{id}/application`. */
export interface ApiApplication {
  job_id: number;
  status: "applied" | "replied" | "interview" | "offer" | "rejected" | "withdrawn";
  applied_on: string;
  channel: "email" | "ats" | "linkedin" | "referral";
  ats: "greenhouse" | "lever" | "ashby" | "workable" | "smartrecruiters" | "other" | null;
  company_domains: string[];
  company_emails: string[];
  status_changed_at: string;
  allowed_transitions: ApiApplication["status"][];
}

/** Матриця переходів сервера (v1): статус → куди можна. */
const MOVES: Record<ApiApplication["status"], ApiApplication["status"][]> = {
  applied: ["replied", "interview", "offer", "rejected", "withdrawn"],
  replied: ["interview", "offer", "rejected", "withdrawn"],
  interview: ["offer", "rejected", "withdrawn"],
  offer: ["withdrawn"],
  rejected: [],
  withdrawn: [],
};
const ACTIVE = ["applied", "replied", "interview", "offer"];
const CLOSED = ["rejected", "withdrawn"];

export function apiApplication(job_id: number, overrides: Partial<ApiApplication> = {}): ApiApplication {
  const status = overrides.status ?? "applied";
  return {
    job_id,
    status,
    applied_on: "2026-10-20",
    channel: "email",
    ats: null,
    company_domains: [],
    company_emails: [],
    status_changed_at: "2026-10-20T10:00:00Z",
    allowed_transitions: MOVES[status],
    ...overrides,
  };
}

/** Керування збоями: скільки найближчих відповідей на дію зробити помилкою 500. */
export interface Failures {
  list: number;
  get: number;
  analysis: number;
  dismiss: number;
  restore: number;
  add: number;
  application: number;
  saveApplication: number;
  move: number;
}

/** Лічильники табів у відповіді списку (`counts` в API); тест задає їх напряму: вони не залежать від списку. */
export interface ApiCounts {
  in_progress: number;
  applied_unreviewed: number;
  needs_text: boolean;
}

export interface JobsBackend {
  fetchFn: typeof fetch;
  jobs: ApiJob[];
  /** Номери вакансій з іншими взаємодіями (interview kit, тема підготовки, факт) — крім аналізу й документів. */
  interactions: number[];
  /** Що сервер віддає в `counts` кожного списку. */
  counts: ApiCounts;
  analyses: ApiAnalysis[];
  documents: ApiDocument[];
  applications: ApiApplication[];
  failures: Failures;
  /** Статуси найближчих відповідей на список документів (500, 401, 403, 404): кожен запит бере наступний. */
  documentStatuses: number[];
  /** Рядки «МЕТОД /шлях?запит» усіх запитів до `/api/jobs…` у порядку надходження. */
  requests: string[];
  /** Тіла POST-запитів у порядку надходження. */
  bodies: unknown[];
  /** Затримує відповіді списку, вакансії й додавання, доки не викличуть `release()` (стан завантаження). */
  hold(): { release(): void };
  /** Затримує лише відповіді аналізу: вакансія вже завантажена, аналіз ще ні. */
  holdAnalysis(): { release(): void };
  /** Затримує лише відповіді списку документів (стан завантаження блоку). */
  holdDocuments(): { release(): void };
  /** Затримує відповіді на читання, збереження й перехід подачі (pending, подвійний submit, завантаження блоку). */
  holdApplication(): { release(): void };
}

const SERVER_ERROR = () => json(500, { code: "internal_error", message: "Внутрішня помилка", field_errors: [] });

function matches(job: ApiJob, query: string): boolean {
  const needle = query.toLowerCase();
  return [job.title, job.company, job.text].some((value) => (value ?? "").toLowerCase().includes(needle));
}

interface NewJobBody {
  text: string;
  url: string;
  title: string;
  company: string;
}

const fingerprint = (text: string | null) => (text ?? "").split(/\s+/).filter(Boolean).join(" ").toLowerCase();
const LINKEDIN = /linkedin\.com\/(?:comm\/)?jobs\/view\/(?:[^/?#\s]*?-)?(\d{6,})/i;

/** Додавання як на сервері (спрощено): 422 з текстами v1, дубль за текстом чи URL, дописування тексту в «потрібен текст». */
function addResponse(jobs: ApiJob[], body: NewJobBody): Response {
  const errors: { field: string; message: string }[] = [];
  if (body.text.trim() === "") {
    errors.push({ field: "text", message: "Встав текст опису вакансії." });
  }
  if (body.url.trim() !== "" && !/^https?:\/\/\S+$/i.test(body.url.trim())) {
    errors.push({ field: "url", message: "Посилання має починатися з http:// або https://." });
  }
  if (errors.length > 0) {
    return json(422, { code: "invalid_fields", message: errors.map((error) => error.message).join(" "), field_errors: errors });
  }
  const linkedin = LINKEDIN.exec(body.url)?.[1];
  const url = body.url.trim() === "" ? null : linkedin === undefined ? body.url.trim() : `https://www.linkedin.com/jobs/view/${linkedin}`;
  const outcome = (job_id: number, kind: string, status: number) => json(status, { job_id, duplicate: kind === "duplicate", outcome: kind });
  const waiting = url === null ? undefined : jobs.find((job) => job.text === null && job.url === url);
  const sameText = jobs.find((job) => job.text !== null && fingerprint(job.text) === fingerprint(body.text));
  if (waiting !== undefined) {
    if (sameText !== undefined) {
      return outcome(sameText.job_id, "duplicate", 200);
    }
    waiting.text = body.text.trim();
    waiting.needs_text = false;
    return outcome(waiting.job_id, "text_added", 200);
  }
  const existing = sameText ?? (url === null ? undefined : jobs.find((job) => job.url === url));
  if (existing !== undefined) {
    return outcome(existing.job_id, "duplicate", 200);
  }
  const job_id = Math.max(0, ...jobs.map((job) => job.job_id)) + 1;
  jobs.push({
    job_id,
    source: "manual",
    url,
    title: body.title.trim() === "" ? null : body.title.trim(),
    company: body.company.trim() === "" ? null : body.company.trim(),
    location: null,
    text: body.text.trim(),
    created_at: new Date().toISOString(),
    needs_text: false,
    dismissed_at: null,
    dismiss_reason: null,
    triage: null,
    is_new: false,
  });
  return outcome(job_id, "created", 201);
}

const VERDICT_RANK = { analyse: 0, maybe: 1, skip: 2 } as const;

/** Список як на сервері: фільтри; без тексту — наприкінці; проаналізовані першими (фільтри, скор); далі тріаж; далі новіші. */
const STAGES = ["open", "in_progress", "applied"];

/** Етап вакансії для табів вебу, як на сервері: відкрита / у процесі / подана; поза етапами — відмова. */
function stageOf(job: ApiJob, state: JobsBackend): "open" | "in_progress" | "applied" | null {
  const status = state.applications.find((application) => application.job_id === job.job_id)?.status ?? null;
  if (status === "rejected") {
    return null;
  }
  if (status === "withdrawn") {
    return "in_progress";
  }
  if (status !== null) {
    return "applied";
  }
  const touched =
    state.analyses.some((analysis) => analysis.job_id === job.job_id) ||
    state.documents.some((document) => document.job_id === job.job_id) ||
    state.interactions.includes(job.job_id);
  if (touched) {
    return "in_progress";
  }
  return job.text === null ? null : "open";
}

function listResponse(state: JobsBackend, params: URLSearchParams): Response {
  const { jobs, analyses, applications } = state;
  const stage = params.get("stage") ?? "";
  if (stage !== "" && !STAGES.includes(stage)) {
    return json(422, {
      code: "invalid_fields",
      message: "Етап — один з: open, in_progress, applied.",
      field_errors: [{ field: "stage", message: "Етап — один з: open, in_progress, applied." }],
    });
  }
  const query = params.get("query") ?? "";
  const days = params.get("days") ?? "";
  const source = params.get("source") ?? "";
  const needsText = params.get("needs_text") === "true";
  const dismissed = params.get("dismissed") === "true";
  const verdict = params.get("triage_verdict") ?? "";
  const workMode = params.get("work_mode") ?? "";
  const statusParam = params.get("status") ?? "";
  const statuses = statusParam === "active" ? ACTIVE : statusParam === "closed" ? CLOSED : statusParam === "" ? null : [statusParam];
  const limit = Number(params.get("limit") ?? "50");
  const since = days === "" ? null : Date.now() - Number(days) * 86_400_000;
  const analysisOf = (job: ApiJob) => analyses.find((analysis) => analysis.job_id === job.job_id);
  const statusOf = (job: ApiJob) => applications.find((application) => application.job_id === job.job_id)?.status ?? null;
  const items = jobs
    .filter((job) => (job.dismissed_at !== null) === dismissed)
    // Веб-список не показує відмови ні в одному табі, навіть за пошуком.
    .filter((job) => statusOf(job) !== "rejected")
    .filter((job) => stage === "" || stageOf(job, state) === stage)
    .filter((job) => query === "" || matches(job, query))
    .filter((job) => since === null || Date.parse(job.created_at) >= since)
    .filter((job) => source === "" || job.source === source)
    .filter((job) => !needsText || job.text === null)
    .filter((job) => verdict === "" || job.triage?.verdict === verdict)
    .filter((job) => workMode === "" || analysisOf(job)?.work_mode === workMode)
    .filter((job) => statuses === null || statuses.includes(statusOf(job) ?? ""))
    .sort((a, b) => {
      const x = analysisOf(a);
      const y = analysisOf(b);
      return (
        Number(a.text === null) - Number(b.text === null) ||
        Number(x === undefined) - Number(y === undefined) ||
        Number(y?.filters_passed ?? false) - Number(x?.filters_passed ?? false) ||
        (y?.score ?? 0) - (x?.score ?? 0) ||
        (a.triage === null ? 3 : VERDICT_RANK[a.triage.verdict]) - (b.triage === null ? 3 : VERDICT_RANK[b.triage.verdict]) ||
        (b.triage?.score ?? -1) - (a.triage?.score ?? -1) ||
        Date.parse(b.created_at) - Date.parse(a.created_at) ||
        b.job_id - a.job_id
      );
    })
    .slice(0, limit)
    .map((job) => {
      const analysis = analysisOf(job);
      return {
        job_id: job.job_id,
        source: job.source,
        url: job.url,
        title: job.title,
        company: job.company,
        created_at: job.created_at,
        needs_text: job.needs_text,
        dismissed: job.dismissed_at !== null,
        score: analysis?.score ?? null,
        filters_passed: analysis?.filters_passed ?? null,
        work_mode: analysis?.work_mode ?? null,
        triage_score: job.triage?.score ?? null,
        triage_verdict: job.triage?.verdict ?? null,
        triage_reason: job.triage?.reason ?? null,
        status: statusOf(job),
        is_new: job.is_new,
      };
    });
  return json(200, { items, sources: [...new Set(jobs.map((job) => job.source))].sort(), counts: state.counts });
}

export function jobsBackend(initial: ApiJob[], analyses: ApiAnalysis[] = [], documents: ApiDocument[] = [], applications: ApiApplication[] = []): JobsBackend {
  const state: JobsBackend = {
    jobs: structuredClone(initial),
    interactions: [],
    counts: { in_progress: 0, applied_unreviewed: 0, needs_text: false },
    analyses: structuredClone(analyses),
    documents: structuredClone(documents),
    applications: structuredClone(applications),
    documentStatuses: [],
    failures: { list: 0, get: 0, analysis: 0, dismiss: 0, restore: 0, add: 0, application: 0, saveApplication: 0, move: 0 },
    requests: [],
    bodies: [],
    hold() {
      let release = () => {};
      held = new Promise<void>((resolve) => {
        release = resolve;
      });
      return { release };
    },
    holdAnalysis() {
      let release = () => {};
      heldAnalysis = new Promise<void>((resolve) => {
        release = resolve;
      });
      return { release };
    },
    holdDocuments() {
      let release = () => {};
      heldDocuments = new Promise<void>((resolve) => {
        release = resolve;
      });
      return { release };
    },
    holdApplication() {
      let release = () => {};
      heldApplication = new Promise<void>((resolve) => {
        release = resolve;
      });
      return { release };
    },
    fetchFn: undefined as unknown as typeof fetch,
  };
  let held: Promise<void> | null = null;
  let heldApplication: Promise<void> | null = null;
  let heldAnalysis: Promise<void> | null = null;
  let heldDocuments: Promise<void> | null = null;

  const fail = (action: keyof Failures): boolean => {
    if (state.failures[action] > 0) {
      state.failures[action] -= 1;
      return true;
    }
    return false;
  };

  const notFound = () => json(404, { code: "not_found", message: "Не знайдено", field_errors: [] });
  const invalid = (...errors: [string, string][]) =>
    json(422, { code: "invalid_fields", message: errors.map(([, message]) => message).join(" "), field_errors: errors.map(([field, message]) => ({ field, message })) });

  /** Подача як на сервері (спрощено): PUT створює чи замінює деталі, статус лишається; перехід — за матрицею. */
  const applicationResponse = async (jobId: number, statusRoute: boolean, method: string, init: RequestInit | undefined): Promise<Response> => {
    if (heldApplication !== null) {
      await heldApplication;
    }
    const current = state.applications.find((application) => application.job_id === jobId);
    if (!statusRoute && method === "GET") {
      if (fail("application")) {
        return SERVER_ERROR();
      }
      return current === undefined ? notFound() : json(200, current);
    }
    if (!state.jobs.some((job) => job.job_id === jobId)) {
      return notFound();
    }
    if (!statusRoute && method === "PUT") {
      if (fail("saveApplication")) {
        return SERVER_ERROR();
      }
      const body = JSON.parse(String(init?.body)) as { channel: string; applied_on: string; ats: string; company_domains: string[]; company_emails: string[] };
      const errors: [string, string][] = [];
      if (body.applied_on !== "" && !/^\d{4}-\d{2}-\d{2}$/.test(body.applied_on)) {
        errors.push(["applied_on", "Дата подачі — у форматі YYYY-MM-DD."]);
      } else if (body.applied_on > new Date(Date.now() + 86_400_000).toISOString().slice(0, 10)) {
        errors.push(["applied_on", "Дата подачі не може бути в майбутньому."]);
      }
      if (!["email", "ats", "linkedin", "referral"].includes(body.channel)) {
        errors.push(["channel", "Канал — один з: email, ats, linkedin, referral."]);
      }
      if (body.ats !== "" && !["greenhouse", "lever", "ashby", "workable", "smartrecruiters", "other"].includes(body.ats)) {
        errors.push(["ats", "ATS — один з: greenhouse, lever, ashby, workable, smartrecruiters, other."]);
      }
      const badDomain = body.company_domains.find((domain) => !/^[a-z0-9.-]+\.[a-z]{2,}$/i.test(domain));
      if (badDomain !== undefined) {
        errors.push(["company_domains", `Некоректний домен компанії: ${badDomain}.`]);
      }
      const badEmail = body.company_emails.find((email) => !/^\S+@\S+\.\S+$/.test(email));
      if (badEmail !== undefined) {
        errors.push(["company_emails", `Некоректна адреса компанії: ${badEmail}.`]);
      }
      if (errors.length > 0) {
        return invalid(...errors);
      }
      const saved = apiApplication(jobId, {
        status: current?.status ?? "applied",
        applied_on: body.applied_on === "" ? new Date().toISOString().slice(0, 10) : body.applied_on,
        channel: body.channel as ApiApplication["channel"],
        ats: body.ats === "" ? null : (body.ats as ApiApplication["ats"]),
        company_domains: body.company_domains.map((domain) => domain.toLowerCase()),
        company_emails: body.company_emails.map((email) => email.toLowerCase()),
        status_changed_at: current?.status_changed_at ?? new Date().toISOString(),
      });
      state.applications = [...state.applications.filter((application) => application.job_id !== jobId), saved];
      return json(200, saved);
    }
    if (statusRoute && method === "POST") {
      if (current === undefined) {
        return notFound();
      }
      if (fail("move")) {
        return SERVER_ERROR();
      }
      const { status } = JSON.parse(String(init?.body)) as { status: ApiApplication["status"] };
      if (!(status in MOVES)) {
        return invalid(["status", "Статус — один з: applied, replied, interview, offer, rejected, withdrawn."]);
      }
      if (status === current.status) {
        return json(200, current);
      }
      if (!current.allowed_transitions.includes(status)) {
        return invalid(["status", MOVES[current.status].length === 0 ? `Подачу вже закрито (${current.status}): статус більше не змінюється.` : `Статус ${current.status} → ${status} неможливий: він рухається лише вперед.`]);
      }
      const moved = apiApplication(jobId, { ...current, status, allowed_transitions: MOVES[status], status_changed_at: new Date().toISOString() });
      state.applications = state.applications.map((application) => (application.job_id === jobId ? moved : application));
      return json(200, moved);
    }
    return Promise.reject(new Error(`Непередбачений запит: ${method} /api/jobs/${jobId}/application`));
  };

  state.fetchFn = (input, init) => {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url, "http://test");
    const method = init?.method ?? "GET";
    const path = url.pathname;
    if (method === "GET" && path === "/api/auth/me") {
      return Promise.resolve(MEANS_LOGGED_IN["GET /api/auth/me"]());
    }
    // Блоки «Підготовка» і «Пакет до інтерв'ю» в деталях: без підготовки в цьому бекенді — порожня підготовка й пакета нема (їхні тести: jobBlocksHarness).
    const prepBlock = /^\/api\/jobs\/\d+\/(prep|interview-kit)$/.exec(path);
    if (method === "GET" && prepBlock !== null) {
      return Promise.resolve(prepBlock[1] === "prep" ? json(200, { readiness: null, topics: [] }) : json(404, { code: "not_found", message: "Не знайдено", field_errors: [] }));
    }
    if (!path.startsWith("/api/jobs")) {
      return Promise.reject(new Error(`Непередбачений запит: ${method} ${path}`));
    }
    state.requests.push(`${method} ${path}${url.search}`);
    if (init?.body !== undefined) {
      state.bodies.push(JSON.parse(String(init.body)));
    }
    const respond = async (): Promise<Response> => {
      if (method === "GET" && path === "/api/jobs") {
        if (held !== null) {
          await held;
        }
        return fail("list") ? SERVER_ERROR() : listResponse(state, url.searchParams);
      }
      if (method === "POST" && path === "/api/jobs") {
        if (held !== null) {
          await held;
        }
        return fail("add") ? SERVER_ERROR() : addResponse(state.jobs, JSON.parse(String(init?.body)) as NewJobBody);
      }
      if (method === "POST" && path === "/api/jobs/dismiss") {
        if (fail("dismiss")) {
          return SERVER_ERROR();
        }
        const body = JSON.parse(String(init?.body)) as { job_ids: number[]; reason: string };
        if (body.reason.trim() === "") {
          return json(422, {
            code: "invalid_value",
            message: "Вкажи причину приховування.",
            field_errors: [{ field: "reason", message: "Вкажи причину приховування." }],
          });
        }
        for (const [index, id] of body.job_ids.entries()) {
          if (state.applications.some((application) => application.job_id === id)) {
            const where = body.job_ids.length > 1 ? `Елемент ${index + 1}: на` : "На";
            return json(409, {
              code: "job_has_application",
              message: `${where} вакансію ${id} уже є подача — поданих вакансій не ховають.`,
              field_errors: [],
            });
          }
        }
        for (const id of body.job_ids) {
          const job = state.jobs.find((candidate) => candidate.job_id === id);
          if (job !== undefined && job.dismissed_at === null) {
            job.dismissed_at = new Date().toISOString();
            job.dismiss_reason = body.reason;
          }
        }
        return noContent();
      }
      const restore = /^\/api\/jobs\/(\d+)\/restore$/.exec(path);
      if (method === "POST" && restore !== null) {
        const job = state.jobs.find((candidate) => candidate.job_id === Number(restore[1]));
        if (job === undefined) {
          return json(404, { code: "not_found", message: "Не знайдено", field_errors: [] });
        }
        if (fail("restore")) {
          return SERVER_ERROR();
        }
        job.dismissed_at = null;
        job.dismiss_reason = null;
        return noContent();
      }
      const analysis = /^\/api\/jobs\/(\d+)\/analysis$/.exec(path);
      if (method === "GET" && analysis !== null) {
        if (held !== null) {
          await held;
        }
        if (heldAnalysis !== null) {
          await heldAnalysis;
        }
        if (fail("analysis")) {
          return SERVER_ERROR();
        }
        const found = state.analyses.find((candidate) => candidate.job_id === Number(analysis[1]));
        return found === undefined ? json(404, { code: "not_found", message: "Не знайдено", field_errors: [] }) : json(200, found);
      }
      const applicationRoute = /^\/api\/jobs\/(\d+)\/application(\/status)?$/.exec(path);
      if (applicationRoute !== null) {
        return applicationResponse(Number(applicationRoute[1]), applicationRoute[2] !== undefined, method, init);
      }
      const listed = /^\/api\/jobs\/(\d+)\/documents$/.exec(path);
      if (method === "GET" && listed !== null) {
        if (heldDocuments !== null) {
          await heldDocuments;
        }
        const status = state.documentStatuses.shift();
        if (status !== undefined) {
          return json(status, { code: "failed", message: "Не вдалося", field_errors: [] });
        }
        const items = state.documents.filter((candidate) => candidate.job_id === Number(listed[1]));
        return json(200, { items });
      }
      const one = /^\/api\/jobs\/(\d+)$/.exec(path);
      if (method === "GET" && one !== null) {
        if (held !== null) {
          await held;
        }
        if (fail("get")) {
          return SERVER_ERROR();
        }
        const job = state.jobs.find((candidate) => candidate.job_id === Number(one[1]));
        return job === undefined ? json(404, { code: "not_found", message: "Не знайдено", field_errors: [] }) : json(200, job);
      }
      return Promise.reject(new Error(`Непередбачений запит: ${method} ${path}`));
    };
    return respond();
  };
  return state;
}
