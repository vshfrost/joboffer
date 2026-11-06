/** Тріаж і повний аналіз вакансії: що клієнт знає про них і як їх показує. */

export const VERDICTS = ["analyse", "maybe", "skip"] as const;
export type TriageVerdict = (typeof VERDICTS)[number];
/** Хто оцінив: агент через MCP чи сервер за ключовими словами. */
export const TRIAGE_SOURCES = ["agent", "rules"] as const;
export type TriageSource = (typeof TRIAGE_SOURCES)[number];
export const TRIAGE_SOURCE_NOTES: Record<TriageSource, string> = {
  agent: "Оцінив агент за профілем, підтвердженими фактами й вимогами з опису.",
  rules: "Оцінив сервер за тими самими правилами — за ключовими словами, без агента.",
};

export const VERDICT_LABELS: Record<TriageVerdict, string> = { analyse: "Аналізувати", maybe: "Можливо", skip: "Пропустити" };

export const WORK_MODES = ["remote", "hybrid", "onsite"] as const;
export type WorkMode = (typeof WORK_MODES)[number];

export const WORK_MODE_LABELS: Record<WorkMode, string> = { remote: "Remote", hybrid: "Hybrid", onsite: "Onsite" };

export const SENIORITIES = ["junior", "middle", "senior", "lead", "principal"] as const;
export type Seniority = (typeof SENIORITIES)[number];

export const SENIORITY_LABELS: Record<Seniority, string> = {
  junior: "Junior",
  middle: "Middle",
  senior: "Senior",
  lead: "Lead",
  principal: "Principal",
};

export const GAP_STATUSES = ["open", "closed", "no_experience"] as const;
export type GapStatus = (typeof GAP_STATUSES)[number];

export const GAP_STATUS_LABELS: Record<GapStatus, string> = { open: "Відкрита", closed: "Закрита фактами", no_experience: "Нема досвіду" };

/** Прогалина аналізу з відповіддю користувача: закрита фактами (їхні номери), «нема досвіду» чи ще відкрита. */
export interface Gap {
  number: number;
  gap: string;
  /** Питання до користувача; `null` у аналізах старого формату. */
  question: string | null;
  status: GapStatus;
  /** Номери фактів, що закривають прогалину; порожньо, коли вона не закрита фактами. */
  factIds: number[];
}

/** Швидкий тріаж: окремий від повного аналізу результат за початком опису. */
export interface Triage {
  score: number;
  verdict: TriageVerdict;
  reason: string;
  /** Момент тріажу, ISO 8601. */
  triagedAt: string;
  source: TriageSource;
}

/** Повний аналіз із flags (знімок фільтрів профілю на момент збереження) і знаком застарілості. */
export interface JobAnalysis {
  id: number;
  score: number;
  summary: string;
  mustHave: string[];
  niceToHave: string[];
  keywords: string[];
  seniority: Seniority | null;
  workMode: WorkMode | null;
  location: string | null;
  languages: string[];
  salaryMinEur: number | null;
  salaryMaxEur: number | null;
  relocation: boolean | null;
  reasons: string[];
  gaps: Gap[];
  filtersPassed: boolean;
  flags: string[];
  updatedAt: string;
  /** З якого моменту профіль змінено після аналізу; `null` — аналіз актуальний. */
  staleSince: string | null;
}

export const NOT_STATED = "не вказано";

/** «Не оцінено» лише коли оцінки нема; 0 — валідна оцінка. */
export function scoreText(score: number | null): string {
  return score === null ? "Не оцінено" : `${score}%`;
}

const AMOUNT = new Intl.NumberFormat("uk-UA");

/** Вилка зарплати з аналізу; чого вакансія не сказала — «не вказано», а не нуль. */
export function salaryText(min: number | null, max: number | null): string {
  if (min !== null && max !== null) {
    return min === max ? `${AMOUNT.format(min)} EUR на рік` : `${AMOUNT.format(min)}–${AMOUNT.format(max)} EUR на рік`;
  }
  if (max !== null) {
    return `до ${AMOUNT.format(max)} EUR на рік`;
  }
  if (min !== null) {
    return `від ${AMOUNT.format(min)} EUR на рік`;
  }
  return NOT_STATED;
}

export function relocationText(relocation: boolean | null): string {
  if (relocation === null) {
    return NOT_STATED;
  }
  return relocation ? "Допомога з переїздом є" : "Допомоги з переїздом нема";
}
