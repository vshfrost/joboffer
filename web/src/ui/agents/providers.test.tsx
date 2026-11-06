/** Захисна перевірка провайдера агентів: хук без провайдера кидає зрозумілу помилку. */
import { renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { useAgents } from "./AgentsServices";

// React друкує кинуту помилку хука в console.error: тут вона очікувана.
beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => undefined);
});
afterEach(() => {
  vi.restoreAllMocks();
});

test("useAgents без провайдера", () => {
  expect(() => renderHook(() => useAgents())).toThrow("useAgents потребує AgentsServicesProvider");
});
