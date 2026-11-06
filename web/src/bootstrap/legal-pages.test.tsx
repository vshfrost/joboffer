import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { fakeBackend, json, MEANS_LOGGED_IN, renderClient } from "./testClient";

const NOT_AUTHENTICATED = { code: "not_authenticated", message: "Потрібен вхід", field_errors: [], correlation_id: "c1" };
const ANONYMOUS = { "GET /api/auth/me": () => json(401, NOT_AUTHENTICATED) };

const TERMS = { doc: "terms", version: "2026-10-28.1", text: "1. Загальні умови\nСервіс особистий.\n\n2. Відповідальність\nЯк є." };
const PRIVACY = { doc: "privacy", version: "2026-10-28.3", text: "1. Дані\nДані видаляємо на запит." };

const location = () => screen.getByTestId("location").textContent;

describe("сторінки умов і політики", () => {
  test("/terms без сесії показує умови: заголовок, версію й текст", async () => {
    renderClient("/terms", fakeBackend({ ...ANONYMOUS, "GET /api/legal/terms": () => json(200, TERMS) }));

    await screen.findByRole("heading", { level: 1, name: "Умови користування" });
    expect(location()).toBe("/terms");
    expect(screen.getByText("Версія 2026-10-28.1")).toBeDefined();
    expect(screen.getByTestId("legal-text").textContent).toBe(TERMS.text);
  });

  test("/privacy без сесії показує політику конфіденційності", async () => {
    renderClient("/privacy", fakeBackend({ ...ANONYMOUS, "GET /api/legal/privacy": () => json(200, PRIVACY) }));

    await screen.findByRole("heading", { level: 1, name: "Політика конфіденційності" });
    expect(screen.getByText("Версія 2026-10-28.3")).toBeDefined();
    expect(screen.getByTestId("legal-text").textContent).toContain("Дані видаляємо на запит.");
  });

  test("із сесією сторінка теж відкривається, без переходу на вхід", async () => {
    renderClient("/terms", fakeBackend({ ...MEANS_LOGGED_IN, "GET /api/legal/terms": () => json(200, TERMS) }));

    await screen.findByRole("heading", { level: 1, name: "Умови користування" });
    expect(location()).toBe("/terms");
  });

  test("текст у відповіді рендериться як текст, а не як HTML", async () => {
    const hostile = { ...TERMS, text: "<script>window.hacked = 1</script><b>жирний</b> **зірки**" };
    renderClient("/terms", fakeBackend({ ...ANONYMOUS, "GET /api/legal/terms": () => json(200, hostile) }));

    const text = await screen.findByTestId("legal-text");
    expect(text.textContent).toBe(hostile.text);
    expect(text.querySelector("script, b")).toBeNull();
  });

  test("на вузькому екрані (375 px) текст переноситься і зберігає абзаци, а контейнер не ширший за екран", async () => {
    renderClient("/terms", fakeBackend({ ...ANONYMOUS, "GET /api/legal/terms": () => json(200, TERMS) }));

    const text = await screen.findByTestId("legal-text");
    expect(text.className).toContain("whitespace-pre-wrap");
    expect(text.className).toContain("break-words");
    const page = screen.getByRole("main");
    expect(page.className).toContain("w-full");
    expect(page.className).toContain("max-w-3xl");
    expect(page.className).toContain("px-4");
  });

  test("поки текст вантажиться, показує статус завантаження", async () => {
    const pending = new Promise<Response>(() => undefined);
    renderClient("/terms", fakeBackend({ ...ANONYMOUS, "GET /api/legal/terms": () => pending as unknown as Response }));

    expect((await screen.findByRole("status")).textContent).toContain("Завантаження");
    expect(location()).toBe("/terms");
    expect(screen.getByRole("heading", { level: 1, name: "Умови користування" })).toBeDefined();
  });

  test("сервер недоступний — повідомлення і «Спробувати ще раз», який вантажить знову", async () => {
    const user = userEvent.setup();
    let calls = 0;
    const legal = () => (++calls === 1 ? json(500, {}) : json(200, TERMS));
    renderClient("/terms", fakeBackend({ ...ANONYMOUS, "GET /api/legal/terms": legal }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Не вдалося завантажити текст");
    await user.click(within(alert).getByRole("button", { name: "Спробувати ще раз" }));

    await screen.findByRole("heading", { level: 1, name: "Умови користування" });
    expect(screen.getByTestId("legal-text").textContent).toBe(TERMS.text);
  });

  test("мережевий збій — теж повідомлення про недоступність", async () => {
    const down = () => Promise.reject(new Error("offline")) as unknown as Response;
    renderClient("/privacy", fakeBackend({ ...ANONYMOUS, "GET /api/legal/privacy": down }));

    expect((await screen.findByRole("alert")).textContent).toContain("Не вдалося завантажити текст");
  });

  test("відповідь не за контрактом — повідомлення про недоступність", async () => {
    renderClient("/terms", fakeBackend({ ...ANONYMOUS, "GET /api/legal/terms": () => json(200, { doc: "terms" }) }));

    expect((await screen.findByRole("alert")).textContent).toContain("Не вдалося завантажити текст");
  });

  test("404 від сервера — документ не знайдено", async () => {
    renderClient("/terms", fakeBackend({ ...ANONYMOUS, "GET /api/legal/terms": () => json(404, {}) }));

    expect((await screen.findByRole("alert")).textContent).toContain("Документ не знайдено");
  });

  test("заголовок вкладки — назва документа", async () => {
    renderClient("/privacy", fakeBackend({ ...ANONYMOUS, "GET /api/legal/privacy": () => json(200, PRIVACY) }));

    await screen.findByRole("heading", { level: 1, name: "Політика конфіденційності" });
    expect(document.title).toBe("Політика конфіденційності · joboffer");
  });

  test("зі сторінки є шлях назад", async () => {
    renderClient("/terms", fakeBackend({ ...ANONYMOUS, "GET /api/legal/terms": () => json(200, TERMS) }));

    const back = await screen.findByRole("link", { name: "На головну" });
    expect(back.getAttribute("href")).toBe("/");
  });
});

describe("посилання на умови зі сторінки входу", () => {
  test("форма входу веде на /terms і /privacy", async () => {
    renderClient("/login", fakeBackend({ ...ANONYMOUS, "GET /api/auth/providers": () => json(200, { google: false }) }));

    await screen.findByRole("heading", { level: 1, name: "Вхід" });
    expect(screen.getByRole("link", { name: "Умови користування" }).getAttribute("href")).toBe("/terms");
    expect(screen.getByRole("link", { name: "Політика конфіденційності" }).getAttribute("href")).toBe("/privacy");
  });
});
