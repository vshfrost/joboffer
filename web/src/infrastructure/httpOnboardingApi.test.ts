/** Застарілі маршрути підказок лишаються робочими, хоч веб їх більше не викликає: контракт POST /onboarding/tips/{key}/seen|dismiss. */
import { describe, expect, test, vi } from "vitest";

import { OnboardingUnavailableError } from "../domain/onboardingErrors";
import { createApiClient } from "./apiClient";
import { createHttpOnboardingApi } from "./httpOnboardingApi";

function apiWith(respond: () => Response | Promise<Response>) {
  const fetchFn = vi.fn<typeof fetch>(() => Promise.resolve(respond()));
  return { api: createHttpOnboardingApi(createApiClient(fetchFn, "/api")), fetchFn };
}

describe.each([
  ["markSeen", "seen"],
  ["dismiss", "dismiss"],
] as const)("%s", (method, route) => {
  test(`шле POST /onboarding/tips/goal/${route}; 204 — успіх`, async () => {
    const { api, fetchFn } = apiWith(() => new Response(null, { status: 204 }));

    await api[method]("goal");

    const [path, init] = fetchFn.mock.calls[0] ?? [];
    expect(path).toBe(`/api/onboarding/tips/goal/${route}`);
    expect(init?.method).toBe("POST");
  });

  test("інша відповідь сервера — OnboardingUnavailableError", async () => {
    const { api } = apiWith(() => new Response(JSON.stringify({ code: "internal_error" }), { status: 500 }));

    await expect(api[method]("goal")).rejects.toThrow(OnboardingUnavailableError);
  });

  test("мережа недоступна — OnboardingUnavailableError", async () => {
    const fetchFn = vi.fn<typeof fetch>(() => Promise.reject(new TypeError("fetch failed")));
    const api = createHttpOnboardingApi(createApiClient(fetchFn, "/api"));

    await expect(api[method]("goal")).rejects.toThrow(OnboardingUnavailableError);
  });
});
