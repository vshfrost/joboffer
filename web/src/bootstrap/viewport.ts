/** Ширина вікна для тестів: jsdom не має `matchMedia`, тож без виклику `setViewport` застосунок вважає екран широким. */
import { afterEach, vi } from "vitest";

const WIDTHS = { desktop: 1280, mobile: 375 } as const;

function matchesMinWidth(query: string, width: number): boolean {
  const found = /\(min-width:\s*([\d.]+)(rem|px)\)/.exec(query);
  if (found === null) {
    return false;
  }
  const value = Number(found[1]) * (found[2] === "rem" ? 16 : 1);
  return width >= value;
}

export function setViewport(kind: keyof typeof WIDTHS): void {
  const width = WIDTHS[kind];
  vi.stubGlobal(
    "matchMedia",
    (query: string): MediaQueryList =>
      ({
        matches: matchesMinWidth(query, width),
        media: query,
        addEventListener: () => {},
        removeEventListener: () => {},
      }) as unknown as MediaQueryList,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});
