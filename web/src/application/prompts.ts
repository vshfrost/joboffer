import type { Prompts } from "../domain/prompts";
import { PromptsUnavailableError } from "../domain/promptsErrors";
import type { PromptsApi } from "../ports/promptsApi";

export type LoadPromptsOutcome = { ok: true; prompts: Prompts } | { ok: false };

export interface PromptsServices {
  load(): Promise<LoadPromptsOutcome>;
}

export function createPromptsServices(api: PromptsApi): PromptsServices {
  return {
    async load() {
      try {
        return { ok: true, prompts: await api.load() };
      } catch (error) {
        if (error instanceof PromptsUnavailableError) {
          return { ok: false };
        }
        throw error;
      }
    },
  };
}
