/** Панель «Фільтри» у тестах списку вакансій: відкрити, обрати значення, застосувати. */
import { screen, within } from "@testing-library/react";
import type { UserEvent } from "@testing-library/user-event";

export type FilterLabel = "Свіжість" | "Джерело" | "Статус подачі" | "Вердикт тріажу" | "Формат";

export const filtersButton = () => screen.getByRole("button", { name: /^Фільтри/ });

export async function openFilters(user: UserEvent) {
  if (filtersButton().getAttribute("aria-expanded") !== "true") {
    await user.click(filtersButton());
  }
  return screen.getByRole("region", { name: "Фільтри вакансій" });
}

/** Вибирає значення в панелі й тисне «Застосувати фільтри»; значення — текст варіанта або його value. */
export async function applyFilters(user: UserEvent, values: Partial<Record<FilterLabel, string>>) {
  const panel = await openFilters(user);
  for (const [label, value] of Object.entries(values)) {
    await user.selectOptions(within(panel).getByRole("combobox", { name: label }), value);
  }
  await user.click(within(panel).getByRole("button", { name: "Застосувати фільтри" }));
}

/** Умови, що показані чипами під панеллю. */
export const chips = () => {
  const list = screen.queryByRole("list", { name: "Активні фільтри" });
  return list === null ? [] : within(list).getAllByRole("listitem").map((item) => item.textContent?.trim());
};
