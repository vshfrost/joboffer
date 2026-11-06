import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, test } from "vitest";

import { ANONYMOUS, apiError, INVITE, location, renderSignup, resetAltcha, signupBackend } from "./signupHarness";
import { fakeBackend, json, renderClient } from "./testClient";

const INVALID_HEADING = "Посилання недійсне";
const INVITE_CHECK = `GET /api/auth/signup/invite?invite=${INVITE}`;

beforeEach(resetAltcha);

function expectNoForm() {
  expect(screen.queryByLabelText("Email")).toBeNull();
  expect(screen.queryByLabelText("Пароль")).toBeNull();
  expect(screen.queryByRole("checkbox")).toBeNull();
  expect(screen.queryByRole("button", { name: "Зареєструватися" })).toBeNull();
  expect(screen.queryByTestId("altcha-widget")).toBeNull();
}

describe("запрошення на /signup", () => {
  test("без запрошення в адресі — екран помилки без форми, а сервер не питають", async () => {
    const backend = signupBackend();
    renderSignup("/signup", backend);

    await screen.findByRole("heading", { level: 1, name: INVALID_HEADING });
    expectNoForm();
    expect(backend.mock.calls.filter(([url]) => String(url).includes("/auth/signup/invite"))).toHaveLength(0);
  });

  test("порожнє запрошення в адресі — теж екран помилки без форми", async () => {
    renderSignup("/signup?invite=", signupBackend());

    await screen.findByRole("heading", { level: 1, name: INVALID_HEADING });
    expectNoForm();
  });

  test("запрошення недійсне, прострочене чи використане (404 invite_invalid) — екран помилки без форми", async () => {
    renderSignup(
      `/signup?invite=${INVITE}`,
      signupBackend({ [INVITE_CHECK]: () => apiError(404, "invite_invalid", "Запрошення недійсне") }),
    );

    await screen.findByRole("heading", { level: 1, name: INVALID_HEADING });
    expectNoForm();
  });

  test("реєстрація закрита (404 signup_closed) — той самий екран помилки без форми", async () => {
    renderSignup(
      `/signup?invite=${INVITE}`,
      signupBackend({ [INVITE_CHECK]: () => apiError(404, "signup_closed", "Реєстрацію закрито") }),
    );

    await screen.findByRole("heading", { level: 1, name: INVALID_HEADING });
    expectNoForm();
  });

  test.each([
    ["забагато перевірок (429)", () => apiError(429, "too_many_attempts", "Забагато спроб", {}, { "Retry-After": "60" })],
    ["сервер недоступний (503)", () => apiError(503, "registration_closed", "Реєстрацію закрито")],
    ["відповідь не за контрактом", () => json(200, { hello: "world" })],
  ])("перевірити запрошення не вдалося — %s: екран помилки без форми", async (_name, handler) => {
    renderSignup(`/signup?invite=${INVITE}`, signupBackend({ [INVITE_CHECK]: handler }));

    await screen.findByRole("heading", { level: 1, name: "Не вдалося перевірити запрошення" });
    expectNoForm();
  });

  test("мережа недоступна — екран помилки без форми", async () => {
    const offline = () => Promise.reject(new TypeError("Failed to fetch"));
    renderSignup(`/signup?invite=${INVITE}`, offline);

    await screen.findByRole("heading", { level: 1, name: "Не вдалося перевірити запрошення" });
    expectNoForm();
  });

  test("дійсне запрошення відкриває форму; токен іде в запит перевірки закодованим", async () => {
    const backend = signupBackend({
      "GET /api/auth/signup/invite?invite=a%2Bb%20c": () => json(200, { valid: true, expires_at: "2026-11-06T10:00:00Z" }),
    });
    renderSignup("/signup?invite=a%2Bb%20c", backend);

    await screen.findByRole("heading", { level: 1, name: "Реєстрація" });
    expect(screen.getByLabelText("Email")).toBeDefined();
    expect(backend).toHaveBeenCalledWith(
      "/api/auth/signup/invite?invite=a%2Bb%20c",
      expect.objectContaining({ method: "GET", credentials: "same-origin" }),
    );
    expect(document.title).toBe("Реєстрація · joboffer");
  });

  test("поки сервер не відповів про запрошення, форми нема", async () => {
    const pending = new Promise<Response>(() => undefined);
    const backend = signupBackend({ [INVITE_CHECK]: () => pending as unknown as Response });
    renderSignup(`/signup?invite=${INVITE}`, backend);

    await waitFor(() => {
      expect(backend).toHaveBeenCalledWith(`/api/auth/signup/invite?invite=${INVITE}`, expect.anything());
    });
    expect(screen.getByRole("status").textContent).toContain("Завантаження");
    expectNoForm();
  });

  test("на вузькому екрані (375 px) картка не ширша за екран, відступи по краях збережено", async () => {
    renderSignup(`/signup?invite=${INVITE}`, signupBackend());

    await screen.findByRole("heading", { level: 1, name: "Реєстрація" });
    const page = screen.getByRole("main");
    expect(page.className).toContain("px-4");
    const card = screen.getByRole("heading", { level: 1 }).parentElement;
    expect(card?.className).toContain("w-full");
    expect(card?.className).toContain("max-w-sm");
  });

  test("на екрані помилки є вхід для тих, хто вже має акаунт, і сторінка не вимагає сесії", async () => {
    renderSignup("/signup", signupBackend());

    await screen.findByRole("heading", { level: 1, name: INVALID_HEADING });
    expect(screen.getByRole("link", { name: "До сторінки входу" }).getAttribute("href")).toBe("/login");
    expect(location()).toBe("/signup");
  });
});

describe("/signup/verify без реєстрації", () => {
  test("без активної реєстрації — той самий екран помилки без форми", async () => {
    const backend = signupBackend();
    renderSignup("/signup/verify", backend);

    await screen.findByRole("heading", { level: 1, name: INVALID_HEADING });
    expectNoForm();
    expect(screen.queryByLabelText("Код з листа")).toBeNull();
    expect(backend.mock.calls.filter(([url]) => String(url).includes("/auth/signup"))).toHaveLength(0);
  });
});

describe("вхід і реєстрація", () => {
  test("на /login нема посилання на реєстрацію", async () => {
    renderClient("/login", fakeBackend({ ...ANONYMOUS, "GET /api/auth/providers": () => json(200, { google: false }) }));

    await screen.findByRole("heading", { level: 1, name: "Вхід" });
    const links = screen.getAllByRole("link").map((link) => link.getAttribute("href"));
    expect(links.filter((href) => href?.includes("signup"))).toEqual([]);
    expect(screen.queryByText(/Зареєструватися|Реєстрація|Створити акаунт/)).toBeNull();
  });

  test("на формі реєстрації нема кнопки Google, навіть коли вхід через Google ввімкнено", async () => {
    const backend = signupBackend({ "GET /api/auth/providers": () => json(200, { google: true }) });
    renderSignup(`/signup?invite=${INVITE}`, backend);

    await screen.findByRole("heading", { level: 1, name: "Реєстрація" });
    expect(screen.queryByText(/Google/)).toBeNull();
    expect(screen.queryByRole("link", { name: /Google/ })).toBeNull();
  });
});
