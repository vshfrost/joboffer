/** Джерела вакансій: компанії на ATS і RSS-стрічки, їхні прогони, «Оновити зараз» і вакансії, що вже не проходять фільтр. */

import { madridDay, madridTime } from "./mail";

export type SourceKind = "company" | "feed";
/** Вкладка сторінки: компанії або RSS-стрічки. */
export type SourcesTab = "companies" | "feeds";
/** Фільтр стану; порожній — «Усі». */
export type StateFilter = "" | "enabled" | "error" | "disabled";
export type SourceState = "ok" | "error" | "pending" | "disabled";
export type CompanyPlatform = "greenhouse" | "ashby" | "lever";
export type FeedSource = "dou" | "djinni";
export type FailureCode = "timeout" | "not_found" | "rate_limited" | "unavailable" | "rejected" | "invalid" | "unsupported";
export type FilteredReason = "title" | "excluded" | "format" | "location";

export interface LastRun {
  /** ISO-момент. */
  ranAt: string;
  found: number;
  imported: number;
  filtered: number;
  duplicate: number;
  completed: number;
  error: FailureCode | null;
}

/** Джерело в списку: для компанії `key` — слаг, для стрічки — параметри запиту. */
export interface Source {
  kind: SourceKind;
  id: string;
  /** Код платформи (`greenhouse`) або стрічки (`dou`). */
  platform: string;
  name: string;
  key: string;
  enabled: boolean;
  lastRun: LastRun | null;
}

export interface RefreshState {
  limit: number;
  remaining: number;
  /** ISO-момент, коли звільниться наступний запит; `null` — запити є. */
  nextAt: string | null;
  /** ISO-момент найпізнішого прогону джерел; `null` — прогонів ще не було. */
  lastRunAt: string | null;
}

export interface SourcesOverview {
  companies: Source[];
  feeds: Source[];
  refresh: RefreshState;
  filteredOutCount: number;
}

export interface FilteredJob {
  number: number;
  title: string | null;
  company: string | null;
  reason: FilteredReason;
}

export type NewSource =
  | { kind: "company"; platform: CompanyPlatform; slug: string; name: string }
  | { kind: "feed"; source: FeedSource; query: string };

/** Що показує сторінка: усе живе в адресі. `open` — id розгорнутого джерела. */
export interface SourcesQuery {
  tab: SourcesTab;
  q: string;
  status: StateFilter;
  open: string;
}

export const SOURCES_TABS: readonly SourcesTab[] = ["companies", "feeds"];
export const STATE_FILTERS: readonly StateFilter[] = ["", "enabled", "error", "disabled"];
export const COMPANY_PLATFORMS: readonly CompanyPlatform[] = ["greenhouse", "ashby", "lever"];
export const FEED_SOURCES: readonly FeedSource[] = ["dou", "djinni"];
export const FAILURE_CODES: readonly FailureCode[] = ["timeout", "not_found", "rate_limited", "unavailable", "rejected", "invalid", "unsupported"];
export const FILTERED_REASONS: readonly FilteredReason[] = ["title", "excluded", "format", "location"];

export const STATE_LABELS: Record<SourceState, string> = {
  ok: "Працює",
  error: "Помилка",
  pending: "Ще не оновлювалось",
  disabled: "Вимкнено",
};

export const STATE_FILTER_LABELS: Record<StateFilter, string> = {
  "": "Усі",
  enabled: "Увімкнені",
  error: "З помилками",
  disabled: "Вимкнені",
};

export const PLATFORM_LABELS: Record<string, string> = {
  greenhouse: "Greenhouse",
  ashby: "Ashby",
  lever: "Lever",
  dou: "DOU",
  djinni: "Djinni",
};

/** Код збою прогону → текст для людини. */
export const FAILURE_TEXT: Record<FailureCode, string> = {
  timeout: "Перевищено час очікування",
  not_found: "Джерело не знайдено на платформі",
  rate_limited: "Платформа обмежила кількість запитів",
  unavailable: "Платформа тимчасово недоступна",
  rejected: "Платформа відхилила запит",
  invalid: "Відповідь платформи не вдалося розібрати",
  unsupported: "Цей вид джерела поки не підтримується",
};

export const FILTERED_REASON_TEXT: Record<FilteredReason, string> = {
  title: "Назва не збігається з ціллю профілю",
  excluded: "Виключений рівень у назві",
  format: "Формат роботи не відповідає профілю",
  location: "Локація не відповідає профілю",
};

const PLURALS = new Intl.PluralRules("uk");
const SOURCE_NOUNS: Record<SourcesTab, readonly [string, string, string]> = {
  companies: ["компанія", "компанії", "компаній"],
  feeds: ["стрічка", "стрічки", "стрічок"],
};

/** Адреса сторінки → що показувати; усе нерозпізнане стає значенням за замовчуванням. */
export function parseSourcesQuery(params: URLSearchParams): SourcesQuery {
  return {
    tab: SOURCES_TABS.find((tab) => tab === params.get("tab")) ?? "companies",
    q: (params.get("q") ?? "").trim(),
    status: STATE_FILTERS.find((status) => status === params.get("status")) ?? "",
    open: (params.get("open") ?? "").trim(),
  };
}

/** Запит → параметри адреси сторінки (значення за замовчуванням не пишуться). */
export function sourcesQueryParams(query: SourcesQuery): URLSearchParams {
  const params = new URLSearchParams();
  if (query.tab !== "companies") {
    params.set("tab", query.tab);
  }
  if (query.q !== "") {
    params.set("q", query.q);
  }
  if (query.status !== "") {
    params.set("status", query.status);
  }
  if (query.open !== "") {
    params.set("open", query.open);
  }
  return params;
}

/** Чи є щось, що «Скинути фільтри» скине: пошук або стан. */
export function hasSourceFilters(query: SourcesQuery): boolean {
  return query.q !== "" || query.status !== "";
}

/** Стан для бейджа: вимкнене — завжди «Вимкнено», далі помилка прогону, далі «ще не оновлювалось». */
export function sourceState(source: Source): SourceState {
  if (!source.enabled) {
    return "disabled";
  }
  if (source.lastRun === null) {
    return "pending";
  }
  return source.lastRun.error === null ? "ok" : "error";
}

/** Джерела вкладки за пошуком (назва, слаг чи параметри, платформа) і станом. */
export function visibleSources(sources: readonly Source[], query: SourcesQuery): Source[] {
  const needle = query.q.toLowerCase();
  return sources.filter((source) => {
    const haystack = `${source.name} ${source.key} ${source.platform} ${platformLabel(source.platform)}`.toLowerCase();
    if (!haystack.includes(needle)) {
      return false;
    }
    return query.status === "" || (query.status === "enabled" ? source.enabled : query.status === "disabled" ? !source.enabled : sourceState(source) === "error");
  });
}

export function platformLabel(platform: string): string {
  return PLATFORM_LABELS[platform] ?? platform;
}

/** Стрічка не має назви на сервері: «DOU · category=Python&remote». */
export function feedName(source: FeedSource, query: string): string {
  return `${platformLabel(source)} · ${query}`;
}

/** Скільки імпортовано останнім прогоном; без прогону й після помилки — «—». */
export function importedText(source: Source): string {
  return source.lastRun === null || source.lastRun.error !== null ? "—" : String(source.lastRun.imported);
}

/** Форма слова для числа: [1, 21…; 2–4, 22…; решта]. */
export function plural(count: number, forms: readonly [string, string, string]): string {
  const category = PLURALS.select(count);
  return category === "one" ? forms[0] : category === "few" ? forms[1] : forms[2];
}

/** «5 компаній», «1 стрічка». */
export function sourceCountText(tab: SourcesTab, count: number): string {
  return `${count} ${plural(count, SOURCE_NOUNS[tab])}`;
}

/** Заголовок банера «Уже не проходять фільтр». */
export function bannerTitle(count: number): string {
  const verb = plural(count, ["вже не проходить", "вже не проходять", "вже не проходять"]);
  return `${count} ${plural(count, ["вакансія", "вакансії", "вакансій"])} ${verb} фільтр профілю`;
}

/** Заголовок підтвердження приховування. */
export function hideTitle(count: number): string {
  return `Приховати ${count} ${plural(count, ["вакансію", "вакансії", "вакансій"])}?`;
}

/** «1/2 ручних запитів за 30 хв». */
export function quotaText(refresh: RefreshState): string {
  return `${refresh.remaining}/${refresh.limit} ручних запитів за 30 хв`;
}

/** «2026-10-26 · 13:15» за часом Мадрида. */
export function stampText(iso: string): string {
  return `${madridDay(iso)} · ${madridTime(iso)}`;
}

/** ISO-момент через `retryAfterSeconds` після `nowMs`: коли звільниться запит після 429. */
export function nextRequestAt(nowMs: number, retryAfterSeconds: number): string {
  return new Date(nowMs + retryAfterSeconds * 1000).toISOString();
}

/** Огляд, у якому джерело замінено оновленим (за видом і id). */
export function replaceSource(overview: SourcesOverview, source: Source): SourcesOverview {
  const swap = (sources: Source[]) => sources.map((item) => (item.id === source.id ? source : item));
  return source.kind === "company" ? { ...overview, companies: swap(overview.companies) } : { ...overview, feeds: swap(overview.feeds) };
}

/** Огляд без джерела. */
export function withoutSource(overview: SourcesOverview, source: Pick<Source, "kind" | "id">): SourcesOverview {
  const keep = (sources: Source[]) => sources.filter((item) => item.id !== source.id);
  return source.kind === "company" ? { ...overview, companies: keep(overview.companies) } : { ...overview, feeds: keep(overview.feeds) };
}

/** Вид джерела для підпису в деталях. */
export const KIND_TEXT: Record<SourceKind, string> = { company: "Сторінка компанії", feed: "RSS-стрічка" };
