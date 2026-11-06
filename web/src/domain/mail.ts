/** Пошта: листи, переслані в joboffer. Відправник, імʼя, тема й текст — недовірені дані третіх сторін. */

export type MailCategory =
  | "company"
  | "linkedin_alert"
  | "linkedin_application"
  | "linkedin_message"
  | "forwarding_confirmation"
  | "suspicious"
  | "other";
export type SenderAuth = "verified" | "failed" | "unknown";
export type DropReason = "daily_limit" | "retired_tag";

/** Вид листа у фільтрі «Вхідних»: група категорій або відкинуті листи. */
export type MailKind = "company" | "linkedin_alert" | "linkedin_message" | "forwarding_confirmation" | "other" | "dropped";

export const MAIL_KINDS: readonly MailKind[] = ["company", "linkedin_alert", "linkedin_message", "forwarding_confirmation", "other", "dropped"];
export const PAGE_SIZES = [20, 50, 100] as const;
export type PageSize = (typeof PAGE_SIZES)[number];
export const DEFAULT_PAGE_SIZE: PageSize = 20;

/** Рядок «Вхідних»: збережений лист або відкинутий (тоді є причина, а категорії й вердикту нема). */
export interface MailItem {
  id: number;
  dropped: boolean;
  fromAddress: string;
  fromName: string;
  subject: string;
  /** ISO-момент. */
  receivedAt: string;
  category: MailCategory | null;
  senderAuth: SenderAuth | null;
  reason: DropReason | null;
}

export interface MailPage {
  number: number;
  size: number;
  total: number;
  first: number;
  last: number;
  hasNewer: boolean;
  hasOlder: boolean;
}

export interface MailList {
  items: MailItem[];
  page: MailPage;
}

/** Лист Gmail про пересилання: порожній код — Gmail надіслав лише посилання. */
export interface Forwarding {
  code: string;
  linkOnly: boolean;
  requestedBy: string;
  receivedAt: string;
  /** false — лист до ротації адреси: код для старої адреси. */
  current: boolean;
}

export interface MailDetail {
  item: MailItem;
  /** Текст листа, уже підготовлений сервером для людини; усе одно недовірений. */
  text: string;
  forwarding: Forwarding | null;
}

export interface ManualSync {
  limit: number;
  remaining: number;
  /** ISO-момент, коли звільниться наступний запит; `null` — запити є. */
  nextAt: string | null;
}

export interface MailSettings {
  address: string;
  rotatedAt: string | null;
  syncedAt: string | null;
  syncFailed: boolean;
  syncError: string;
  manual: ManualSync;
}

/** Що шукають у «Вхідних»: усе живе в адресі сторінки. */
export interface MailQuery {
  q: string;
  kind: "" | MailKind;
  page: number;
  perPage: PageSize;
}

export const KIND_LABELS: Record<MailKind, string> = {
  company: "Компанія",
  linkedin_alert: "LinkedIn: вакансії",
  linkedin_message: "LinkedIn: повідомлення",
  forwarding_confirmation: "Підтвердження Gmail",
  other: "Інше",
  dropped: "Відхилені",
};

export const DROP_REASON_TEXT: Record<DropReason, string> = {
  daily_limit: "Понад добовий ліміт: за 24 години збережено вже 100 листів.",
  retired_tag: "Лист на стару адресу: пересилання в Gmail ще не оновлено.",
};

const CATEGORY_LABELS: Record<MailCategory, string> = {
  company: "Компанія",
  linkedin_alert: "LinkedIn: вакансії",
  linkedin_application: "LinkedIn: подачі",
  linkedin_message: "LinkedIn: повідомлення",
  forwarding_confirmation: "Підтвердження Gmail",
  suspicious: "Підозрілий",
  other: "Інше",
};

const SENDER_LABELS: Record<SenderAuth, { text: string; tone: "success" | "warning" | "danger" }> = {
  verified: { text: "Відправника підтверджено", tone: "success" },
  unknown: { text: "Відправника не підтверджено", tone: "warning" },
  failed: { text: "Підроблений відправник", tone: "danger" },
};

const POSITIVE_INTEGER = /^[1-9]\d*$/;
const MADRID = "Europe/Madrid";
const DAY = new Intl.DateTimeFormat("en-CA", { timeZone: MADRID, year: "numeric", month: "2-digit", day: "2-digit" });
const TIME = new Intl.DateTimeFormat("en-GB", { timeZone: MADRID, hour: "2-digit", minute: "2-digit", hourCycle: "h23" });

/** Адреса сторінки → запит; усе нерозпізнане стає значенням за замовчуванням. */
export function parseMailQuery(params: URLSearchParams): MailQuery {
  const page = params.get("page") ?? "";
  return {
    q: (params.get("q") ?? "").trim(),
    kind: MAIL_KINDS.find((kind) => kind === params.get("kind")) ?? "",
    page: POSITIVE_INTEGER.test(page) ? Number(page) : 1,
    perPage: PAGE_SIZES.find((size) => String(size) === params.get("per_page")) ?? DEFAULT_PAGE_SIZE,
  };
}

/** Запит → параметри адреси сторінки (значення за замовчуванням не пишуться). */
export function mailQueryParams(query: MailQuery): URLSearchParams {
  const params = new URLSearchParams();
  if (query.q !== "") {
    params.set("q", query.q);
  }
  if (query.kind !== "") {
    params.set("kind", query.kind);
  }
  if (query.page > 1) {
    params.set("page", String(query.page));
  }
  if (query.perPage !== DEFAULT_PAGE_SIZE) {
    params.set("per_page", String(query.perPage));
  }
  return params;
}

/** Чи є щось, що «Скинути фільтри» скине: пошук або вид. */
export function hasMailFilters(query: MailQuery): boolean {
  return query.q !== "" || query.kind !== "";
}

/** Назва виду рядка: для відкинутого — «Відхилено», для збереженого — за категорією. */
export function itemLabel(item: MailItem): string {
  if (item.dropped) {
    return "Відхилено";
  }
  return item.category === null ? CATEGORY_LABELS.other : CATEGORY_LABELS[item.category];
}

/** Позначка автентичності відправника; без вердикту (відкинутий лист) — як непідтверджений. */
export function senderLabel(auth: SenderAuth | null): { text: string; tone: "success" | "warning" | "danger" } {
  return SENDER_LABELS[auth ?? "unknown"];
}

/** Хто написав: імʼя, інакше адреса; сам лист міг не мати жодного. */
export function senderName(item: Pick<MailItem, "fromName" | "fromAddress">): string {
  return item.fromName !== "" ? item.fromName : item.fromAddress !== "" ? item.fromAddress : "(без відправника)";
}

/** Тема листа; порожня тема має позначку. */
export function subjectText(item: Pick<MailItem, "subject">): string {
  return item.subject.trim() === "" ? "(без теми)" : item.subject;
}

/** Чому лист відкинуто; для збереженого листа порожньо. */
export function dropReasonText(item: MailItem): string {
  return item.reason === null ? "" : DROP_REASON_TEXT[item.reason];
}

/** «2026-10-24» за часом Мадрида. */
export function madridDay(iso: string): string {
  return DAY.format(new Date(iso));
}

/** «15:45» за часом Мадрида. */
export function madridTime(iso: string): string {
  return TIME.format(new Date(iso));
}

/** «1–20 з 45»; порожній список і сторінка за межею списку мають окремі тексти. */
export function rangeText(page: MailPage): string {
  if (page.total === 0) {
    return "0 листів";
  }
  if (page.first > page.total) {
    return `0 листів на цій сторінці з ${page.total}`;
  }
  return `${page.first}–${page.last} з ${page.total}`;
}
