/** Захисна перевірка провайдера онбордингу: хук без провайдера кидає зрозумілу помилку. */
import { renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { useOnboardingServices } from "./OnboardingServices";

// React друкує кинуту помилку хука в console.error: тут вона очікувана.
beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => undefined);
});
afterEach(() => {
  vi.restoreAllMocks();
});

test("useOnboardingServices без провайдера", () => {
  expect(() => renderHook(() => useOnboardingServices())).toThrow("useOnboardingServices потребує OnboardingServicesProvider");
});
