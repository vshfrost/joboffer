import { madridDay } from "./jobs";

/** Подачі: статус у воронці, дані подачі й чернетка форми «Я подався». Матрицю переходів знає сервер: клієнт показує лише `allowedTransitions`. */

export const APPLICATION_STATUSES = ["applied", "replied", "interview", "offer", "rejected", "withdrawn"] as const;
export type ApplicationStatus = (typeof APPLICATION_STATUSES)[number];

export const ACTIVE_STATUSES: readonly ApplicationStatus[] = ["applied", "replied", "interview", "offer"];
export const CLOSED_STATUSES: readonly ApplicationStatus[] = ["rejected", "withdrawn"];

export const STATUS_LABELS: Record<ApplicationStatus, string> = {
  applied: "Подано",
  replied: "Є відповідь",
  interview: "Співбесіда",
  offer: "Оффер",
  rejected: "Відмова",
  withdrawn: "Відкликано",
};

/** Колір лише підсилює текст статусу: applied — інформація, replied / interview — увага, offer — успіх, rejected — помилка, withdrawn — нейтральний. */
export const STATUS_TONES = {
  applied: "info",
  replied: "warning",
  interview: "warning",
  offer: "success",
  rejected: "danger",
  withdrawn: "neutral",
} as const satisfies Record<ApplicationStatus, string>;

/** Підпис кнопки переходу в цей статус. */
export const MOVE_LABELS: Record<ApplicationStatus, string> = {
  applied: "Подано",
  replied: "Є відповідь",
  interview: "Перейти до співбесіди",
  offer: "Отримано оффер",
  rejected: "Відмова",
  withdrawn: "Відкликати подачу",
};

export const CHANNELS = ["email", "ats", "linkedin", "referral"] as const;
export type ApplicationChannel = (typeof CHANNELS)[number];

export const CHANNEL_LABELS: Record<ApplicationChannel, string> = {
  email: "Email",
  ats: "ATS або сайт компанії",
  linkedin: "LinkedIn",
  referral: "Рекомендація",
};

export const ATS_PLATFORMS = ["greenhouse", "lever", "ashby", "workable", "smartrecruiters", "other"] as const;
export type AtsPlatform = (typeof ATS_PLATFORMS)[number];

export const ATS_LABELS: Record<AtsPlatform, string> = {
  greenhouse: "Greenhouse",
  lever: "Lever",
  ashby: "Ashby",
  workable: "Workable",
  smartrecruiters: "SmartRecruiters",
  other: "Інша система",
};

export interface Application {
  jobId: number;
  status: ApplicationStatus;
  /** День подачі, `YYYY-MM-DD`. */
  appliedOn: string;
  channel: ApplicationChannel;
  ats: AtsPlatform | null;
  companyDomains: string[];
  companyEmails: string[];
  /** Момент останньої зміни статусу, ISO 8601. */
  statusChangedAt: string;
  /** Куди подачу можна рухати зараз (порядок воронки); порожньо — подачу закрито. */
  allowedTransitions: ApplicationStatus[];
}

/** Поля форми «Я подався»: рядки; домени й адреси — по одному в рядку. Правила й тексти помилок — на сервері. */
export interface ApplicationDraft {
  channel: "" | ApplicationChannel;
  appliedOn: string;
  ats: "" | AtsPlatform;
  domains: string;
  emails: string;
}

/** Що йде на сервер з форми. */
export interface ApplicationInput {
  channel: string;
  appliedOn: string;
  ats: string;
  companyDomains: string[];
  companyEmails: string[];
}

/** Порожня форма: дата — сьогодні за Мадридом. */
export function emptyDraft(now: Date = new Date()): ApplicationDraft {
  return { channel: "", appliedOn: madridDay(now.toISOString()), ats: "", domains: "", emails: "" };
}

/** Форма зі збережених даних подачі. */
export function draftOf(application: Application): ApplicationDraft {
  return {
    channel: application.channel,
    appliedOn: application.appliedOn,
    ats: application.ats ?? "",
    domains: application.companyDomains.join("\n"),
    emails: application.companyEmails.join("\n"),
  };
}

export function sameDraft(a: ApplicationDraft, b: ApplicationDraft): boolean {
  return a.channel === b.channel && a.appliedOn === b.appliedOn && a.ats === b.ats && a.domains === b.domains && a.emails === b.emails;
}

/** Домени й адреси з текстових полів: по одному в рядку (чи через кому), без порожніх. */
export function applicationInput(draft: ApplicationDraft): ApplicationInput {
  return {
    channel: draft.channel,
    appliedOn: draft.appliedOn,
    ats: draft.ats,
    companyDomains: lines(draft.domains),
    companyEmails: lines(draft.emails),
  };
}

export function isClosed(application: Application): boolean {
  return CLOSED_STATUSES.includes(application.status);
}

function lines(text: string): string[] {
  return text
    .split(/[\n,]+/)
    .map((line) => line.trim())
    .filter((line) => line !== "");
}
