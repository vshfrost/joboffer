/** Етап «Налаштувати профіль»: агента підключено, вибір «з агентом» чи «вручну»; ручний режим показує стан із сервера. */
import { within } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { CHATGPT, CLAUDE, CODEX, CURSOR } from "./agentsBackend";
import { openConnected } from "./firstStepsHarness";

const MANUAL = { name: /Налаштувати вручну/ };

describe("агента підключено", () => {
  test("заголовок і підпис з назвою агента", async () => {
    const { card } = await openConnected([CLAUDE]);

    expect(within(card).getByRole("heading", { level: 3, name: "Агента підключено" })).toBeDefined();
    expect(await within(card).findByText(/Ваш Claude готовий допомогти\./)).toBeDefined();
  });

  test("підключено кілька агентів — називаємо того, кого обрано на першому етапі, інакше першого", async () => {
    const { card } = await openConnected([CODEX, CHATGPT]);

    expect(await within(card).findByText(/Ваш Codex готовий допомогти\./)).toBeDefined();
  });

  test.each([
    ["агент kind «other»", [CURSOR]],
    ["список агентів порожній", []],
    ["список агентів недоступний", "fail" as const],
  ])("%s — «MCP працює. Назву агента не визначено.»", async (_name, agents) => {
    const { card } = await openConnected(agents);

    expect(await within(card).findByText(/MCP працює\. Назву агента не визначено\./)).toBeDefined();
    expect(within(card).queryByText(/готовий допомогти/)).toBeNull();
  });

  test("пропозиція вибору: «Завершити з агентом» і «Налаштувати вручну»", async () => {
    const { card } = await openConnected([CLAUDE]);

    expect(within(card).getByRole("button", { name: /Завершити з агентом/ })).toBeDefined();
    expect(within(card).getByRole("button", MANUAL)).toBeDefined();
  });

  test("вибір способу лише в клієнті: на сервер нічого не йде", async () => {
    const { card, user, backend } = await openConnected([CLAUDE]);

    await user.click(within(card).getByRole("button", MANUAL));
    await user.click(within(card).getByRole("button", { name: /Продовжити з агентом/ }));

    expect(backend.calls).toEqual(["GET /api/onboarding"]);
  });
});

describe("вручну", () => {
  const ITEMS = [
    ["Задати ціль пошуку", "/profile/target"],
    ["Додати локації", "/profile/locations"],
    ["Заповнити контакти для CV", "/profile/contacts"],
    ["Додати оригінальне CV", "/facts"],
  ] as const;

  async function openManual(done: readonly string[] = ["claude"]) {
    const opened = await openConnected([CLAUDE], done);
    await opened.user.click(within(opened.card).getByRole("button", MANUAL));
    return opened;
  }

  test("рівно чотири пункти: ціль, локації, контакти для CV, оригінальне CV", async () => {
    const { card } = await openManual();

    const items = within(within(card).getByRole("list", { name: "Налаштування профілю" })).getAllByRole("listitem");
    expect(items.map((item) => ITEMS.find(([title]) => item.textContent.includes(title))?.[0])).toEqual(ITEMS.map(([title]) => title));
  });

  test.each(ITEMS)("«%s» веде на %s", async (title, href) => {
    const { card } = await openManual();

    expect(within(card).getByRole("link", { name: title }).getAttribute("href")).toBe(href);
  });

  test("стан кожного пункту береться з сервера: зроблені — «Готово», решта — «Заповнити»", async () => {
    const { card } = await openManual(["claude", "goal", "original_cv"]);

    const state = (title: string) => within(within(card).getByRole("link", { name: title }).closest("li") as HTMLElement);
    expect(state("Задати ціль пошуку").getByText("Готово")).toBeDefined();
    expect(state("Додати оригінальне CV").getByText("Готово")).toBeDefined();
    expect(state("Додати локації").getByText("Заповнити")).toBeDefined();
    expect(state("Заповнити контакти для CV").getByText("Заповнити")).toBeDefined();
  });

  test("прапорців, які перемикає користувач, нема", async () => {
    const { card } = await openManual(["claude", "goal"]);

    expect(within(card).queryAllByRole("checkbox")).toEqual([]);
  });

  test("лічильник «N із 5 виконано» за обов'язковими кроками сервера, необов'язкові не рахуються", async () => {
    const { card } = await openManual(["claude", "goal", "locations", "photo", "mail"]);

    expect(within(card).getByText("3 із 5 виконано")).toBeDefined();
    expect(within(card).queryByText(/Крок \d із 3/)).toBeNull();
  });

  test("додаткові можливості: фото й пошта можна пізніше, не пунктами", async () => {
    const { card } = await openManual();

    expect(within(card).getByText("Додаткові можливості")).toBeDefined();
    expect(within(card).getByText("Фото для CV · Підключення пошти · Можна пізніше")).toBeDefined();
    expect(within(card).queryByRole("link", { name: "Додати фото для CV" })).toBeNull();
    expect(within(card).queryByRole("link", { name: "Підключити пошту" })).toBeNull();
  });

  test("«Продовжити з агентом» повертає до блоку «Делегувати агенту»", async () => {
    const { card, user } = await openManual();

    await user.click(within(card).getByRole("button", { name: /Продовжити з агентом/ }));

    expect(await within(card).findByRole("region", { name: "Делегувати агенту" })).toBeDefined();
    expect(within(card).queryByRole("list", { name: "Налаштування профілю" })).toBeNull();
  });
});

describe("з агентом", () => {
  test("«Завершити з агентом» показує блок «Делегувати агенту», лічильник лишається «Крок 2 із 3»", async () => {
    const { card, user } = await openConnected([CLAUDE]);

    await user.click(within(card).getByRole("button", { name: /Завершити з агентом/ }));

    expect(await within(card).findByRole("region", { name: "Делегувати агенту" })).toBeDefined();
    expect(within(card).getByText("Крок 2 із 3")).toBeDefined();
  });

  test("з цього режиму можна перейти до ручного", async () => {
    const { card, user } = await openConnected([CLAUDE]);
    await user.click(within(card).getByRole("button", { name: /Завершити з агентом/ }));

    await user.click(within(card).getByRole("button", MANUAL));

    expect(within(card).getByRole("list", { name: "Налаштування профілю" })).toBeDefined();
    expect(within(card).queryByRole("region", { name: "Делегувати агенту" })).toBeNull();
  });
});
