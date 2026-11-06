import { FACT_KINDS, SOURCES, type Fact, type FactKind, type FactSource, type OriginalCv } from "../domain/facts";
import { FactNotFoundError, FactsConflictError, FactsUnavailableError, FactsValidationError } from "../domain/factsErrors";
import type { FactsApi } from "../ports/factsApi";
import type { ApiClient, ApiResponse } from "./apiClient";

const CONTRACT = "Відповідь сервера не за контрактом";

export function createHttpFactsApi(client: ApiClient): FactsApi {
  return {
    async list() {
      const response = await requestOrUnavailable(() => client.request("GET", "/facts"));
      if (response.status !== 200) {
        throw new FactsUnavailableError(`Факти: відповідь ${response.status}`);
      }
      return readFacts(response.body, "facts");
    },

    async originalCv() {
      const response = await requestOrUnavailable(() => client.request("GET", "/facts/original-cv"));
      if (response.status === 404) {
        return null;
      }
      if (response.status !== 200) {
        throw new FactsUnavailableError(`Оригінал CV: відповідь ${response.status}`);
      }
      return readCv(response.body);
    },

    async confirm(ids) {
      const response = await requestOrUnavailable(() => client.request("POST", "/facts/confirm", { fact_ids: [...ids] }));
      if (response.status === 422) {
        throw readValidation(response);
      }
      if (response.status === 404) {
        throw new FactNotFoundError();
      }
      if (response.status !== 200) {
        throw new FactsUnavailableError(`Підтвердження: відповідь ${response.status}`);
      }
      return readFacts(response.body, "facts");
    },

    async create(draft) {
      const response = await requestOrUnavailable(() => client.request("POST", "/facts", { kind: draft.kind, text: draft.text }));
      if (response.status === 422) {
        throw readValidation(response);
      }
      if (response.status === 409) {
        throw new FactsConflictError(readMessage(response));
      }
      if (response.status !== 201) {
        throw new FactsUnavailableError(`Додавання факту: відповідь ${response.status}`);
      }
      return readFact(response.body);
    },

    async update(id, draft) {
      const response = await requestOrUnavailable(() => client.request("PUT", `/facts/${id}`, { kind: draft.kind, text: draft.text }));
      if (response.status === 422) {
        throw readValidation(response);
      }
      if (response.status === 409) {
        throw new FactsConflictError(readMessage(response));
      }
      if (response.status === 404) {
        throw new FactNotFoundError();
      }
      if (response.status !== 200) {
        throw new FactsUnavailableError(`Зміна факту: відповідь ${response.status}`);
      }
      return readFact(response.body);
    },

    async remove(id) {
      const response = await requestOrUnavailable(() => client.request("DELETE", `/facts/${id}`));
      if (response.status === 404) {
        throw new FactNotFoundError();
      }
      if (response.status !== 204) {
        throw new FactsUnavailableError(`Видалення: відповідь ${response.status}`);
      }
    },
  };
}

async function requestOrUnavailable<T>(call: () => Promise<T>): Promise<T> {
  try {
    return await call();
  } catch (error) {
    throw new FactsUnavailableError(error instanceof Error ? error.message : "Мережа недоступна");
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readMessage(response: ApiResponse): string {
  const message = isRecord(response.body) ? response.body["message"] : undefined;
  if (typeof message !== "string" || message === "") {
    throw new FactsUnavailableError(CONTRACT);
  }
  return message;
}

/** `{message, field_errors: [{field, message}]}` → помилка перевірки; без розпізнаних полів — збій контракту. */
function readValidation(response: ApiResponse): FactsValidationError {
  const items = isRecord(response.body) ? response.body["field_errors"] : undefined;
  if (!Array.isArray(items)) {
    throw new FactsUnavailableError(CONTRACT);
  }
  const fieldErrors: Record<string, string> = {};
  for (const item of items) {
    if (!isRecord(item) || typeof item["field"] !== "string" || typeof item["message"] !== "string") {
      throw new FactsUnavailableError(CONTRACT);
    }
    fieldErrors[item["field"]] ??= item["message"];
  }
  if (Object.keys(fieldErrors).length === 0) {
    throw new FactsUnavailableError(CONTRACT);
  }
  return new FactsValidationError(readMessage(response), fieldErrors);
}

function text(value: unknown): string {
  if (typeof value !== "string") {
    throw new FactsUnavailableError(CONTRACT);
  }
  return value;
}

function kind(value: unknown): FactKind {
  const found = FACT_KINDS.find((known) => known === value);
  if (found === undefined) {
    throw new FactsUnavailableError(CONTRACT);
  }
  return found;
}

function source(value: unknown): FactSource {
  const found = SOURCES.find((known) => known === value);
  if (found === undefined) {
    throw new FactsUnavailableError(CONTRACT);
  }
  return found;
}

function jobId(value: unknown): number | null {
  if (value === null) {
    return null;
  }
  if (typeof value !== "number" || !Number.isInteger(value)) {
    throw new FactsUnavailableError(CONTRACT);
  }
  return value;
}

function readFacts(body: unknown, key: string): Fact[] {
  const items = isRecord(body) ? body[key] : undefined;
  if (!Array.isArray(items)) {
    throw new FactsUnavailableError(CONTRACT);
  }
  return items.map(readFact);
}

function readFact(item: unknown): Fact {
  if (!isRecord(item) || typeof item["fact_id"] !== "number" || !Number.isInteger(item["fact_id"]) || typeof item["confirmed"] !== "boolean") {
    throw new FactsUnavailableError(CONTRACT);
  }
  return {
    id: item["fact_id"],
    kind: kind(item["kind"]),
    text: text(item["text"]),
    confirmed: item["confirmed"],
    source: source(item["source"]),
    jobId: jobId(item["job_id"]),
    createdAt: text(item["created_at"]),
    updatedAt: text(item["updated_at"]),
  };
}

function readCv(body: unknown): OriginalCv {
  if (!isRecord(body)) {
    throw new FactsUnavailableError(CONTRACT);
  }
  return {
    fileName: body["file_name"] === null ? null : text(body["file_name"]),
    text: text(body["text"]),
    savedAt: text(body["saved_at"]),
  };
}
