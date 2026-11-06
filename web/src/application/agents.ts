import { AgentsUnavailableError } from "../domain/agentsErrors";
import type { Agent } from "../domain/agents";
import type { AgentsApi } from "../ports/agentsApi";

export type LoadAgentsOutcome = { ok: true; agents: Agent[] } | { ok: false };

export interface AgentsServices {
  load(): Promise<LoadAgentsOutcome>;
}

export function createAgentsServices(api: AgentsApi): AgentsServices {
  return {
    async load() {
      try {
        return { ok: true, agents: await api.list() };
      } catch (error) {
        if (error instanceof AgentsUnavailableError) {
          return { ok: false };
        }
        throw error;
      }
    },
  };
}
