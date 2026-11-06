import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { fakeBackend, json, MEANS_LOGGED_IN, noContent, renderClient, sessionBody } from "./testClient";

const location = () => screen.getByTestId("location").textContent;

async function logOut(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: "Вийти" }));
}

describe("вихід", () => {
  test("POST /api/auth/logout з X-CSRF-Token із me, далі /login", async () => {
    const user = userEvent.setup();
    const backend = fakeBackend({ ...MEANS_LOGGED_IN, "POST /api/auth/logout": () => noContent() });
    renderClient("/vacancies", backend);

    await logOut(user);

    await screen.findByRole("heading", { level: 1, name: "Вхід" });
    expect(location()).toBe("/login");
    const call = backend.mock.calls.find(([url]) => url === "/api/auth/logout");
    expect(call?.[1]).toMatchObject({ method: "POST", credentials: "same-origin" });
    expect(new Headers(call?.[1]?.headers).get("X-CSRF-Token")).toBe("csrf-me");
  });

  test("після входу формою вихід шле токен із відповіді login, а не старий", async () => {
    const user = userEvent.setup();
    const backend = fakeBackend({
      "GET /api/auth/me": () => json(401, { code: "not_authenticated", message: "x", field_errors: [], correlation_id: "c" }),
      "POST /api/auth/login": () => json(200, sessionBody("csrf-login")),
      "POST /api/auth/logout": () => noContent(),
    });
    renderClient("/login", backend);
    await user.type(await screen.findByLabelText("Email"), "taras@example.com");
    await user.type(screen.getByLabelText("Пароль"), "correct horse battery");
    await user.click(screen.getByRole("button", { name: "Увійти" }));

    await logOut(user);

    await screen.findByRole("heading", { level: 1, name: "Вхід" });
    const call = backend.mock.calls.find(([url]) => url === "/api/auth/logout");
    expect(new Headers(call?.[1]?.headers).get("X-CSRF-Token")).toBe("csrf-login");
  });

  test("після виходу приватні маршрути знову ведуть на /login", async () => {
    const user = userEvent.setup();
    renderClient("/vacancies", fakeBackend({ ...MEANS_LOGGED_IN, "POST /api/auth/logout": () => noContent() }));
    await logOut(user);
    await screen.findByRole("heading", { level: 1, name: "Вхід" });

    await user.click(screen.getByRole("link", { name: "probe: факти" }));

    await screen.findByRole("heading", { level: 1, name: "Вхід" });
    const url = new URL(location() ?? "", "http://app.test");
    expect(url.pathname).toBe("/login");
    expect(url.searchParams.get("next")).toBe("/facts");
    expect(screen.queryByRole("navigation", { name: "Головна навігація" })).toBeNull();
  });

  test("CSRF-токен лише в памʼяті: у сховищах браузера нічого нема", async () => {
    renderClient("/vacancies", fakeBackend(MEANS_LOGGED_IN));
    await screen.findByRole("banner");

    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });

  test("якщо сервер вихід не підтвердив, лишає в оболонці й пояснює", async () => {
    const user = userEvent.setup();
    renderClient(
      "/vacancies",
      fakeBackend({
        ...MEANS_LOGGED_IN,
        // Головна сторінка тепер сама вантажить вакансії; порожній список — не помилка.
        "GET /api/jobs?stage=open&limit=200": () => json(200, { items: [], sources: [], counts: { in_progress: 0, applied_unreviewed: 0, needs_text: false } }),
        "POST /api/auth/logout": () => json(500, { code: "internal_error", message: "x", field_errors: [], correlation_id: "c" }),
      }),
    );

    await logOut(user);

    expect((await screen.findByRole("alert")).textContent).toContain("Не вдалося вийти. Спробуй ще раз.");
    expect(location()).toBe("/vacancies");
    expect(screen.getByRole("navigation", { name: "Головна навігація" })).toBeDefined();
  });
});
