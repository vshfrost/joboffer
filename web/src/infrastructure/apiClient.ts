import { ServiceUnavailableError } from "../domain/authErrors";

export interface ApiResponse {
  status: number;
  headers: Headers;
  /** Розібране JSON-тіло; `undefined`, якщо тіла нема або це не JSON. */
  body: unknown;
}

export interface ApiClient {
  request(method: string, path: string, body?: unknown): Promise<ApiResponse>;
  /** CSRF-токен лише в памʼяті цього клієнта; його шлють у `X-CSRF-Token` небезпечними методами. */
  setCsrfToken(token: string | null): void;
}

const CSRF_HEADER = "X-CSRF-Token";
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

/** Спільний HTTP-клієнт API: cookie того ж origin, JSON, CSRF. Мережевий збій — ServiceUnavailableError. */
export function createApiClient(fetchFn: typeof fetch, baseUrl: string): ApiClient {
  let csrfToken: string | null = null;
  return {
    setCsrfToken(token) {
      csrfToken = token;
    },
    async request(method, path, body) {
      const headers: Record<string, string> = { Accept: "application/json" };
      // Multipart-форму (фото) браузер сам підписує межею в Content-Type: вручну його не ставимо.
      const form = body instanceof FormData;
      if (body !== undefined && !form) {
        headers["Content-Type"] = "application/json";
      }
      if (csrfToken !== null && !SAFE_METHODS.has(method)) {
        headers[CSRF_HEADER] = csrfToken;
      }
      let response: Response;
      try {
        response = await fetchFn(`${baseUrl}${path}`, {
          method,
          headers,
          credentials: "same-origin",
          ...(body === undefined ? {} : { body: form ? body : JSON.stringify(body) }),
        });
      } catch {
        throw new ServiceUnavailableError("Мережа недоступна");
      }
      return { status: response.status, headers: response.headers, body: await readJson(response) };
    },
  };
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return undefined;
  }
}
