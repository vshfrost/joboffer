import { VERDICTS, WORK_MODES, type TriageVerdict, type WorkMode } from "../../domain/analysis";
import { ACTIVE_STATUSES, type ApplicationStatus } from "../../domain/applications";
import { FRESHNESS_OPTIONS, NO_FILTERS, TABS, type JobFilters, type JobsTab } from "../../domain/jobs";

const FRESHNESS_VALUES: readonly string[] = FRESHNESS_OPTIONS.map((option) => option.value);

/** Фільтри з адреси; усе, що не розпізнано (зокрема старі `tab=all` і `closed`), — значення за замовчуванням. */
export function filtersFromParams(params: URLSearchParams): JobFilters {
  const tab = params.get("tab");
  const days = params.get("days") ?? "";
  const verdict = params.get("verdict");
  const mode = params.get("mode");
  const parsedTab = TABS.find((candidate): candidate is JobsTab => candidate === tab) ?? NO_FILTERS.tab;
  // Статус подачі є лише в табі «Подано» й лише з активних.
  const status = ACTIVE_STATUSES.find((candidate): candidate is ApplicationStatus => candidate === params.get("status"));
  return {
    tab: parsedTab,
    query: (params.get("q") ?? "").trim(),
    days: FRESHNESS_VALUES.includes(days) ? days : "",
    source: (params.get("source") ?? "").trim(),
    verdict: VERDICTS.find((candidate): candidate is TriageVerdict => candidate === verdict) ?? "",
    mode: WORK_MODES.find((candidate): candidate is WorkMode => candidate === mode) ?? "",
    status: parsedTab === "applied" && status !== undefined ? status : "",
  };
}

/** Адреса несе лише те, що відрізняється від значень за замовчуванням. */
export function paramsFromFilters(filters: JobFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.tab !== NO_FILTERS.tab) params.set("tab", filters.tab);
  if (filters.query !== "") params.set("q", filters.query);
  if (filters.days !== "") params.set("days", filters.days);
  if (filters.source !== "") params.set("source", filters.source);
  if (filters.verdict !== "") params.set("verdict", filters.verdict);
  if (filters.mode !== "") params.set("mode", filters.mode);
  if (filters.tab === "applied" && filters.status !== "") params.set("status", filters.status);
  return params;
}
