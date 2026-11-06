import { AGENT_KINDS, type Agent, type AgentKind } from "../domain/agents";
import { AgentsUnavailableError } from "../domain/agentsErrors";
import type { AgentsApi } from "../ports/agentsApi";
import type { ApiClient } from "./apiClient";

const CONTRACT = "Відповідь сервера не за контрактом";

export function createHttpAgentsApi(client: ApiClient): AgentsApi {
  return {
    async list() {
      let response;
      try {
        response = await client.request("GET", "/agents");
      } catch {
        throw new AgentsUnavailableError("Мережа недоступна");
      }
      if (response.status !== 200) {
        throw new AgentsUnavailableError(`Агенти: відповідь ${response.status}`);
      }
      return readAgents(response.body);
    },
  };
}

function readAgents(body: unknown): Agent[] {
  if (!Array.isArray(body)) {
    throw new AgentsUnavailableError(CONTRACT);
  }
  return body.map(readAgent);
}

function readAgent(item: unknown): Agent {
  if (typeof item !== "object" || item === null) {
    throw new AgentsUnavailableError(CONTRACT);
  }
  const { id, kind, name } = item as Record<string, unknown>;
  if (typeof id !== "string" || typeof kind !== "string" || typeof name !== "string") {
    throw new AgentsUnavailableError(CONTRACT);
  }
  return { id, kind: kindOf(kind), name };
}

/** Вид, якого клієнт ще не знає, — «інший»: кнопка лишається, запит лише копіюється. */
function kindOf(value: string): AgentKind {
  return AGENT_KINDS.find((kind) => kind === value) ?? "other";
}
