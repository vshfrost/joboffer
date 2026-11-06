import { describe, expect, test, vi } from "vitest";

import type { Agent } from "../domain/agents";
import { AgentsUnavailableError } from "../domain/agentsErrors";
import type { AgentsApi } from "../ports/agentsApi";
import { createAgentsServices } from "./agents";

const AGENTS: Agent[] = [{ id: "a1", kind: "claude", name: "Claude" }];

function servicesOver(list: AgentsApi["list"]) {
  return createAgentsServices({ list: vi.fn(list) });
}

describe("load", () => {
  test("віддає агентів із порту", async () => {
    expect(await servicesOver(() => Promise.resolve(AGENTS)).load()).toEqual({ ok: true, agents: AGENTS });
  });

  test("порожній список — успіх із порожнім списком", async () => {
    expect(await servicesOver(() => Promise.resolve([])).load()).toEqual({ ok: true, agents: [] });
  });

  test("недоступний сервер — не успіх, без винятку", async () => {
    expect(await servicesOver(() => Promise.reject(new AgentsUnavailableError("збій"))).load()).toEqual({ ok: false });
  });

  test("несподівана помилка не ховається", async () => {
    await expect(servicesOver(() => Promise.reject(new TypeError("помилка програмування"))).load()).rejects.toThrow("помилка програмування");
  });
});
