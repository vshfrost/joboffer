/** Документи вакансії: CV і cover letter, їхні версії та ATS-звіт. `id` — номер документа в межах користувача. */

export const DOCUMENT_KINDS = ["cv", "cl"] as const;
export type DocumentKind = (typeof DOCUMENT_KINDS)[number];

export const KIND_LABELS: Record<DocumentKind, string> = { cv: "CV", cl: "Cover letter" };

export interface LintIssue {
  code: string;
  message: string;
}

/** Ключові слова з аналізу вакансії: що є в тексті PDF, чого нема, відсоток від сервера. */
export interface KeywordCoverage {
  covered: string[];
  missing: string[];
  percent: number;
}

/** ATS-звіт на момент збереження версії. `passed` = нема issues; покриття ключових слів на нього не впливає. */
export interface LintReport {
  passed: boolean;
  pages: number;
  issues: LintIssue[];
  /** `null` — вакансію не аналізовано, покриття не рахувалося. */
  keywords: KeywordCoverage | null;
}

export interface JobDocument {
  id: number;
  jobId: number;
  kind: DocumentKind;
  /** Версії CV і листа однієї вакансії нумеруються окремо. */
  version: number;
  /** Момент збереження, ISO 8601. */
  createdAt: string;
  fileName: string;
  /** `false` — файл PDF цієї версії зник: посилання не показуємо й іншу версію не підставляємо. */
  pdfAvailable: boolean;
  /** Номер фото в шапці CV; `null` — без фото (листи фото не мають). */
  photoId: number | null;
  /** `null` — версія без звіту (це не «пройдено» і не нулі). */
  lint: LintReport | null;
}

export interface DocumentsOfKind {
  /** Остання збережена версія (не «відправлена»); `null` — документа цього виду ще нема. */
  latest: JobDocument | null;
  /** Попередні версії, новіші першими. */
  history: JobDocument[];
}

export type AtsStatus = "no-report" | "passed" | "issues";

export function splitByKind(documents: readonly JobDocument[]): Record<DocumentKind, DocumentsOfKind> {
  const ofKind = (kind: DocumentKind): DocumentsOfKind => {
    // Остання — версія з найбільшим номером свого виду, а не перша у відповіді.
    const [latest = null, ...history] = documents.filter((item) => item.kind === kind).sort((a, b) => b.version - a.version);
    return { latest, history };
  };
  return { cv: ofKind("cv"), cl: ofKind("cl") };
}

export function atsStatus(lint: LintReport | null): AtsStatus {
  if (lint === null) {
    return "no-report";
  }
  return lint.passed ? "passed" : "issues";
}

/** «зауваження» за правилами української множини: 1, 2–4, 5–20, 21… */
export function issuesText(count: number): string {
  const lastTwo = count % 100;
  const last = count % 10;
  const few = last >= 1 && last <= 4 && (lastTwo < 11 || lastTwo > 14);
  return `${count} ${few ? "зауваження" : "зауважень"}`;
}

export function atsBadge(lint: LintReport | null): { tone: "neutral" | "success" | "warning"; text: string } {
  if (lint === null) {
    return { tone: "neutral", text: "ATS: немає звіту" };
  }
  if (lint.passed) {
    return { tone: "success", text: "✓ ATS: перевірку пройдено" };
  }
  return { tone: "warning", text: `ATS · ${issuesText(lint.issues.length)}` };
}

export function keywordSummary(lint: LintReport | null): string {
  if (lint === null) {
    return "Покриття не перевірено";
  }
  const keywords = lint.keywords;
  if (keywords === null) {
    return "Покриття не рахувалося: вакансію не аналізовано";
  }
  const total = keywords.covered.length + keywords.missing.length;
  if (total === 0) {
    return "В аналізі нема ключових слів";
  }
  return `Ключові слова: ${keywords.covered.length}/${total} · ${keywords.percent}%`;
}

export function pagesText(pages: number): string {
  return `${pages} стор.`;
}

const MADRID_DAY = new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Madrid" });
const MADRID_TIME = new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Madrid", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });

/** Дата й час за Мадридом: «2026-10-22, 11:40». */
export function madridDateTime(iso: string): string {
  const moment = new Date(iso);
  return `${MADRID_DAY.format(moment)}, ${MADRID_TIME.format(moment)}`;
}

/** Позначка фото в картці CV: «з фото» / «без фото»; лист фото не має. */
export function photoMark(document: JobDocument): string | null {
  if (document.kind !== "cv") {
    return null;
  }
  return document.photoId === null ? "без фото" : "з фото";
}
