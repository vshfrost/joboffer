/** Картка «Перші кроки» на /profile — маршрут з трьох етапів: етап береться з сервера, картка зникає, коли готові обов'язкові кроки. */
import { screen, within } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { CLAUDE } from "./agentsBackend";
import { openCard } from "./firstStepsHarness";
import { onboardingBackend, onboardingBody, REQUIRED_KEYS, settle, STEP_KEYS } from "./onboardingBackend";
import { FULL_PROFILE, profileBackend } from "./profileBackend";
import { fakeBackend, json, MEANS_LOGGED_IN, renderClient } from "./testClient";
import { setViewport } from "./viewport";

const STAGES = ["Підключити агента", "Налаштувати профіль", "Готово до пошуку"];

function stages(card: HTMLElement) {
  return within(within(card).getByRole("list", { name: "Маршрут" })).getAllByRole("listitem");
}

function current(card: HTMLElement) {
  return stages(card).filter((item) => item.getAttribute("aria-current") === "step");
}

describe("маршрут", () => {
  test("картка «Перші кроки» стоїть на /profile разом із картками профілю", async () => {
    const { card } = await openCard();

    expect(within(card).getByRole("heading", { level: 2, name: "Перші кроки" })).toBeDefined();
    expect(within(card).getByText("ВАШ СТАРТ У JOBOFFER")).toBeDefined();
    expect(screen.getByRole("heading", { level: 2, name: "Кар’єрна ціль" })).toBeDefined();
    expect(screen.getByRole("heading", { level: 2, name: "Пошта" })).toBeDefined();
  });

  test("три етапи в порядку: підключити агента, налаштувати профіль, готово до пошуку", async () => {
    const { card } = await openCard();

    const found = stages(card).map((item) => STAGES.find((title) => item.textContent.includes(title)));
    expect(found).toEqual(STAGES);
  });

  test("агента ще не підключено — поточний етап перший, лічильник «Крок 1 із 3»", async () => {
    const { card } = await openCard();

    expect(current(card).map((item) => item.textContent)).toEqual([expect.stringContaining("Підключити агента")]);
    expect(within(card).getByText("Крок 1 із 3")).toBeDefined();
  });

  test("агента підключено — поточний етап другий, лічильник «Крок 2 із 3»", async () => {
    const { card } = await openCard({ done: ["claude"] }, [CLAUDE]);

    expect(current(card).map((item) => item.textContent)).toEqual([expect.stringContaining("Налаштувати профіль")]);
    expect(within(card).getByText("Крок 2 із 3")).toBeDefined();
  });

  test("третій етап лише підпис на маршруті: поточним не буває", async () => {
    const { card } = await openCard({ done: ["claude", "goal", "locations", "contacts"] }, [CLAUDE]);

    expect(current(card).map((item) => item.textContent)).toEqual([expect.stringContaining("Налаштувати профіль")]);
  });

  test("стан береться з сервера: GET /api/onboarding", async () => {
    const { backend } = await openCard();

    expect(backend.calls).toEqual(["GET /api/onboarding"]);
  });

  test("старого списку з семи кроків і смуги прогресу нема", async () => {
    const { card } = await openCard();

    expect(within(card).queryByRole("progressbar")).toBeNull();
    expect(within(card).queryByRole("list", { name: "Кроки" })).toBeNull();
    expect(within(card).queryByText("Підключити Claude")).toBeNull();
  });
});

describe("зникає разом з усіма обов'язковими кроками", () => {
  async function hubWithoutCard(done: readonly string[]) {
    const backend = onboardingBackend({ done });
    renderClient("/profile", backend.fetchFn);
    await screen.findByRole("link", { name: /Кар’єрна ціль/ });
    await screen.findByRole("heading", { level: 2, name: "Пошта" });
    await settle();
    return backend;
  }

  test("обов'язкові зроблено, фото й пошти нема — картки нема", async () => {
    const backend = await hubWithoutCard([...REQUIRED_KEYS]);

    expect(backend.calls).toEqual(["GET /api/onboarding"]);
    expect(screen.queryByRole("region", { name: "Перші кроки" })).toBeNull();
  });

  test("зроблено все — картки теж нема, і «готово» не показується", async () => {
    await hubWithoutCard([...STEP_KEYS]);

    expect(screen.queryByRole("region", { name: "Перші кроки" })).toBeNull();
    expect(screen.queryByText(/Усе готово/)).toBeNull();
    expect(screen.queryByText("Готово до пошуку")).toBeNull();
  });

  test("одного обов'язкового кроку бракує — картка є", async () => {
    const { card } = await openCard({ done: REQUIRED_KEYS.filter((key) => key !== "original_cv") });

    expect(within(card).getByRole("heading", { level: 2, name: "Перші кроки" })).toBeDefined();
  });
});

describe("підказок нема", () => {
  test("жодного поповера чи кнопки підказки, і сервер не отримує запитів про підказки", async () => {
    const { backend } = await openCard();
    await settle();

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.queryAllByRole("button", { name: /^Підказка: / })).toEqual([]);
    expect(backend.calls).toEqual(["GET /api/onboarding"]);
  });

  test("не з'являються й на етапі налаштування профілю", async () => {
    const { backend } = await openCard({ done: ["claude"] }, [CLAUDE]);
    await settle();

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.queryAllByRole("button", { name: /^Підказка: / })).toEqual([]);
    expect(backend.calls).toEqual(["GET /api/onboarding"]);
  });
});

describe("вузький екран (375 px)", () => {
  test("рядки кнопок переносяться, адреса не вилазить, фіксованої ширини нема", async () => {
    setViewport("mobile");
    const { card } = await openCard();

    const fixed = [...card.querySelectorAll<HTMLElement>("*")].filter(
      (element) => /(^|\s)(min-)?w-\[\d+px\]/.test(element.className) || /width:\s*\d+px/.test(element.getAttribute("style") ?? ""),
    );
    expect(fixed).toEqual([]);
    expect(within(card).getByRole("button", { name: "Claude" }).parentElement?.className).toContain("flex-wrap");
    expect(within(card).getByText("http://localhost:3000/mcp").className).toContain("[overflow-wrap:anywhere]");
    expect(card.className).toContain("min-w-0");
  });
});

describe("онбординг недоступний", () => {
  const CARD_NAME = { name: "Перші кроки" };

  async function hubWithout(routes: Record<string, () => Response | Promise<Response>>) {
    const backend = profileBackend(FULL_PROFILE, routes);
    renderClient("/profile", backend.fetchFn);
    await screen.findByRole("heading", { level: 2, name: "Пошта" });
    await screen.findByRole("link", { name: /Кар’єрна ціль/ });
    await settle();
  }

  test.each([
    ["сервер відповів 500", () => Promise.resolve(json(500, { code: "internal_error" }))],
    ["сесія завершилась (401)", () => Promise.resolve(json(401, { code: "unauthorized" }))],
    ["мережа недоступна", () => Promise.reject(new TypeError("fetch failed"))],
  ])("%s — картки нема, решта хабу працює", async (_name, failure) => {
    await hubWithout({ "GET /api/onboarding": failure });

    expect(screen.queryByRole("region", CARD_NAME)).toBeNull();
    expect(screen.getAllByRole("heading", { level: 2 }).map((heading) => heading.textContent)).toEqual([
      "Кар’єрна ціль",
      "Локації та формат",
      "Правила відбору",
      "Контакти для CV",
      "Фото для CV",
      "Пошта",
    ]);
  });

  const valid = onboardingBody({ done: new Set(), seen: new Set(), dismissed: new Set() });
  const [firstStep] = valid.steps;
  const [firstTip] = valid.tips;

  test.each<[string, unknown]>([
    ["тіло — не обʼєкт", null],
    ["steps — не масив", { ...valid, steps: "x" }],
    ["крок — не обʼєкт", { ...valid, steps: [1] }],
    ["ключ кроку — не рядок", { ...valid, steps: [{ ...firstStep, key: 5 }] }],
    ["невідомий ключ кроку", { ...valid, steps: [{ ...firstStep, key: "zzz" }] }],
    ["done — не булеве", { ...valid, steps: [{ ...firstStep, done: "yes" }] }],
    ["optional — не булеве", { ...valid, steps: [{ ...firstStep, optional: 1 }] }],
    ["tips — не масив", { ...valid, tips: null }],
    ["ключ підказки — не рядок", { ...valid, tips: [{ ...firstTip, key: null }] }],
    ["seen — не булеве", { ...valid, tips: [{ ...firstTip, seen: "no" }] }],
    ["dismissed — не булеве", { ...valid, tips: [{ ...firstTip, dismissed: undefined }] }],
    ["complete — не булеве", { ...valid, complete: "no" }],
  ])("відповідь не за контрактом (%s) — картки нема", async (_name, body) => {
    await hubWithout({ "GET /api/onboarding": () => json(200, body) });

    expect(screen.queryByRole("region", CARD_NAME)).toBeNull();
  });

  test("порожня відповідь без тіла — картки нема", async () => {
    const backend = fakeBackend({
      ...MEANS_LOGGED_IN,
      "GET /api/profile": () => json(200, FULL_PROFILE),
      "GET /api/onboarding": () => new Response("не json", { status: 200 }),
    });
    renderClient("/profile", backend);
    await screen.findByRole("heading", { level: 2, name: "Пошта" });
    await settle();

    expect(screen.queryByRole("region", CARD_NAME)).toBeNull();
  });
});
