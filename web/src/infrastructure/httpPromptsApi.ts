import { PROMPT_KEYS, type Prompts } from "../domain/prompts";
import { PromptsUnavailableError } from "../domain/promptsErrors";
import type { PromptsApi } from "../ports/promptsApi";
import type { ApiClient } from "./apiClient";

const CONTRACT = "Відповідь сервера не за контрактом";

export function createHttpPromptsApi(client: ApiClient): PromptsApi {
  return {
    async load() {
      let response;
      try {
        response = await client.request("GET", "/prompts");
      } catch {
        throw new PromptsUnavailableError("Мережа недоступна");
      }
      if (response.status !== 200) {
        throw new PromptsUnavailableError(`Тексти запитів: відповідь ${response.status}`);
      }
      return readPrompts(response.body);
    },
  };
}

/** Кожен відомий клієнту ключ має бути непорожнім рядком: інакше кнопка скопіювала б порожній запит. */
function readPrompts(body: unknown): Prompts {
  if (typeof body !== "object" || body === null) {
    throw new PromptsUnavailableError(CONTRACT);
  }
  const record = body as Record<string, unknown>;
  const entries = PROMPT_KEYS.map((key) => {
    const text = record[key];
    if (typeof text !== "string" || text === "") {
      throw new PromptsUnavailableError(CONTRACT);
    }
    return [key, text] as const;
  });
  return Object.fromEntries(entries) as Prompts;
}
