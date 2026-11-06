import { describe, expect, test, vi } from "vitest";

import { AgentsUnavailableError } from "../domain/agentsErrors";
import { createApiClient } from "./apiClient";
import { createHttpAgentsApi } from "./httpAgentsApi";

function apiWith(respond: () => Response | Promise<Response>) {
  const fetchFn = vi.fn<typeof fetch>(() => Promise.resolve(respond()));
  return { api: createHttpAgentsApi(createApiClient(fetchFn, "/api")), fetchFn };
}

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

describe("GET /agents", () => {
  test("віддає агентів у порядку відповіді", async () => {
    const { api, fetchFn } = apiWith(() =>
      json(200, [
        { id: "a1", kind: "claude", name: "Claude" },
        { id: "a2", kind: "other", name: "Cursor" },
      ]),
    );

    const agents = await api.list();

    const [path, init] = fetchFn.mock.calls[0] ?? [];
    expect(path).toBe("/api/agents");
    expect(init?.method).toBe("GET");
    expect(agents).toEqual([
      { id: "a1", kind: "claude", name: "Claude" },
      { id: "a2", kind: "other", name: "Cursor" },
    ]);
  });

  test("порожній список — це порожній список, а не помилка", async () => {
    const { api } = apiWith(() => json(200, []));

    expect(await api.list()).toEqual([]);
  });

  test("невідомий вид агента вважається іншим: кнопка лишається, запит лише копіюється", async () => {
    const { api } = apiWith(() => json(200, [{ id: "a1", kind: "gemini", name: "Gemini" }]));

    expect(await api.list()).toEqual([{ id: "a1", kind: "other", name: "Gemini" }]);
  });

  test("відповідь 500 — AgentsUnavailableError", async () => {
    const { api } = apiWith(() => json(500, { code: "internal" }));

    await expect(api.list()).rejects.toBeInstanceOf(AgentsUnavailableError);
  });

  test("мережа недоступна — AgentsUnavailableError", async () => {
    const fetchFn = vi.fn<typeof fetch>(() => Promise.reject(new TypeError("offline")));
    const api = createHttpAgentsApi(createApiClient(fetchFn, "/api"));

    await expect(api.list()).rejects.toBeInstanceOf(AgentsUnavailableError);
  });

  test.each([
    ["не масив", { agents: [] }],
    ["елемент не обʼєкт", ["claude"]],
    ["id не рядок", [{ id: 1, kind: "claude", name: "Claude" }]],
    ["name не рядок", [{ id: "a1", kind: "claude", name: null }]],
    ["kind не рядок", [{ id: "a1", kind: 5, name: "Claude" }]],
  ])("відповідь не за контрактом (%s) — AgentsUnavailableError", async (_title, body) => {
    const { api } = apiWith(() => json(200, body));

    await expect(api.list()).rejects.toBeInstanceOf(AgentsUnavailableError);
  });
});
