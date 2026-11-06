import type { MailDetail, MailList, MailQuery, MailSettings, ManualSync } from "../domain/mail";

/** API пошти. Помилки — з `domain/mailErrors`. */
export interface MailApi {
  /** «Вхідні»: збережені й відкинуті листи. Кидає MailUnauthorizedError, MailNotConfiguredError або MailUnavailableError. */
  list(query: MailQuery): Promise<MailList>;
  /** Лист із текстом. Кидає MailNotFoundError, MailUnauthorizedError, MailNotConfiguredError або MailUnavailableError. */
  get(id: number): Promise<MailDetail>;
  /** Адреса, стан синку й ліміт синку вручну. */
  settings(): Promise<MailSettings>;
  /** Запит синку вручну. Кидає MailSyncLimitError, коли ліміт вичерпано. */
  requestSync(): Promise<ManualSync>;
  /** Нова адреса для пересилання; повертає оновлені налаштування. */
  rotate(): Promise<MailSettings>;
}
