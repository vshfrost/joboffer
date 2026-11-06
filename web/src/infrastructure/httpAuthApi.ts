import { InvalidCredentialsError, ServiceUnavailableError, TooManyAttemptsError } from "../domain/authErrors";
import type { AuthProviders, Session } from "../domain/session";
import type { AuthApi } from "../ports/authApi";
import type { ApiClient } from "./apiClient";

const DEFAULT_RETRY_AFTER_SECONDS = 60;

/** `client` спільний з іншими адаптерами: CSRF-токен сесії живе в ньому, а не в кожного свій. */
export function createHttpAuthApi(client: ApiClient, baseUrl: string): AuthApi {
  return {
    async login(email, password) {
      const response = await client.request("POST", "/auth/login", { email, password });
      if (response.status === 200) {
        return acceptSession(client, response.body);
      }
      if (response.status === 401) {
        throw new InvalidCredentialsError("Невірний email або пароль");
      }
      if (response.status === 429) {
        throw new TooManyAttemptsError(retryAfterSeconds(response.headers.get("Retry-After")));
      }
      throw new ServiceUnavailableError(`Вхід: відповідь ${response.status}`);
    },

    async currentSession() {
      const response = await client.request("GET", "/auth/me");
      if (response.status === 200) {
        return acceptSession(client, response.body);
      }
      client.setCsrfToken(null);
      if (response.status === 401) {
        return null;
      }
      throw new ServiceUnavailableError(`Сесія: відповідь ${response.status}`);
    },

    async logout() {
      const response = await client.request("POST", "/auth/logout");
      if (response.status !== 204) {
        throw new ServiceUnavailableError(`Вихід: відповідь ${response.status}`);
      }
      client.setCsrfToken(null);
    },

    async providers() {
      const response = await client.request("GET", "/auth/providers");
      const google = isRecord(response.body) ? response.body["google"] : undefined;
      if (response.status !== 200 || typeof google !== "boolean") {
        throw new ServiceUnavailableError(`Провайдери: відповідь ${response.status}`);
      }
      return { google } satisfies AuthProviders;
    },

    googleStartUrl(next) {
      return `${baseUrl}/auth/google/start?next=${encodeURIComponent(next)}`;
    },
  };
}

export function retryAfterSeconds(header: string | null): number {
  const seconds = Number(header);
  return Number.isInteger(seconds) && seconds > 0 ? seconds : DEFAULT_RETRY_AFTER_SECONDS;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

/** Відповідь `login` / `me`: `{user: {id, email, display_name}, csrf_token}`. Інакше — збій контракту. */
export function acceptSession(client: ApiClient, body: unknown): Session {
  const user = isRecord(body) ? body["user"] : undefined;
  const csrfToken = isRecord(body) ? body["csrf_token"] : undefined;
  if (
    !isRecord(user) ||
    typeof user["id"] !== "string" ||
    typeof user["email"] !== "string" ||
    typeof user["display_name"] !== "string" ||
    typeof csrfToken !== "string"
  ) {
    throw new ServiceUnavailableError("Відповідь сервера не за контрактом");
  }
  client.setCsrfToken(csrfToken);
  return { user: { id: user["id"], email: user["email"], displayName: user["display_name"] } };
}
