/** Спільне для тестів маршруту «Перші кроки»: хаб профілю з онбордингом і підключеними агентами. */
import { waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, vi } from "vitest";

import { connectAgents, type ApiAgent } from "./agentsBackend";
import { onboardingBackend, openHubWithOnboarding, type OnboardingBackend, type OnboardingState } from "./onboardingBackend";
import { connectPrompts, PROMPTS, type PromptsReply } from "./promptsBackend";

export const ADDRESS = "http://localhost:3000/mcp";

/** Картка «Перші кроки» зі станом сервера, списком агентів (`"fail"` — /api/agents не відповідає) і текстами запитів (`"fail"` — /api/prompts не відповідає, `"hang"` — не завершується). */
export async function openCard(
  state: OnboardingState = {},
  agents: readonly ApiAgent[] | "fail" = [],
  backend: OnboardingBackend = onboardingBackend(state),
  prompts: PromptsReply = PROMPTS,
) {
  const stub = connectAgents(backend, agents);
  const promptsStub = connectPrompts(backend, prompts);
  const opened = await openHubWithOnboarding(backend);
  return { ...opened, backend, stub, promptsStub };
}

/** Агент підключено (крок claude зроблено): картка на етапі «Налаштувати профіль». */
export function openConnected(agents: readonly ApiAgent[] | "fail", done: readonly string[] = ["claude"], prompts: PromptsReply = PROMPTS) {
  return openCard({ done }, agents, undefined, prompts);
}

/** Клієнт для кліків і буфер обміну: користувача створюємо після картки, бо userEvent.setup() ставить свою заглушку буфера. */
export function clipboardUser() {
  const user = userEvent.setup();
  const writeText = vi.spyOn(navigator.clipboard, "writeText");
  return { user, writeText };
}

/** Обирає «Завершити з агентом» і повертає блок «Делегувати агенту», коли тексти запитів уже не вантажаться. */
export async function openDelegate(card: HTMLElement, user: ReturnType<typeof userEvent.setup>) {
  await user.click(await within(card).findByRole("button", { name: /Завершити з агентом/ }));
  const block = within(await within(card).findByRole("region", { name: "Делегувати агенту" }));
  const copy = block.getByRole("button", { name: "Копіювати промпт" }) as HTMLButtonElement;
  await waitFor(() => expect(copy.disabled).toBe(false));
  return block;
}
