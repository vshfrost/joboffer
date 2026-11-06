import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { fakeBackend, MEANS_LOGGED_IN, renderClient } from "./testClient";

/** Оболонка з'являється, коли `GET /api/auth/me` підтвердив сесію. */
async function renderAt(path: string) {
  renderClient(path, fakeBackend(MEANS_LOGGED_IN));
  await screen.findByRole("navigation", { name: "Головна навігація" });
}

const SECTIONS = [
  { label: "Вакансії", path: "/vacancies" },
  { label: "Факти", path: "/facts" },
  { label: "Відповіді", path: "/replies" },
  { label: "Підготовка", path: "/prep" },
  { label: "Джерела", path: "/sources" },
  { label: "Профіль", path: "/profile" },
];

describe("оболонка", () => {
  test("головна навігація веде в усі розділи", async () => {
    await renderAt("/vacancies");
    const nav = screen.getByRole("navigation", { name: "Головна навігація" });
    for (const { label, path } of SECTIONS) {
      expect(within(nav).getByRole("link", { name: label }).getAttribute("href")).toBe(path);
    }
  });

  test("поточний розділ позначено aria-current, решта — ні", async () => {
    await renderAt("/facts");
    const nav = screen.getByRole("navigation", { name: "Головна навігація" });
    const current = within(nav)
      .getAllByRole("link")
      .filter((link) => link.getAttribute("aria-current") === "page");
    expect(current.map((link) => link.textContent)).toEqual(["Факти"]);
  });

  test("бренд-посилання веде на головну", async () => {
    await renderAt("/facts");
    expect(screen.getByRole("link", { name: "joboffer" }).getAttribute("href")).toBe("/");
  });

  test("кореневий шлях відкриває вакансії", async () => {
    await renderAt("/");
    expect(await screen.findByRole("heading", { level: 1, name: "Вакансії" })).toBeDefined();
  });

  test("невідомий маршрут показує «не знайдено» в тій самій оболонці", async () => {
    await renderAt("/nope");
    expect(screen.getByRole("heading", { level: 1, name: "Сторінку не знайдено" })).toBeDefined();
    expect(screen.getByRole("link", { name: "До вакансій" }).getAttribute("href")).toBe("/vacancies");
    expect(screen.getByRole("navigation", { name: "Головна навігація" })).toBeDefined();
  });

  test("заголовок вкладки відповідає розділу", async () => {
    await renderAt("/facts");
    expect(document.title).toBe("Факти · joboffer");
  });

  test("заголовок вкладки для невідомого маршруту", async () => {
    await renderAt("/nope");
    expect(document.title).toBe("Не знайдено · joboffer");
  });

  test("перше, що отримує клавіатура, — посилання «Перейти до змісту», яке веде в main", async () => {
    const user = userEvent.setup();
    await renderAt("/vacancies");
    await user.tab();
    const skip = screen.getByRole("link", { name: "Перейти до змісту" });
    expect(document.activeElement).toBe(skip);
    expect(skip.getAttribute("href")).toBe("#content");
    expect(screen.getByRole("main").getAttribute("id")).toBe("content");
  });

  test("хлібні крихти показують розділ", async () => {
    await renderAt("/profile");
    const crumbs = screen.getByRole("navigation", { name: "Хлібні крихти" });
    expect(crumbs.textContent).toContain("Профіль");
  });
});

describe("мобільне меню", () => {
  test("відкривається кнопкою, містить навігацію й закривається вибором розділу", async () => {
    const user = userEvent.setup();
    await renderAt("/vacancies");
    expect(screen.queryByRole("dialog")).toBeNull();

    await user.click(screen.getByRole("button", { name: "Відкрити навігацію" }));
    const dialog = screen.getByRole("dialog", { name: "Навігація" });
    await user.click(within(dialog).getByRole("link", { name: "Профіль" }));

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("heading", { level: 1, name: "Профіль" })).toBeDefined();
  });

  test("Escape закриває меню", async () => {
    const user = userEvent.setup();
    await renderAt("/vacancies");
    await user.click(screen.getByRole("button", { name: "Відкрити навігацію" }));
    expect(screen.getByRole("dialog", { name: "Навігація" })).toBeDefined();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
