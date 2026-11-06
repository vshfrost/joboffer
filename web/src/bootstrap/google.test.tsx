import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import { fakeBackend, json, renderClient } from "./testClient";

const NOT_AUTHENTICATED = { code: "not_authenticated", message: "Потрібен вхід", field_errors: [], correlation_id: "c1" };

function anonymous(providers: () => Response | Promise<Response>) {
  return fakeBackend({
    "GET /api/auth/me": () => json(401, NOT_AUTHENTICATED),
    "GET /api/auth/providers": providers,
  });
}

const googleOn = () => json(200, { google: true });

describe("кнопка Google на екрані входу", () => {
  test("є, коли бекенд каже, що Google увімкнено, і веде на старт входу з next", async () => {
    renderClient("/login?next=%2Fvacancies", anonymous(googleOn));

    const button = await screen.findByRole("link", { name: "Увійти через Google" });

    expect(button.getAttribute("href")).toBe("/api/auth/google/start?next=%2Fvacancies");
  });

  test("клік: «Переходимо до Google…» зі спінером, а повторний клік ігнорується (перехід не повторюється)", async () => {
    renderClient("/login", anonymous(googleOn));
    const link = await screen.findByRole("link", { name: "Увійти через Google" });
    // Перехід за посиланням у jsdom не реалізовано: фіксуємо, чи його скасував застосунок, і гасимо сами.
    const prevented: boolean[] = [];
    const record = (event: Event) => {
      prevented.push(event.defaultPrevented);
      event.preventDefault();
    };
    document.addEventListener("click", record);
    let busy: HTMLElement;
    try {
      fireEvent.click(link);
      busy = await screen.findByRole("link", { name: "Переходимо до Google…" });
      fireEvent.click(busy);
    } finally {
      document.removeEventListener("click", record);
    }

    expect(busy.getAttribute("aria-busy")).toBe("true");
    expect(busy.querySelector("svg")).not.toBeNull();
    expect(prevented).toEqual([false, true]);
  });

  test("без next веде з next=/ (головна)", async () => {
    renderClient("/login", anonymous(googleOn));

    const button = await screen.findByRole("link", { name: "Увійти через Google" });

    expect(button.getAttribute("href")).toBe("/api/auth/google/start?next=%2F");
  });

  test.each(["https://evil.example", "//evil"])("небезпечний next=%s не потрапляє в посилання", async (next) => {
    renderClient(`/login?next=${encodeURIComponent(next)}`, anonymous(googleOn));

    const button = await screen.findByRole("link", { name: "Увійти через Google" });

    expect(button.getAttribute("href")).toBe("/api/auth/google/start?next=%2F");
  });

  test("next зберігає параметри адреси", async () => {
    renderClient("/login?next=%2Fvacancies%3Ftab%3Darchived", anonymous(googleOn));

    const button = await screen.findByRole("link", { name: "Увійти через Google" });

    expect(button.getAttribute("href")).toBe("/api/auth/google/start?next=%2Fvacancies%3Ftab%3Darchived");
  });

  test("нема, коли бекенд каже, що Google вимкнено; форма пароля на місці", async () => {
    renderClient("/login", anonymous(() => json(200, { google: false })));

    await screen.findByLabelText("Email");

    expect(screen.queryByRole("link", { name: "Увійти через Google" })).toBeNull();
    expect(screen.getByLabelText("Пароль")).toBeDefined();
  });

  test.each([
    ["сервер відповів 500", () => json(500, { code: "internal_error", message: "x", field_errors: [], correlation_id: "c" })],
    ["відповідь не за контрактом", () => json(200, { hello: "world" })],
  ])("якщо дізнатися про провайдерів не вдалося (%s), кнопки нема, а вхід паролем працює", async (_name, providers) => {
    renderClient("/login", anonymous(providers));

    await screen.findByLabelText("Email");

    expect(screen.queryByRole("link", { name: "Увійти через Google" })).toBeNull();
    expect(screen.getByRole("button", { name: "Увійти" })).toBeDefined();
  });

  test("якщо мережа недоступна, кнопки нема", async () => {
    const offline = vi.fn<typeof fetch>((input) =>
      input === "/api/auth/me" ? Promise.resolve(json(401, NOT_AUTHENTICATED)) : Promise.reject(new TypeError("Failed to fetch")),
    );
    renderClient("/login", offline);

    await screen.findByLabelText("Email");

    expect(screen.queryByRole("link", { name: "Увійти через Google" })).toBeNull();
  });

  test("запит про провайдерів іде на /api/auth/providers з cookie того ж origin", async () => {
    const backend = anonymous(googleOn);
    renderClient("/login", backend);
    await screen.findByRole("link", { name: "Увійти через Google" });

    expect(backend).toHaveBeenCalledWith("/api/auth/providers", expect.objectContaining({ method: "GET", credentials: "same-origin" }));
  });
});

describe("повідомлення після повернення з Google", () => {
  test.each([
    ["email_required", "Google не передав підтверджений email — вхід неможливий"],
    ["cancelled", "Вхід скасовано"],
    ["failed", "Не вдалося увійти через Google. Спробуй ще раз."],
    ["щось-невідоме", "Не вдалося увійти через Google. Спробуй ще раз."],
  ])("?error=%s → «%s»", async (error, message) => {
    renderClient(`/login?error=${encodeURIComponent(error)}`, anonymous(googleOn));

    const alert = await screen.findByRole("alert");

    expect(alert.textContent).toContain(message);
    expect(screen.getByLabelText("Email")).toBeDefined();
  });

  test("без ?error= повідомлення нема", async () => {
    renderClient("/login", anonymous(googleOn));
    await screen.findByRole("link", { name: "Увійти через Google" });

    expect(screen.queryByRole("alert")).toBeNull();
  });

  test("помилка з Google не блокує вхід паролем і зникає, коли користувач пробує пароль", async () => {
    const user = (await import("@testing-library/user-event")).default.setup();
    const backend = fakeBackend({
      "GET /api/auth/me": () => json(401, NOT_AUTHENTICATED),
      "GET /api/auth/providers": googleOn,
      "POST /api/auth/login": () => json(401, { code: "invalid_credentials", message: "x", field_errors: [], correlation_id: "c" }),
    });
    renderClient("/login?error=cancelled", backend);

    await user.type(await screen.findByLabelText("Email"), "taras@example.com");
    await user.type(screen.getByLabelText("Пароль"), "wrong password here");
    await user.click(screen.getByRole("button", { name: "Увійти" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Невірний email або пароль");
    expect(screen.queryByText("Вхід скасовано")).toBeNull();
  });
});
