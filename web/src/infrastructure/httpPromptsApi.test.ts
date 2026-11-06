import { describe, expect, test, vi } from "vitest";

import { PROMPT_KEYS } from "../domain/prompts";
import { PromptsUnavailableError } from "../domain/promptsErrors";
import { createApiClient } from "./apiClient";
import { createHttpPromptsApi } from "./httpPromptsApi";

const BODY = Object.fromEntries(PROMPT_KEYS.map((key) => [key, `текст ${key}\n`]));

function apiWith(respond: () => Response | Promise<Response>) {
  const fetchFn = vi.fn<typeof fetch>(() => Promise.resolve(respond()));
  return { api: createHttpPromptsApi(createApiClient(fetchFn, "/api")), fetchFn };
}

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

describe("GET /prompts", () => {
  test("віддає шаблони дослівно, за ключами сервера", async () => {
    const { api, fetchFn } = apiWith(() => json(200, BODY));

    const prompts = await api.load();

    const [path, init] = fetchFn.mock.calls[0] ?? [];
    expect(path).toBe("/api/prompts");
    expect(init?.method).toBe("GET");
    expect(prompts).toEqual(BODY);
    expect(prompts["onboarding/setup"]).toBe("текст onboarding/setup\n");
  });

  test("зайвий ключ у відповіді не заважає", async () => {
    const { api } = apiWith(() => json(200, { ...BODY, "requests/new": "x" }));

    expect(await api.load()).toEqual(BODY);
  });

  test("відповідь 401 — PromptsUnavailableError", async () => {
    const { api } = apiWith(() => json(401, { code: "not_authenticated" }));

    await expect(api.load()).rejects.toBeInstanceOf(PromptsUnavailableError);
  });

  test("відповідь 500 — PromptsUnavailableError", async () => {
    const { api } = apiWith(() => json(500, { code: "internal" }));

    await expect(api.load()).rejects.toBeInstanceOf(PromptsUnavailableError);
  });

  test("мережа недоступна — PromptsUnavailableError", async () => {
    const fetchFn = vi.fn<typeof fetch>(() => Promise.reject(new TypeError("offline")));
    const api = createHttpPromptsApi(createApiClient(fetchFn, "/api"));

    await expect(api.load()).rejects.toBeInstanceOf(PromptsUnavailableError);
  });

  test.each([
    ["не обʼєкт", ["requests/triage"]],
    ["нема тіла", null],
    ["бракує ключа", Object.fromEntries(Object.entries(BODY).slice(1))],
    ["значення не рядок", { ...BODY, "requests/triage": 5 }],
    ["порожній текст", { ...BODY, "requests/triage": "" }],
  ])("відповідь не за контрактом (%s) — PromptsUnavailableError", async (_title, body) => {
    const { api } = apiWith(() => json(200, body));

    await expect(api.load()).rejects.toBeInstanceOf(PromptsUnavailableError);
  });
});
