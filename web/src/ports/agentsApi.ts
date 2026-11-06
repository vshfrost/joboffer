import type { Agent } from "../domain/agents";

/** API підключених агентів. Кидає AgentsUnavailableError, якщо сервер не відповів як треба. */
export interface AgentsApi {
  /** Лише агенти, підключені зараз. */
  list(): Promise<Agent[]>;
}
