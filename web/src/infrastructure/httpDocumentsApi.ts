import { DOCUMENT_KINDS, type JobDocument, type KeywordCoverage, type LintIssue, type LintReport } from "../domain/documents";
import {
  DocumentsForbiddenError,
  DocumentsNotFoundError,
  DocumentsUnauthorizedError,
  DocumentsUnavailableError,
} from "../domain/documentsErrors";
import type { DocumentsApi } from "../ports/documentsApi";
import type { ApiClient, ApiResponse } from "./apiClient";

const CONTRACT = "Відповідь сервера не за контрактом";

export function createHttpDocumentsApi(client: ApiClient, apiBase: string): DocumentsApi {
  return {
    async list(jobId) {
      const response = await requestOrUnavailable(() => client.request("GET", `/jobs/${jobId}/documents`));
      throwForStatus(response);
      return readList(response.body);
    },

    pdfUrl: (documentId) => `${apiBase}/documents/${documentId}/pdf`,
  };
}

function throwForStatus(response: ApiResponse): void {
  switch (response.status) {
    case 200:
      return;
    case 401:
      throw new DocumentsUnauthorizedError();
    case 403:
      throw new DocumentsForbiddenError();
    case 404:
      throw new DocumentsNotFoundError();
    default:
      throw new DocumentsUnavailableError(`Документи: відповідь ${response.status}`);
  }
}

async function requestOrUnavailable<T>(call: () => Promise<T>): Promise<T> {
  try {
    return await call();
  } catch (error) {
    throw new DocumentsUnavailableError(error instanceof Error ? error.message : "Мережа недоступна");
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function record(value: unknown): Record<string, unknown> {
  if (!isRecord(value)) {
    throw new DocumentsUnavailableError(CONTRACT);
  }
  return value;
}

function text(value: unknown): string {
  if (typeof value !== "string") {
    throw new DocumentsUnavailableError(CONTRACT);
  }
  return value;
}

function flag(value: unknown): boolean {
  if (typeof value !== "boolean") {
    throw new DocumentsUnavailableError(CONTRACT);
  }
  return value;
}

function integer(value: unknown): number {
  if (typeof value !== "number" || !Number.isInteger(value)) {
    throw new DocumentsUnavailableError(CONTRACT);
  }
  return value;
}

function list<T>(value: unknown, read: (item: unknown) => T): T[] {
  if (!Array.isArray(value)) {
    throw new DocumentsUnavailableError(CONTRACT);
  }
  return value.map(read);
}

function readList(body: unknown): JobDocument[] {
  return list(record(body)["items"], readDocument);
}

function readDocument(item: unknown): JobDocument {
  const value = record(item);
  const kind = DOCUMENT_KINDS.find((known) => known === value["kind"]);
  if (kind === undefined) {
    throw new DocumentsUnavailableError(CONTRACT);
  }
  return {
    id: integer(value["document_id"]),
    jobId: integer(value["job_id"]),
    kind,
    version: integer(value["version"]),
    createdAt: text(value["created_at"]),
    fileName: text(value["file_name"]),
    pdfAvailable: flag(value["pdf_available"]),
    photoId: value["photo_id"] === null ? null : integer(value["photo_id"]),
    lint: value["lint"] === null ? null : readLint(value["lint"]),
  };
}

function readLint(item: unknown): LintReport {
  const value = record(item);
  return {
    passed: flag(value["passed"]),
    pages: integer(value["pages"]),
    issues: list(value["issues"], readIssue),
    keywords: value["keywords"] === null ? null : readKeywords(value["keywords"]),
  };
}

function readIssue(item: unknown): LintIssue {
  const value = record(item);
  return { code: text(value["code"]), message: text(value["message"]) };
}

function readKeywords(item: unknown): KeywordCoverage {
  const value = record(item);
  return { covered: list(value["covered"], text), missing: list(value["missing"], text), percent: integer(value["percent"]) };
}
