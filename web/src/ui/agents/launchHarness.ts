/** Спільне для тестів запуску агентів: межа браузера (рідні посилання й нова вкладка) підміняється двійником. */
import { vi, type MockInstance } from "vitest";

export interface LaunchSpy {
  /** Адреси рідних посилань (claude://, codex://), на які перейшли, у порядку переходів. */
  navigations: string[];
  /** `window.open`: нова вкладка для вебагентів. */
  open: MockInstance<typeof window.open>;
}

/** Підміняє перехід за посиланням і `window.open`; знімається `vi.restoreAllMocks()`. */
export function spyLaunch(): LaunchSpy {
  const navigations: string[] = [];
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
    navigations.push(this.href);
  });
  const open = vi.spyOn(window, "open").mockImplementation(() => null);
  return { navigations, open };
}
