import type { Application, ApplicationInput, ApplicationStatus } from "../domain/applications";

/** API подач. Усі помилки — з `domain/applicationsErrors`. */
export interface ApplicationsApi {
  /** Подача на вакансію; `null` — подачі нема (сервер відповідає 404 і коли вакансії нема, і коли на неї не подавались). Кидає ApplicationsUnavailableError. */
  get(jobId: number): Promise<Application | null>;
  /** «Я подався» / зміна даних подачі. Кидає ApplicationsValidationError (422), ApplicationNotFoundError або ApplicationsUnavailableError. */
  save(jobId: number, input: ApplicationInput): Promise<Application>;
  /** Переводить подачу в наступний статус. Кидає ApplicationsValidationError (422: перехід неможливий), ApplicationNotFoundError або ApplicationsUnavailableError. */
  setStatus(jobId: number, status: ApplicationStatus): Promise<Application>;
}
