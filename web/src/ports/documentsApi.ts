import type { JobDocument } from "../domain/documents";

/** API документів вакансії. Усі помилки — з `domain/documentsErrors`. */
export interface DocumentsApi {
  /**
   * Версії CV і листів вакансії, новіші першими: без вмісту, з ATS-звітом кожної.
   * Кидає DocumentsUnauthorizedError, DocumentsForbiddenError, DocumentsNotFoundError або DocumentsUnavailableError.
   */
  list(jobId: number): Promise<JobDocument[]>;
  /** Адреса PDF конкретної версії: відкривається нативним посиланням з тією ж сесією. */
  pdfUrl(documentId: number): string;
}
