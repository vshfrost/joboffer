import type { Launch } from "../../domain/agents";

/** Єдине місце, де сторінка відкриває агента: рідне посилання застосунку чи нова вкладка вебагента. */
export function launchAgent(launch: Launch): void {
  if (launch.how === "open") {
    window.open(launch.url, "_blank", "noopener");
    return;
  }
  // Посилання-якір, а не iframe: так браузер питає дозвіл відкрити застосунок і не ламає поточну сторінку.
  const anchor = document.createElement("a");
  anchor.href = launch.url;
  anchor.click();
}
