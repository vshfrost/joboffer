/** Спільне для тестів сторінок із блоком «Делегувати агенту»: на сторінці їх може бути кілька, розрізняє їх опис під заголовком. */
import { waitFor, within } from "@testing-library/react";
import { expect } from "vitest";

export const DELEGATE = { name: "Делегувати агенту" };

/** Скопійований без агентів промпт: підтвердження в блоці. */
export const COPIED = "Промпт скопійовано. Встав його у свій агент.";

/** Усі блоки в області (за замовчуванням — вся сторінка). */
export function delegateBlocks(container: HTMLElement = document.body): HTMLElement[] {
  return within(container).queryAllByRole("region", DELEGATE);
}

/** Блок із цим описом, якщо він уже на екрані. */
export function queryDelegate(description: string, container: HTMLElement = document.body) {
  const block = delegateBlocks(container).find((candidate) => within(candidate).queryByText(description) !== null);
  return block === undefined ? null : within(block);
}

/** Чекає блок «Делегувати агенту» з цим описом, коли текст запиту вже не вантажиться (кнопки доступні). */
export async function findDelegate(description: string, container: HTMLElement = document.body) {
  const block = await waitFor(() => {
    const found = queryDelegate(description, container);
    if (found === null) {
      throw new Error(`Нема блоку «Делегувати агенту» з описом «${description}»`);
    }
    return found;
  });
  const copy = block.getByRole("button", { name: "Копіювати промпт" }) as HTMLButtonElement;
  await waitFor(() => expect(copy.disabled).toBe(false));
  return block;
}
