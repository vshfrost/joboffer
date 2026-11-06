import {
  APPLICATION_STATUSES,
  ATS_PLATFORMS,
  CHANNELS,
  type Application,
  type ApplicationChannel,
  type ApplicationStatus,
  type AtsPlatform,
} from "../domain/applications";
import { ApplicationNotFoundError, ApplicationsUnavailableError, ApplicationsValidationError } from "../domain/applicationsErrors";
import type { ApplicationsApi } from "../ports/applicationsApi";
import type { ApiClient, ApiResponse } from "./apiClient";

const CONTRACT = "Відповідь сервера не за контрактом";

export function createHttpApplicationsApi(client: ApiClient): ApplicationsApi {
  return {
    async get(jobId) {
      const response = await requestOrUnavailable(() => client.request("GET", `/jobs/${jobId}/application`));
      if (response.status === 404) {
        return null;
      }
      if (response.status !== 200) {
        throw new ApplicationsUnavailableError(`Подача: відповідь ${response.status}`);
      }
      return readApplication(response.body);
    },

    async save(jobId, input) {
      const body = {
        channel: input.channel,
        applied_on: input.appliedOn,
        ats: input.ats,
        company_domains: input.companyDomains,
        company_emails: input.companyEmails,
      };
      const response = await requestOrUnavailable(() => client.request("PUT", `/jobs/${jobId}/application`, body));
      return changed(response, "Збереження подачі");
    },

    async setStatus(jobId, status) {
      const response = await requestOrUnavailable(() => client.request("POST", `/jobs/${jobId}/application/status`, { status }));
      return changed(response, "Зміна статусу");
    },
  };
}

/** Відповідь на збереження чи перехід: 200 — подача; 422 — тексти біля полів; 404 — вакансії чи подачі нема. */
function changed(response: ApiResponse, action: string): Application {
  if (response.status === 422) {
    throw new ApplicationsValidationError(readFieldErrors(response));
  }
  if (response.status === 404) {
    throw new ApplicationNotFoundError();
  }
  if (response.status !== 200) {
    throw new ApplicationsUnavailableError(`${action}: відповідь ${response.status}`);
  }
  return readApplication(response.body);
}

async function requestOrUnavailable<T>(call: () => Promise<T>): Promise<T> {
  try {
    return await call();
  } catch (error) {
    throw new ApplicationsUnavailableError(error instanceof Error ? error.message : "Мережа недоступна");
  }
}

/** `{field_errors: [{field, message}]}` → поле → текст; без розпізнаних полів — збій контракту. */
function readFieldErrors(response: ApiResponse): Record<string, string> {
  const items = isRecord(response.body) ? response.body["field_errors"] : undefined;
  if (!Array.isArray(items)) {
    throw new ApplicationsUnavailableError(CONTRACT);
  }
  const errors: Record<string, string> = {};
  for (const item of items) {
    if (!isRecord(item) || typeof item["field"] !== "string" || typeof item["message"] !== "string") {
      throw new ApplicationsUnavailableError(CONTRACT);
    }
    errors[item["field"]] ??= item["message"];
  }
  if (Object.keys(errors).length === 0) {
    throw new ApplicationsUnavailableError(CONTRACT);
  }
  return errors;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function text(value: unknown): string {
  if (typeof value !== "string") {
    throw new ApplicationsUnavailableError(CONTRACT);
  }
  return value;
}

function integer(value: unknown): number {
  if (typeof value !== "number" || !Number.isInteger(value)) {
    throw new ApplicationsUnavailableError(CONTRACT);
  }
  return value;
}

function texts(value: unknown): string[] {
  if (!Array.isArray(value)) {
    throw new ApplicationsUnavailableError(CONTRACT);
  }
  return value.map(text);
}

/** Значення з відомого переліку; усе інше — збій контракту. */
function oneOf<T extends string>(known: readonly T[], value: unknown): T {
  const found = known.find((candidate) => candidate === value);
  if (found === undefined) {
    throw new ApplicationsUnavailableError(CONTRACT);
  }
  return found;
}

function readApplication(body: unknown): Application {
  if (!isRecord(body)) {
    throw new ApplicationsUnavailableError(CONTRACT);
  }
  const transitions = body["allowed_transitions"];
  if (!Array.isArray(transitions)) {
    throw new ApplicationsUnavailableError(CONTRACT);
  }
  return {
    jobId: integer(body["job_id"]),
    status: oneOf<ApplicationStatus>(APPLICATION_STATUSES, body["status"]),
    appliedOn: text(body["applied_on"]),
    channel: oneOf<ApplicationChannel>(CHANNELS, body["channel"]),
    ats: body["ats"] === null ? null : oneOf<AtsPlatform>(ATS_PLATFORMS, body["ats"]),
    companyDomains: texts(body["company_domains"]),
    companyEmails: texts(body["company_emails"]),
    statusChangedAt: text(body["status_changed_at"]),
    allowedTransitions: transitions.map((status) => oneOf<ApplicationStatus>(APPLICATION_STATUSES, status)),
  };
}
