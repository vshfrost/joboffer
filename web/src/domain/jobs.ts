import { VERDICT_LABELS, WORK_MODE_LABELS, type Triage, type TriageVerdict, type WorkMode } from "./analysis";
import { STATUS_LABELS, type ApplicationStatus } from "./applications";

/** Вакансії: що клієнт знає про вакансію й фільтри списку. `id` — номер у межах користувача (як `job_id` в API). */

/** Таби за етапом вакансії; перший — за замовчуванням, невідоме значення в адресі веде на нього. */
export const TABS = ["open", "in-progress", "applied", "needs-text", "dismissed"] as const;
export type JobsTab = (typeof TABS)[number];

export const TAB_LABELS: Record<JobsTab, string> = {
  open: "Відкриті вакансії",
  "in-progress": "У процесі",
  applied: "Подано",
  "needs-text": "Потрібен текст",
  dismissed: "Сховані",
};

/** Свіжість: «додано за останні N днів»; порожньо — будь-коли. */
export const FRESHNESS_OPTIONS = [
  { value: "", label: "Будь-коли" },
  { value: "1", label: "За добу" },
  { value: "7", label: "За тиждень" },
  { value: "30", label: "За місяць" },
] as const;

/** Причина за замовчуванням, коли вакансію ховає кнопка «Не цікаво» (як у v1). */
export const DEFAULT_DISMISS_REASON = "не цікаво";

/** Скільки вакансій просить список; стільки ж — максимум сервера. */
export const LIST_LIMIT = 200;

export interface JobSummary {
  id: number;
  source: string;
  url: string | null;
  title: string | null;
  company: string | null;
  /** Момент додавання, ISO 8601. */
  createdAt: string;
  /** «Потрібен текст»: вакансія з листа-алерту, опису ще нема. Стан даних, не статус. */
  needsText: boolean;
  dismissed: boolean;
  /** Повний аналіз: `null` — вакансію ще не аналізовано (0 — валідна оцінка). */
  score: number | null;
  filtersPassed: boolean | null;
  workMode: WorkMode | null;
  /** Швидкий тріаж — окремо від аналізу. */
  triageScore: number | null;
  triageVerdict: TriageVerdict | null;
  triageReason: string | null;
  /** Статус подачі; `null` — на вакансію не подавались. */
  status: ApplicationStatus | null;
  /** Вакансія з джерела (`ats:` / `rss:`), яку ще не відкривали: у списку має позначку «нове». */
  isNew: boolean;
}

export interface Job {
  id: number;
  source: string;
  url: string | null;
  title: string | null;
  company: string | null;
  location: string | null;
  /** Текст третьої сторони — лише як текст, ніколи як HTML. `null` — потрібен текст. */
  text: string | null;
  createdAt: string;
  needsText: boolean;
  dismissedAt: string | null;
  dismissReason: string | null;
  triage: Triage | null;
}

/** Лічильники табів із сервера: не залежать від фільтрів і від ліміту списку. */
export interface JobTabCounts {
  /** Скільки вакансій у «У процесі». */
  inProgress: number;
  /** Скільки вакансій мають нерозібраний лист до активної подачі: лічильник на «Подано». */
  appliedUnreviewed: number;
  /** Є вакансія без тексту: «!» на «Потрібен текст». */
  needsText: boolean;
}

export const NO_TAB_COUNTS: JobTabCounts = { inProgress: 0, appliedUnreviewed: 0, needsText: false };

export interface JobList {
  items: JobSummary[];
  /** Різні джерела вакансій користувача — для фільтра. */
  sources: string[];
  counts: JobTabCounts;
}

/** Фільтри списку, як вони лежать в адресі. */
export interface JobFilters {
  tab: JobsTab;
  query: string;
  days: string;
  source: string;
  /** Вердикт тріажу; порожньо — будь-який. */
  verdict: "" | TriageVerdict;
  /** Формат з повного аналізу; порожньо — будь-який. */
  mode: "" | WorkMode;
  /** Статус активної подачі (лише в табі «Подано»); порожньо — будь-який. */
  status: "" | ApplicationStatus;
}

/** Етап вакансії в запиті до сервера; порожньо — без етапу (таби «Потрібен текст» і «Сховані»). */
export type JobStage = "" | "open" | "in_progress" | "applied";

/** Що просить список у сервера. */
export interface JobsQuery {
  query: string;
  days: string;
  source: string;
  needsText: boolean;
  dismissed: boolean;
  triageVerdict: string;
  workMode: string;
  /** Статус активної подачі; порожньо — будь-який. */
  status: string;
  stage: JobStage;
  limit: number;
}

/** Поля форми «Додати вакансію»: усі рядки, правила й тексти помилок — на сервері. */
export interface NewJobInput {
  text: string;
  url: string;
  title: string;
  company: string;
}

export const NO_NEW_JOB: NewJobInput = { text: "", url: "", title: "", company: "" };

/** Чим закінчилося додавання: нова вакансія, дубль наявної чи дописаний текст у вакансію з алерту. */
export const ADD_OUTCOMES = ["created", "duplicate", "text_added"] as const;
export type AddOutcome = (typeof ADD_OUTCOMES)[number];

export interface AddedJob {
  id: number;
  outcome: AddOutcome;
}

export const ADD_NOTICES: Record<AddOutcome, string> = {
  created: "Вакансію додано",
  duplicate: "Така вакансія вже є",
  text_added: "Текст додано у вакансію з алерту",
};

export const NO_FILTERS: JobFilters = { tab: "open", query: "", days: "", source: "", verdict: "", mode: "", status: "" };

const STAGES: Record<JobsTab, JobStage> = { open: "open", "in-progress": "in_progress", applied: "applied", "needs-text": "", dismissed: "" };

export function jobsQuery(filters: JobFilters): JobsQuery {
  return {
    query: filters.query,
    days: filters.days,
    source: filters.source,
    needsText: filters.tab === "needs-text",
    dismissed: filters.tab === "dismissed",
    triageVerdict: filters.verdict,
    workMode: filters.mode,
    status: filters.tab === "applied" ? filters.status : "",
    stage: STAGES[filters.tab],
    limit: LIST_LIMIT,
  };
}

/** Умова фільтра для чипа й лічильника на кнопці «Фільтри»: група й підпис значення. */
export interface FilterCondition {
  key: "days" | "source" | "status" | "verdict" | "mode";
  group: string;
  value: string;
}

/** Умови з панелі «Фільтри». Пошук і таб умовами не є. */
export function filterConditions(filters: JobFilters): FilterCondition[] {
  const conditions: FilterCondition[] = [];
  for (const option of FRESHNESS_OPTIONS) {
    if (option.value === filters.days && option.value !== "") {
      conditions.push({ key: "days", group: "Свіжість", value: option.label });
    }
  }
  if (filters.source !== "") {
    conditions.push({ key: "source", group: "Джерело", value: filters.source });
  }
  if (filters.status !== "") {
    conditions.push({ key: "status", group: "Статус подачі", value: STATUS_LABELS[filters.status] });
  }
  if (filters.verdict !== "") {
    conditions.push({ key: "verdict", group: "Вердикт тріажу", value: VERDICT_LABELS[filters.verdict] });
  }
  if (filters.mode !== "") {
    conditions.push({ key: "mode", group: "Формат", value: WORK_MODE_LABELS[filters.mode] });
  }
  return conditions;
}

/** Чи щось, крім таба, звужує список (пошук теж). */
export function hasActiveFilters(filters: JobFilters): boolean {
  return filters.query !== "" || filterConditions(filters).length > 0;
}

export function jobTitle(job: { title: string | null }): string {
  return job.title ?? "Без назви";
}

/** День додавання за Мадридом («YYYY-MM-DD»), як у відповідях MCP. */
export function madridDay(iso: string): string {
  return new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Madrid" }).format(new Date(iso));
}

/** Номер вакансії з адреси: лише ціле від 1 (без знаків, нулів попереду й порожнього). */
export function parseJobNumber(raw: string | undefined): number | null {
  if (raw === undefined || !/^[1-9][0-9]*$/.test(raw)) {
    return null;
  }
  const value = Number(raw);
  return Number.isSafeInteger(value) ? value : null;
}
