/** Підроблений `GET /api/agents` поверх будь-якого іншого підробленого бекенду: інші запити йдуть до нього без змін. */
import { json } from "./testClient";

export interface ApiAgent {
  id: string;
  kind: "claude" | "claude_code" | "chatgpt" | "codex" | "other";
  name: string;
}

export const CLAUDE: ApiAgent = { id: "a1", kind: "claude", name: "Claude" };
export const CLAUDE_CODE: ApiAgent = { id: "a2", kind: "claude_code", name: "Claude Code" };
export const CODEX: ApiAgent = { id: "a3", kind: "codex", name: "Codex" };
export const CHATGPT: ApiAgent = { id: "a4", kind: "chatgpt", name: "ChatGPT" };
export const CURSOR: ApiAgent = { id: "a5", kind: "other", name: "Cursor" };

export interface AgentsStub {
  /** Скільки разів клієнт питав список агентів. */
  requests: number;
}

/** Підміняє `fetchFn` бекенду: `GET /api/agents` віддає `agents` (`"fail"` — помилку 500), решту передає далі. */
export function connectAgents(backend: { fetchFn: typeof fetch }, agents: readonly ApiAgent[] | "fail"): AgentsStub {
  const inner = backend.fetchFn;
  const stub: AgentsStub = { requests: 0 };
  backend.fetchFn = (input, init) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.pathname : input.url;
    if ((init?.method ?? "GET") === "GET" && url === "/api/agents") {
      stub.requests += 1;
      return Promise.resolve(agents === "fail" ? json(500, { code: "internal_error" }) : json(200, agents));
    }
    return inner(input, init);
  };
  return stub;
}
