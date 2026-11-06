import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { EMPTY_PROFILE, FULL_PROFILE, profileBackend, type ApiProfile } from "./profileBackend";
import { fakeBackend, json, MEANS_LOGGED_IN, renderClient } from "./testClient";

async function openOverview(profile: ApiProfile = FULL_PROFILE) {
  const backend = profileBackend(profile);
  renderClient("/profile", backend.fetchFn);
  await screen.findByRole("link", { name: /Кар’єрна ціль/ });
  return backend;
}

function card(title: RegExp | string) {
  const heading = screen.getByRole("heading", { level: 2, name: title });
  const cardElement = heading.closest("li");
  if (cardElement === null) {
    throw new Error(`Картка «${String(title)}» не в списку`);
  }
  return cardElement;
}

describe("огляд профілю", () => {
  test("має заголовок, підзаголовок і назву вкладки", async () => {
    await openOverview();
    expect(screen.getByRole("heading", { level: 1, name: "Профіль" })).toBeDefined();
    expect(screen.getByText("Усе важливе — в огляді. Деталі — у своєму розділі.")).toBeDefined();
    expect(document.title).toBe("Профіль · joboffer");
  });

  test("показує шість карток у фіксованому порядку", async () => {
    await openOverview();
    const titles = screen.getAllByRole("heading", { level: 2 }).map((heading) => heading.textContent);
    expect(titles).toEqual([
      "Кар’єрна ціль",
      "Локації та формат",
      "Правила відбору",
      "Контакти для CV",
      "Фото для CV",
      "Пошта",
    ]);
  });

  test("чотири картки ведуть у свої розділи", async () => {
    await openOverview();
    const hrefs = Object.fromEntries(
      ["Кар’єрна ціль", "Локації та формат", "Правила відбору", "Контакти для CV"].map((title) => [
        title,
        within(card(title)).getByRole("link").getAttribute("href"),
      ]),
    );
    expect(hrefs).toEqual({
      "Кар’єрна ціль": "/profile/target",
      "Локації та формат": "/profile/locations",
      "Правила відбору": "/profile/rules",
      "Контакти для CV": "/profile/contacts",
    });
  });

  test("картка «Пошта» веде до пошти: вхідні, адреса для пересилання й синк", async () => {
    await openOverview();
    const element = card("Пошта");
    expect(within(element).queryByText("З’явиться пізніше")).toBeNull();
    expect(within(element).getByText("Вхідні, адреса для пересилання та синк")).toBeDefined();
    expect(within(element).getByText("Переслані листи рекрутерів і код підтвердження Gmail")).toBeDefined();
    expect(within(element).getByText("Відкрити пошту")).toBeDefined();
    expect(within(element).getByRole("link").getAttribute("href")).toBe("/profile/mail");
  });

  test("картки показують дані профілю коротко", async () => {
    await openOverview();
    expect(card("Кар’єрна ціль").textContent).toContain("Backend Engineer · SRE");
    expect(card("Кар’єрна ціль").textContent).toContain("Senior, Lead · від 65 000 € брутто / рік");
    expect(card("Локації та формат").textContent).toContain("Valencia · Hybrid");
    expect(card("Локації та формат").textContent).toContain("Madrid · Remote, Офіс");
    expect(card("Правила відбору").textContent).toContain("1 слово для пошуку · 2 виключення · 1 стоп-слово");
    expect(card("Контакти для CV").textContent).toContain("Test User");
    expect(card("Контакти для CV").textContent).toContain("user@example.com");
  });

  test("порожній профіль — порожні стани карток", async () => {
    await openOverview(EMPTY_PROFILE);
    expect(card("Кар’єрна ціль").textContent).toContain("Ціль ще не задано");
    expect(card("Локації та формат").textContent).toContain("Локації ще не додано");
    expect(card("Правила відбору").textContent).toContain("Правила ще не задано");
    expect(card("Контакти для CV").textContent).toContain("Контакти не вказано");
  });

  test("50 ролей не розтягують картку: видно дві й «ще 48»", async () => {
    const roles = Array.from({ length: 50 }, (_, index) => `Role ${index + 1}`);
    await openOverview({ ...FULL_PROFILE, target: { ...FULL_PROFILE.target, roles } });
    const text = card("Кар’єрна ціль").textContent ?? "";
    expect(text).toContain("Role 1 · Role 2 · ще 48");
    expect(text).not.toContain("Role 3");
  });

  test("довге ім’я в контактах не губиться в картці", async () => {
    const longName = "N".repeat(200);
    await openOverview({ ...FULL_PROFILE, contacts: { ...FULL_PROFILE.contacts, full_name: longName } });
    expect(card("Контакти для CV").textContent).toContain(longName);
  });

  test("картка відкриває розділ: адреса й заголовок", async () => {
    const user = userEvent.setup();
    await openOverview();
    await user.click(within(card("Кар’єрна ціль")).getByRole("link"));
    expect(screen.getByTestId("location").textContent).toBe("/profile/target");
    expect(await screen.findByRole("heading", { level: 1, name: "Кар’єрна ціль" })).toBeDefined();
  });
});

describe("огляд: людина й завантаження, що не дочекались", () => {
  test("без ролі й міста під іменем нічого немає", async () => {
    await openOverview(EMPTY_PROFILE);
    const name = within(screen.getByRole("main")).getByText("Богдан Прикладенко");
    expect(name.parentElement?.querySelectorAll("p")).toHaveLength(1);
  });

  test("з роллю й містом під іменем — «роль · місто»", async () => {
    await openOverview();
    expect(within(screen.getByRole("main")).getByText("Backend Engineer · Valencia, Spain")).toBeDefined();
  });

  test("відповідь, що прийшла після виходу зі сторінки, нічого не ламає", async () => {
    let finish: (response: Response) => void = () => undefined;
    const pending = new Promise<Response>((resolve) => {
      finish = resolve;
    });
    const errors = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const view = renderClient("/profile", fakeBackend({ ...MEANS_LOGGED_IN, "GET /api/profile": () => pending }));
    await screen.findByText("Завантажуємо профіль…");
    view.unmount();
    finish(json(200, FULL_PROFILE));
    await pending;
    expect(errors).not.toHaveBeenCalled();
    errors.mockRestore();
  });
});

describe("завантаження профілю", () => {
  test("поки профіль вантажиться, показує статус завантаження", async () => {
    let finish: (response: Response) => void = () => undefined;
    const pending = new Promise<Response>((resolve) => {
      finish = resolve;
    });
    renderClient(
      "/profile",
      fakeBackend({ ...MEANS_LOGGED_IN, "GET /api/profile": () => pending }),
    );
    // Спершу ще йде перевірка сесії зі своїм статусом: чекаємо саме на завантаження профілю.
    const loading = await screen.findByText("Завантажуємо профіль…");
    expect(loading.getAttribute("role")).toBe("status");
    expect(screen.queryByRole("heading", { level: 2, name: "Кар’єрна ціль" })).toBeNull();
    finish(json(200, EMPTY_PROFILE));
    expect(await screen.findByRole("heading", { level: 2, name: "Кар’єрна ціль" })).toBeDefined();
  });

  test.each([
    ["сервер відповів 500", () => Promise.resolve(json(500, { code: "internal_error" }))],
    ["мережа недоступна", () => Promise.reject(new TypeError("fetch failed"))],
    ["відповідь не за контрактом", () => Promise.resolve(json(200, { target: 1 }))],
  ])("помилка завантаження (%s) — повідомлення з повтором", async (_name, failure) => {
    const user = userEvent.setup();
    let attempts = 0;
    renderClient(
      "/profile",
      fakeBackend({
        ...MEANS_LOGGED_IN,
        "GET /api/profile": () => {
          attempts += 1;
          return attempts === 1 ? failure() : json(200, FULL_PROFILE);
        },
      }),
    );
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Не вдалося завантажити профіль");
    await user.click(within(alert).getByRole("button", { name: "Спробувати ще раз" }));
    expect(await screen.findByRole("heading", { level: 2, name: "Кар’єрна ціль" })).toBeDefined();
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    expect(attempts).toBe(2);
  });
});
