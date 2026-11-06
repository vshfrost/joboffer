import type { Prompts } from "../domain/prompts";

/** API текстів запитів до агента. Кидає PromptsUnavailableError, якщо сервер не відповів як треба. */
export interface PromptsApi {
  load(): Promise<Prompts>;
}
