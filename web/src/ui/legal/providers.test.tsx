import { renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { useLegalServices } from "./LegalServices";

// React друкує кинуту помилку хука в console.error: тут вона очікувана.
beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => undefined);
});
afterEach(() => {
  vi.restoreAllMocks();
});

test("useLegalServices без провайдера", () => {
  expect(() => renderHook(() => useLegalServices())).toThrow("Юридичні сторінки потребують LegalServicesProvider");
});
