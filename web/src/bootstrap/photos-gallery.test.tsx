/** Галерея фото в хабі профілю: стани, картки фото, дати за Мадридом, пропозиція для CV. */
import { screen, within } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { apiPhoto } from "./photosBackend";
import { openEditor } from "./photosHarness";

const OFFICE = apiPhoto(1, { label: "Ділове", created_at: "2026-10-21T09:00:00Z" });
const CASUAL = apiPhoto(2, { label: "Неформальне", created_at: "2026-10-21T22:30:00Z", last_used_at: "2026-10-22T08:00:00Z" });

function gallery() {
  return within(screen.getByRole("list", { name: "Збережені фото" }));
}

describe("відкриття розділу", () => {
  test("заголовок, підзаголовок, назва вкладки й меню розділів", async () => {
    await openEditor([OFFICE]);

    expect(screen.getByText("Профіль / Фото для CV")).toBeDefined();
    expect(document.title).toBe("Фото для CV · Профіль · joboffer");
    const nav = within(screen.getByRole("navigation", { name: "Розділи профілю" }));
    expect(nav.getAllByRole("link").map((link) => link.textContent)).toEqual([
      "← Огляд профілю",
      "Кар’єрна ціль",
      "Локації та формат",
      "Правила відбору",
      "Контакти для CV",
      "Фото для CV",
    ]);
    expect(nav.getByRole("link", { name: "Фото для CV" }).getAttribute("aria-current")).toBe("page");
  });

  test("мобільне меню розділів має й «Фото для CV»", async () => {
    await openEditor([OFFICE]);

    const select = screen.getByRole("combobox", { name: "Розділ профілю" });
    expect(within(select).getByRole("option", { name: "Фото для CV" })).toBeDefined();
    expect((select as HTMLSelectElement).value).toBe("photos");
  });

  test("пряме відкриття /profile/photos працює й повертається в огляд", async () => {
    const { user } = await openEditor([OFFICE]);

    await user.click(screen.getByRole("link", { name: /Огляд профілю/ }));

    expect(await screen.findByRole("heading", { level: 1, name: "Профіль" })).toBeDefined();
  });
});

describe("стани", () => {
  test("завантаження: статус, а не порожня галерея", async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const { backend } = await openEditor(
      [OFFICE],
      { list: () => gate.then(() => new Response(JSON.stringify({ photos: [OFFICE], suggested_photo_id: 1 }), { status: 200 })) },
      false,
    );

    expect(screen.getByRole("status", { name: "Завантажуємо фото…" })).toBeDefined();
    expect(screen.queryByText("Фото ще не додано")).toBeNull();
    release();

    expect(await screen.findByRole("list", { name: "Збережені фото" })).toBeDefined();
    expect(backend.listRequests).toBe(1);
  });

  test("помилка списку: повідомлення й повтор", async () => {
    let failing = true;
    const { backend, user } = await openEditor([OFFICE], { list: () => (failing ? new Response("{}", { status: 500 }) : undefined) });

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Не вдалося завантажити фото.");
    failing = false;
    await user.click(within(alert).getByRole("button", { name: "Спробувати ще раз" }));

    expect(await screen.findByRole("list", { name: "Збережені фото" })).toBeDefined();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(backend.listRequests).toBe(2);
  });

  test("сесія завершилась: окреме повідомлення", async () => {
    await openEditor([OFFICE], { list: () => new Response("{}", { status: 401 }) });

    expect((await screen.findByRole("alert")).textContent).toContain("Сесія завершилась. Увійди знову, щоб побачити фото.");
  });

  test("порожньо: пояснення, що CV можна й без фото, і кнопка додавання", async () => {
    await openEditor([]);

    expect(await screen.findByRole("heading", { level: 3, name: "Фото ще не додано" })).toBeDefined();
    expect(screen.getByText("CV можна створювати й без фото.")).toBeDefined();
    expect(screen.getByRole("button", { name: "Додати фото" })).toBeDefined();
    expect(screen.queryByRole("list", { name: "Збережені фото" })).toBeNull();
  });
});

describe("картки фото", () => {
  test("одне фото: мініатюра з сервера, підпис, дата додавання, не використовувалось, пропонується", async () => {
    await openEditor([OFFICE]);

    const item = gallery().getAllByRole("listitem")[0] as HTMLElement;
    const image = within(item).getByRole("img", { name: "Фото «Ділове»" });
    expect(image.getAttribute("src")).toBe("/api/photos/1.jpg");
    expect(within(item).getByText("Ділове")).toBeDefined();
    expect(within(item).getByText("Додано 2026-10-21")).toBeDefined();
    expect(within(item).getByText("Ще не використовувалось")).toBeDefined();
    expect(within(item).getByText("Пропонується для CV")).toBeDefined();
  });

  test("багато фото: новіші першими, дати за Мадридом, позначка лише в пропонованого", async () => {
    await openEditor([OFFICE, CASUAL, apiPhoto(3, { created_at: "2026-10-20T09:00:00Z" })]);

    const items = gallery().getAllByRole("listitem");
    expect(items).toHaveLength(3);
    // Найновіше за часом — #2 (21-го о 22:30 UTC, у Мадриді вже 22-ге).
    expect(within(items[0] as HTMLElement).getByText("Неформальне")).toBeDefined();
    expect(within(items[0] as HTMLElement).getByText("Додано 2026-10-22")).toBeDefined();
    expect(within(items[0] as HTMLElement).getByText("У CV: 2026-10-22")).toBeDefined();
    expect(within(items[1] as HTMLElement).getByText("Ділове")).toBeDefined();
    const suggested = screen.getAllByText("Пропонується для CV");
    expect(suggested).toHaveLength(1);
    expect(items[0]?.contains(suggested[0] as HTMLElement)).toBe(true);
  });

  test("без використаних пропонується найновіше", async () => {
    await openEditor([OFFICE, apiPhoto(2, { label: "Нове", created_at: "2026-10-22T08:00:00Z" })]);

    const items = gallery().getAllByRole("listitem");
    expect(within(items[0] as HTMLElement).getByText("Пропонується для CV")).toBeDefined();
    expect(within(items[1] as HTMLElement).queryByText("Пропонується для CV")).toBeNull();
  });

  test("фото без підпису називається за номером", async () => {
    await openEditor([apiPhoto(7)]);

    const item = gallery().getAllByRole("listitem")[0] as HTMLElement;
    expect(within(item).getByText("Фото #7")).toBeDefined();
    expect(within(item).getByRole("img", { name: "Фото #7" })).toBeDefined();
  });

  test("довгий підпис не ламає картку: переноситься, а не виштовхує", async () => {
    const long = "Дуже-дуже-довге-ім'я-без-пробілів-".repeat(8);
    await openEditor([apiPhoto(1, { label: long })]);

    const name = gallery().getByText(long);
    expect(name.className).toContain("[overflow-wrap:anywhere]");
    expect(gallery().getAllByRole("listitem")[0]?.className).toContain("min-w-0");
  });

  test("сітка: одна колонка на вузькому екрані, більше на широкому", async () => {
    await openEditor([OFFICE, CASUAL]);

    const classes = screen.getByRole("list", { name: "Збережені фото" }).className;
    expect(classes).toContain("grid-cols-1");
    expect(classes).toMatch(/sm:grid-cols-2|md:grid-cols-2/);
  });

  test("анімації сторінки лише ті, що гасить prefers-reduced-motion", async () => {
    await openEditor([OFFICE]);

    const animated = [...document.querySelectorAll<HTMLElement>("[class*='animate-']")];
    // Єдина дозволена: пульсація скелета під час завантаження (її прибирає глобальне правило теми).
    expect(animated.filter((element) => element.getAttribute("aria-hidden") !== "true")).toEqual([]);
  });
});

test("тема гасить рух для prefers-reduced-motion", async () => {
  const theme = (await import("../ui/theme.css?raw")).default;

  expect(theme).toMatch(/@media \(prefers-reduced-motion: reduce\)[\s\S]*animation-duration: 0\.01ms !important[\s\S]*transition-duration: 0\.01ms !important/);
});
