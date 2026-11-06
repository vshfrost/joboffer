import { plural } from "./profileSummary";

/** Факти: що клієнт знає про факт і фільтри бібліотеки. `id` — номер у межах користувача (як `fact_id` в API). */

/** Порядок = порядок секцій у списку (як на сервері). */
export const FACT_KINDS = ["experience", "achievement", "project", "skill", "education", "language"] as const;
export type FactKind = (typeof FACT_KINDS)[number];

export const KIND_LABELS: Record<FactKind, string> = {
  experience: "Досвід",
  achievement: "Досягнення",
  project: "Проєкти",
  skill: "Скіли",
  education: "Освіта",
  language: "Мови",
};

/** Звідки взявся факт: розбір CV, розмова з Claude у чаті чи додано вручну. */
export const SOURCES = ["cv", "chat", "manual"] as const;
export type FactSource = (typeof SOURCES)[number];

export const SOURCE_LABELS: Record<FactSource, string> = {
  cv: "з CV",
  chat: "з чату",
  manual: "вручну",
};

export const STATUSES = ["all", "pending", "confirmed"] as const;
export type StatusFilter = (typeof STATUSES)[number];

export const STATUS_LABELS: Record<StatusFilter, string> = {
  all: "Усі",
  pending: "Потребують перевірки",
  confirmed: "Підтверджені",
};

export interface Fact {
  id: number;
  kind: FactKind;
  text: string;
  /** Тільки підтверджені факти потрапляють у CV. */
  confirmed: boolean;
  source: FactSource;
  /** Номер вакансії користувача, з якої факт зʼявився в чаті; інакше `null`. */
  jobId: number | null;
  createdAt: string;
  updatedAt: string;
}

/** Оригінал CV: текст, який Claude прочитав з файлу. */
export interface OriginalCv {
  fileName: string | null;
  text: string;
  /** Момент збереження, ISO 8601. */
  savedAt: string;
}

/** Чернетка факту: те, що йде в `PUT /facts/{id}` і `POST /facts`. */
export interface FactDraft {
  kind: FactKind;
  text: string;
}

/** Фільтри бібліотеки; `kind: null` — усі категорії. */
export interface FactFilters {
  query: string;
  status: StatusFilter;
  kind: FactKind | null;
  /** `null` чи відсутнє — усі джерела. */
  source?: FactSource | null | undefined;
}

export const NO_FILTERS: FactFilters = { query: "", status: "all", kind: null, source: null };

export interface KindCount {
  kind: FactKind;
  total: number;
  pending: number;
}

export interface FactCounts {
  total: number;
  confirmed: number;
  pending: number;
  kinds: KindCount[];
}

export function hasActiveFilters(filters: FactFilters): boolean {
  return filters.query.trim() !== "" || filters.status !== "all" || filters.kind !== null || (filters.source ?? null) !== null;
}

const collapse = (text: string) => text.split(/\s+/).filter(Boolean).join(" ").toLowerCase();

/** Факти, що проходять усі фільтри разом. Порядок вхідного списку зберігається. */
export function filterFacts(facts: readonly Fact[], filters: FactFilters): Fact[] {
  const query = collapse(filters.query);
  // «12» і «#12» — це ID: шукаємо саме номер, а не всі тексти з цією цифрою (які теж знайдуться за текстом).
  const idMatch = /^#?(\d+)$/.exec(query);
  const id = idMatch === null ? null : Number(idMatch[1]);
  return facts.filter(
    (fact) =>
      (filters.kind === null || fact.kind === filters.kind) &&
      ((filters.source ?? null) === null || fact.source === filters.source) &&
      (filters.status === "all" || (filters.status === "confirmed") === fact.confirmed) &&
      (query === "" || fact.id === id || collapse(fact.text).includes(query)),
  );
}

/** Лічильники за всіма фактами (без фільтрів): точні після будь-якої локальної зміни. */
export function countFacts(facts: readonly Fact[]): FactCounts {
  const pending = facts.filter((fact) => !fact.confirmed).length;
  return {
    total: facts.length,
    confirmed: facts.length - pending,
    pending,
    kinds: FACT_KINDS.map((kind) => {
      const own = facts.filter((fact) => fact.kind === kind);
      return { kind, total: own.length, pending: own.filter((fact) => !fact.confirmed).length };
    }),
  };
}

/** Чи змінилась чернетка відносно факту: пробіли по краях не рахуються. */
export function isDraftChanged(fact: Fact, draft: FactDraft): boolean {
  return draft.kind !== fact.kind || draft.text.trim() !== fact.text;
}

/** «2 факти потребують перевірки» з правильною формою слів. */
export function pendingSummary(pending: number): string {
  return `${pending} ${plural(pending, "факт потребує", "факти потребують", "фактів потребують")} перевірки`;
}
