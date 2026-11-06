// Без globals Testing Library сам не прибирає DOM між тестами одного файлу.
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(cleanup);

// jsdom не має ResizeObserver, а Radix (чекбокс у формі) стежить ним за розміром: порожня заглушка середовища.
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
globalThis.ResizeObserver ??= ResizeObserverStub;
