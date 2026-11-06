import { describe, expect, test, vi } from "vitest";

import type { Onboarding } from "../domain/onboarding";
import { OnboardingUnavailableError } from "../domain/onboardingErrors";
import type { OnboardingApi } from "../ports/onboardingApi";
import { createOnboardingServices } from "./onboarding";

const ONBOARDING: Onboarding = {
  steps: [{ key: "goal", done: true, optional: false }],
  tips: [{ key: "goal", seen: true, dismissed: false }],
  complete: false,
};

function fakeApi(overrides: Partial<OnboardingApi> = {}) {
  const api = {
    get: vi.fn<OnboardingApi["get"]>(() => Promise.resolve(ONBOARDING)),
    markSeen: vi.fn<OnboardingApi["markSeen"]>(() => Promise.resolve()),
    dismiss: vi.fn<OnboardingApi["dismiss"]>(() => Promise.resolve()),
    ...overrides,
  };
  return { api, services: createOnboardingServices(api) };
}

const unavailable = () => Promise.reject(new OnboardingUnavailableError("збій"));
const unexpected = () => Promise.reject(new TypeError("помилка програмування"));

describe("load", () => {
  test("віддає онбординг із порту", async () => {
    const { services } = fakeApi();
    expect(await services.load()).toEqual({ ok: true, onboarding: ONBOARDING });
  });

  test("недоступний сервер — не успіх, без винятку", async () => {
    const { services } = fakeApi({ get: unavailable });
    expect(await services.load()).toEqual({ ok: false });
  });

  test("несподівана помилка не ховається", async () => {
    const { services } = fakeApi({ get: unexpected });
    await expect(services.load()).rejects.toThrow("помилка програмування");
  });
});

describe("markSeen", () => {
  test("передає ключ підказки порту", async () => {
    const { api, services } = fakeApi();
    await services.markSeen("claude");
    expect(api.markSeen).toHaveBeenCalledExactlyOnceWith("claude");
  });

  test("збій сервера гаситься: підказку це не ламає", async () => {
    const { services } = fakeApi({ markSeen: unavailable });
    await expect(services.markSeen("claude")).resolves.toBeUndefined();
  });

  test("несподівана помилка не ховається", async () => {
    const { services } = fakeApi({ markSeen: unexpected });
    await expect(services.markSeen("claude")).rejects.toThrow("помилка програмування");
  });
});

describe("dismiss", () => {
  test("передає ключ підказки порту й повідомляє про успіх", async () => {
    const { api, services } = fakeApi();
    expect(await services.dismiss("claude")).toEqual({ ok: true });
    expect(api.dismiss).toHaveBeenCalledExactlyOnceWith("claude");
  });

  test("збій сервера — не успіх", async () => {
    const { services } = fakeApi({ dismiss: unavailable });
    expect(await services.dismiss("claude")).toEqual({ ok: false });
  });

  test("несподівана помилка не ховається", async () => {
    const { services } = fakeApi({ dismiss: unexpected });
    await expect(services.dismiss("claude")).rejects.toThrow("помилка програмування");
  });
});
