/** Захисна перевірка: екрани відповідей не працюють без провайдера сервісів. */
import { renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { useRepliesServices } from "./RepliesServices";

// React друкує кинуту помилку хука в console.error: тут вона очікувана.
beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => undefined);
});
afterEach(() => {
  vi.restoreAllMocks();
});

test("без RepliesServicesProvider хук сервісів кидає зрозумілу помилку", () => {
  expect(() => renderHook(() => useRepliesServices())).toThrow("Відповіді потребують RepliesServicesProvider");
});
