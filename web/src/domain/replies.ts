/** Відповіді на подачі: черги листів компаній, розбір і його ефект на подачу. Відправник, імʼя, тема й текст — недовірені дані третіх сторін. */
import { STATUS_LABELS, type ApplicationStatus } from "./applications";
import { DEFAULT_PAGE_SIZE, PAGE_SIZES, type MailPage, type PageSize, type SenderAuth } from "./mail";

export const REPLY_QUEUES = ["matched", "unmatched", "reviewed"] as const;
export type ReplyQueue = (typeof REPLY_QUEUES)[number];
export const DEFAULT_QUEUE: ReplyQueue = "matched";

export const REPLY_TYPES = ["invitation", "assignment", "rejection", "auto_confirmation", "other"] as const;
export type ReplyType = (typeof REPLY_TYPES)[number];

export type Confidence = "high" | "medium" | "low";
export type MatchedBy = "thread" | "email" | "domain" | "ats" | "name";

export const QUEUE_LABELS: Record<ReplyQueue, string> = { matched: "До розбору", unmatched: "Без вакансії", reviewed: "Розібрані" };
export const TYPE_LABELS: Record<ReplyType, string> = {
  invitation: "Запрошення",
  assignment: "Тестове завдання",
  rejection: "Відмова",
  auto_confirmation: "Автопідтвердження",
  other: "Інше",
};

const CONFIDENCE_LABELS: Record<Confidence, string> = { high: "Висока", medium: "Середня", low: "Низька" };
const MATCHED_BY_LABELS: Record<MatchedBy, string> = {
  thread: "Збіг треду",
  email: "Збіг адреси відправника з контактами подачі",
  domain: "Збіг домену компанії",
  ats: "Збіг ATS-відправника з назвою компанії",
  name: "Збіг назви компанії в листі",
};

/** Скільки символів пошуку приймає сервер. */
const MAX_QUERY = 200;
const POSITIVE_INTEGER = /^[1-9]\d*$/;
const NO_COMPANY = "Без компанії";

/** Вакансія листа: збіг або підтверджена розбором; `status` — статус подачі, `null` — подачі нема. */
export interface ReplyJob {
  jobId: number;
  title: string | null;
  company: string | null;
  status: ApplicationStatus | null;
}

/** Ручне пересилання: відправник і тема з блоку пересланого листа, не перевірені. */
export interface ManualForward {
  fromAddress: string;
  fromName: string;
  subject: string;
}

export interface Reply {
  id: number;
  fromAddress: string;
  fromName: string;
  subject: string;
  /** ISO-момент. */
  receivedAt: string;
  senderAuth: SenderAuth;
  job: ReplyJob | null;
  confidence: Confidence | null;
  matchedBy: MatchedBy | null;
  /** Підказка типу за ключовими словами; тип підтверджує користувач. */
  suggestedType: ReplyType;
  type: ReplyType | null;
  reviewedAt: string | null;
  manualForward: ManualForward | null;
}

export interface ReplyCounts {
  matched: number;
  unmatched: number;
  reviewed: number;
}

export interface ReplyBoard {
  items: Reply[];
  page: MailPage;
  counts: ReplyCounts;
}

/** Подача власника, з якої обирається вакансія для відповіді. */
export interface AppliedJob {
  jobId: number;
  title: string | null;
  company: string | null;
  status: ApplicationStatus;
}

export interface ReplyDetail {
  reply: Reply;
  /** Текст листа, уже підготовлений сервером для людини; усе одно недовірений. */
  text: string;
  applications: AppliedJob[];
}

/** Що розбір зробить зі статусом подачі; без вакансії статусів нема. */
export interface ReviewEffect {
  current: ApplicationStatus | null;
  after: ApplicationStatus | null;
  changes: boolean;
}

export interface ReviewInput {
  type: ReplyType;
  /** `null` — лист не про жодну подачу. */
  jobId: number | null;
}

/** Що шукають у відповідях: усе живе в адресі сторінки. */
export interface ReplyQuery {
  queue: ReplyQueue;
  q: string;
  page: number;
  perPage: PageSize;
}

export const NO_JOB_EFFECT: ReviewEffect = { current: null, after: null, changes: false };

/** Адреса сторінки → запит; усе нерозпізнане стає значенням за замовчуванням. */
export function parseReplyQuery(params: URLSearchParams): ReplyQuery {
  const page = params.get("page") ?? "";
  return {
    queue: REPLY_QUEUES.find((queue) => queue === params.get("queue")) ?? DEFAULT_QUEUE,
    q: (params.get("q") ?? "").trim().slice(0, MAX_QUERY),
    page: POSITIVE_INTEGER.test(page) ? Number(page) : 1,
    perPage: PAGE_SIZES.find((size) => String(size) === params.get("per_page")) ?? DEFAULT_PAGE_SIZE,
  };
}

/** Запит → параметри адреси сторінки (значення за замовчуванням не пишуться). */
export function replyQueryParams(query: ReplyQuery): URLSearchParams {
  const params = new URLSearchParams();
  if (query.queue !== DEFAULT_QUEUE) {
    params.set("queue", query.queue);
  }
  if (query.q !== "") {
    params.set("q", query.q);
  }
  if (query.page > 1) {
    params.set("page", String(query.page));
  }
  if (query.perPage !== DEFAULT_PAGE_SIZE) {
    params.set("per_page", String(query.perPage));
  }
  return params;
}

/** Відкрита відповідь з адреси сторінки: `open=<номер>`. */
export function openReplyId(params: URLSearchParams): number | null {
  const id = params.get("open") ?? "";
  return POSITIVE_INTEGER.test(id) ? Number(id) : null;
}

/** Чи є щось, що «Скинути пошук» скине. */
export function hasReplyFilters(query: ReplyQuery): boolean {
  return query.q !== "";
}

/** Позначка рядка: тип для розібраної, інакше черга. */
export function replyStatusLabel(reply: Reply): string {
  if (reply.type !== null) {
    return TYPE_LABELS[reply.type];
  }
  return QUEUE_LABELS[reply.job === null ? "unmatched" : "matched"];
}

/** «#104 · Northstar — Senior Backend Engineer»; без назви компанії чи посади — з позначкою. */
export function jobLabel(job: Pick<ReplyJob, "jobId" | "title" | "company">): string {
  return job.title === null ? jobTag(job) : `${jobTag(job)} — ${job.title}`;
}

/** «#104 · Northstar»; без назви компанії — з позначкою. */
export function jobTag(job: Pick<ReplyJob, "jobId" | "title" | "company">): string {
  return `#${job.jobId} · ${job.company ?? NO_COMPANY}`;
}

/** «Надійність зіставлення: Висока · Збіг треду»; без зіставлення — `null`. */
export function matchText(reply: Reply): string | null {
  if (reply.confidence === null || reply.matchedBy === null) {
    return null;
  }
  return `Надійність зіставлення: ${CONFIDENCE_LABELS[reply.confidence]} · ${MATCHED_BY_LABELS[reply.matchedBy]}`;
}

/** Вакансія, обрана у формі наперед: збіг листа, якщо він є серед подач. */
export function defaultJobId(detail: ReplyDetail): number | null {
  const matched = detail.reply.job;
  return matched !== null && detail.applications.some((application) => application.jobId === matched.jobId) ? matched.jobId : null;
}

/** Ефект розбору людською мовою. */
export function effectText(effect: ReviewEffect): string {
  if (effect.current === null || effect.after === null) {
    return "Лист буде позначено розібраним без привʼязки до подачі. Статуси подач не зміняться.";
  }
  if (effect.changes) {
    return `Статус подачі: ${STATUS_LABELS[effect.current]} → ${STATUS_LABELS[effect.after]}.`;
  }
  return `Статус подачі не зміниться: ${STATUS_LABELS[effect.current]}.`;
}
