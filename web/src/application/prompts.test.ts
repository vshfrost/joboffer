import { describe, expect, test, vi } from "vitest";

import { PROMPT_KEYS, type Prompts } from "../domain/prompts";
import { PromptsUnavailableError } from "../domain/promptsErrors";
import type { PromptsApi } from "../ports/promptsApi";
import { createPromptsServices } from "./prompts";

const PROMPTS = Object.fromEntries(PROMPT_KEYS.map((key) => [key, key])) as Prompts;

function servicesOver(load: PromptsApi["load"]) {
  return createPromptsServices({ load: vi.fn(load) });
}

describe("load", () => {
  test("віддає шаблони з порту", async () => {
    expect(await servicesOver(() => Promise.resolve(PROMPTS)).load()).toEqual({ ok: true, prompts: PROMPTS });
  });

  test("недоступний сервер — не успіх, без винятку", async () => {
    expect(await servicesOver(() => Promise.reject(new PromptsUnavailableError("збій"))).load()).toEqual({ ok: false });
  });

  test("несподівана помилка не ховається", async () => {
    await expect(servicesOver(() => Promise.reject(new TypeError("помилка програмування"))).load()).rejects.toThrow("помилка програмування");
  });
});
