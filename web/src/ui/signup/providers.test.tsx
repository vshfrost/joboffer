import { renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { useSignup } from "./SignupServices";

// React друкує кинуту помилку хука в console.error: тут вона очікувана.
beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => undefined);
});
afterEach(() => {
  vi.restoreAllMocks();
});

test("useSignup без провайдера", () => {
  expect(() => renderHook(() => useSignup())).toThrow("Реєстрація потребує SignupServicesProvider");
});
