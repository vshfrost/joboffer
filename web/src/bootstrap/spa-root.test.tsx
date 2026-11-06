/** SPA віддається з кореня origin: справжній bootstrap (`main.tsx`) без префікса в адресі. */
import { screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import config from "../../vite.config";
import { profileBackend } from "./profileBackend";
import { fakeBackend, json } from "./testClient";

const NOT_AUTHENTICATED = { code: "not_authenticated", message: "Потрібен вхід", field_errors: [], correlation_id: "c1" };
const ANONYMOUS = fakeBackend({ "GET /api/auth/me": () => json(401, NOT_AUTHENTICATED) });

async function openAt(path: string, fetchFn: typeof fetch) {
  // Збірку з префіксом (`base: "/prefix/"`) імітуємо тут: роутер не повинен читати BASE_URL.
  vi.stubEnv("BASE_URL", "/prefix/");
  window.history.replaceState(null, "", path);
  vi.stubGlobal("fetch", fetchFn);
  document.body.innerHTML = '<div id="root"></div>';
  vi.resetModules();
  await import("./main");
}

beforeEach(() => {
  window.history.replaceState(null, "", "/");
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  document.body.innerHTML = "";
});

test("збірка Vite кладе ресурси в корінь origin (base `/`)", async () => {
  const resolved = typeof config === "function" ? await config({ command: "build", mode: "production" }) : config;

  expect(resolved.base).toBe("/");
});

describe("застосунок на корені origin", () => {
  test("кореневу адресу `/` веде на вакансії, а не в not-found", async () => {
    await openAt("/", profileBackend().fetchFn);

    await screen.findByRole("navigation", { name: "Головна навігація" });
    expect(window.location.pathname).toBe("/vacancies");
  });

  test("`/profile` показує профіль", async () => {
    await openAt("/profile", profileBackend().fetchFn);

    expect(await screen.findByRole("heading", { level: 1, name: "Профіль" })).toBeDefined();
    expect(window.location.pathname).toBe("/profile");
  });

  test("`/facts` показує сторінку фактів, а не not-found", async () => {
    await openAt("/facts", profileBackend().fetchFn);

    await screen.findByRole("navigation", { name: "Головна навігація" });
    expect(screen.queryByRole("heading", { name: "Сторінку не знайдено" })).toBeNull();
  });
});

describe("вхід без префікса", () => {
  test("неавторизованого з `/vacancies/1` веде на `/login` з next без префікса", async () => {
    await openAt("/vacancies/1", ANONYMOUS);

    await screen.findByRole("heading", { level: 1, name: "Вхід" });
    expect(window.location.pathname).toBe("/login");
    expect(new URLSearchParams(window.location.search).get("next")).toBe("/vacancies/1");
  });
});
