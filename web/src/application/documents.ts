import type { JobDocument } from "../domain/documents";
import {
  DocumentsForbiddenError,
  DocumentsNotFoundError,
  DocumentsUnauthorizedError,
  DocumentsUnavailableError,
} from "../domain/documentsErrors";
import type { DocumentsApi } from "../ports/documentsApi";

/** `unauthorized` — сесія завершилась; `forbidden` — нема доступу; `not-found` — вакансії нема; `unavailable` — збій. */
export type LoadDocumentsOutcome =
  | { ok: true; documents: JobDocument[] }
  | { ok: false; kind: "unauthorized" | "forbidden" | "not-found" | "unavailable" };

export interface DocumentsServices {
  load(jobId: number): Promise<LoadDocumentsOutcome>;
  pdfUrl(documentId: number): string;
}

export function createDocumentsServices(api: DocumentsApi): DocumentsServices {
  return {
    async load(jobId) {
      try {
        return { ok: true, documents: await api.list(jobId) };
      } catch (error) {
        if (error instanceof DocumentsUnauthorizedError) {
          return { ok: false, kind: "unauthorized" };
        }
        if (error instanceof DocumentsForbiddenError) {
          return { ok: false, kind: "forbidden" };
        }
        if (error instanceof DocumentsNotFoundError) {
          return { ok: false, kind: "not-found" };
        }
        if (error instanceof DocumentsUnavailableError) {
          return { ok: false, kind: "unavailable" };
        }
        throw error;
      }
    },
    pdfUrl: (documentId) => api.pdfUrl(documentId),
  };
}
