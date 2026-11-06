import { act, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { fakeBackend, json, ME, MEANS_LOGGED_IN, renderClient, sessionBody } from "./testClient";

const NOT_AUTHENTICATED = { code: "not_authenticated", message: "Потрібен вхід", field_errors: [], correlation_id: "c1" };
const INVALID_CREDENTIALS = { code: "invalid_credentials", message: "Невірні дані", field_errors: [], correlation_id: "c2" };
const TOO_MANY = { code: "too_many_attempts", message: "Забагато спроб", field_errors: [], correlation_id: "c3" };

const ANONYMOUS = { "GET /api/auth/me": () => json(401, NOT_AUTHENTICATED) };

const location = () => screen.getByTestId("location").textContent;

async function fillAndSubmit(user: ReturnType<typeof userEvent.setup>, email: string, password: string) {
  await user.type(await screen.findByLabelText("Email"), email);
  await user.type(screen.getByLabelText("Пароль"), password);
  await user.click(screen.getByRole("button", { name: "Увійти" }));
}

afterEach(() => {
  vi.useRealTimers();
});

describe("захист маршрутів", () => {
  test("без сесії приватний маршрут веде на /login з next", async () => {
    renderClient("/vacancies", fakeBackend(ANONYMOUS));

    await screen.findByRole("heading", { level: 1, name: "Вхід" });
    const url = new URL(location() ?? "", "http://app.test");
    expect(url.pathname).toBe("/login");
    expect(url.searchParams.get("next")).toBe("/vacancies");
  });

  test("next зберігає й параметри адреси", async () => {
    renderClient("/vacancies?tab=archived", fakeBackend(ANONYMOUS));

    await screen.findByRole("heading", { level: 1, name: "Вхід" });
    const url = new URL(location() ?? "", "http://app.test");
    expect(url.searchParams.get("next")).toBe("/vacancies?tab=archived");
  });

  test("поки сервер не відповів про сесію, нікуди не перенаправляє", async () => {
    const pending = new Promise<Response>(() => undefined);
    renderClient("/vacancies", fakeBackend({ "GET /api/auth/me": () => pending as unknown as Response }));

    expect(await screen.findByRole("status")).toBeDefined();
    expect(screen.getByRole("status").textContent).toContain("Завантаження…");
    expect(screen.getByRole("status").querySelector("svg")).not.toBeNull();
    expect(location()).toBe("/vacancies");
    expect(screen.queryByRole("navigation", { name: "Головна навігація" })).toBeNull();
  });

  test("сесія є — відкривається оболонка з імʼям користувача в Topbar", async () => {
    renderClient("/vacancies", fakeBackend(MEANS_LOGGED_IN));

    const topbar = await screen.findByRole("banner");
    expect(within(topbar).getByText(ME.display_name)).toBeDefined();
    expect(screen.getByRole("heading", { level: 1, name: "Вакансії" })).toBeDefined();
    expect(location()).toBe("/vacancies");
  });

  test("запит сесії йде на /api/auth/me з cookie того ж origin", async () => {
    const backend = fakeBackend(MEANS_LOGGED_IN);
    renderClient("/vacancies", backend);
    await screen.findByRole("banner");

    expect(backend).toHaveBeenCalledWith("/api/auth/me", expect.objectContaining({ method: "GET", credentials: "same-origin" }));
  });

  test.each([
    ["сервер відповів 500", () => json(500, { code: "internal_error", message: "x", field_errors: [], correlation_id: "c" })],
    ["відповідь не за контрактом", () => json(200, { hello: "world" })],
  ])("якщо сесію перевірити не вдалося (%s), веде на /login", async (_name, handler) => {
    renderClient("/vacancies", fakeBackend({ "GET /api/auth/me": handler }));

    await screen.findByRole("heading", { level: 1, name: "Вхід" });
    expect(new URL(location() ?? "", "http://app.test").pathname).toBe("/login");
  });

  test("якщо мережа недоступна, веде на /login", async () => {
    const offline = vi.fn<typeof fetch>(() => Promise.reject(new TypeError("Failed to fetch")));
    renderClient("/vacancies", offline);

    await screen.findByRole("heading", { level: 1, name: "Вхід" });
  });

  test("користувач із сесією, відкривши /login, потрапляє на next", async () => {
    renderClient("/login?next=%2Ffacts", fakeBackend(MEANS_LOGGED_IN));

    await screen.findByRole("heading", { level: 1, name: "Факти" });
    expect(location()).toBe("/facts");
  });

  test("користувач із сесією, відкривши /login без next, потрапляє на вакансії", async () => {
    renderClient("/login", fakeBackend(MEANS_LOGGED_IN));

    await screen.findByRole("heading", { level: 1, name: "Вакансії" });
    expect(location()).toBe("/vacancies");
  });
});

describe("вхід", () => {
  test("форма має поля email і пароль; пароль приховано", async () => {
    renderClient("/login", fakeBackend(ANONYMOUS));

    const email = await screen.findByLabelText("Email");
    const password = screen.getByLabelText("Пароль");
    expect(email.getAttribute("type")).toBe("email");
    expect(email.getAttribute("autocomplete")).toBe("username");
    expect(password.getAttribute("type")).toBe("password");
    expect(password.getAttribute("autocomplete")).toBe("current-password");
    expect(document.title).toBe("Вхід · joboffer");
  });

  test("вдалий вхід надсилає email і пароль на /api/auth/login та веде на next", async () => {
    const user = userEvent.setup();
    const backend = fakeBackend({ ...ANONYMOUS, "POST /api/auth/login": () => json(200, sessionBody("csrf-login")) });
    renderClient("/vacancies", backend);

    await fillAndSubmit(user, "taras@example.com", "correct horse battery");

    await screen.findByRole("heading", { level: 1, name: "Вакансії" });
    expect(location()).toBe("/vacancies");
    const call = backend.mock.calls.find(([url]) => url === "/api/auth/login");
    expect(call?.[1]).toMatchObject({ method: "POST", credentials: "same-origin" });
    expect(new Headers(call?.[1]?.headers).get("Content-Type")).toBe("application/json");
    expect(JSON.parse(String(call?.[1]?.body))).toEqual({ email: "taras@example.com", password: "correct horse battery" });
    expect(within(screen.getByRole("banner")).getByText(ME.display_name)).toBeDefined();
  });

  test("поки сервер відповідає, кнопка зайнята: «Входимо…», aria-busy, повторно не натиснути", async () => {
    const user = userEvent.setup();
    const backend = fakeBackend({ ...ANONYMOUS, "POST /api/auth/login": () => new Promise<Response>(() => undefined) as unknown as Response });
    renderClient("/login", backend);

    await fillAndSubmit(user, "taras@example.com", "correct horse battery");

    const button = await screen.findByRole("button", { name: "Входимо…" });
    expect(button.getAttribute("aria-busy")).toBe("true");
    expect((button as HTMLButtonElement).disabled).toBe(true);
    expect(button.querySelector("svg")).not.toBeNull();
  });

  test.each(["https://evil.example", "//evil"])("next=%s після входу веде на головну, а не назовні", async (next) => {
    const user = userEvent.setup();
    const backend = fakeBackend({ ...ANONYMOUS, "POST /api/auth/login": () => json(200, sessionBody("csrf-login")) });
    renderClient(`/login?next=${encodeURIComponent(next)}`, backend);

    await fillAndSubmit(user, "taras@example.com", "correct horse battery");

    await screen.findByRole("heading", { level: 1, name: "Вакансії" });
    expect(location()).toBe("/vacancies");
  });

  test("поки сервер відповідає, кнопку вимкнено і повторний сабміт неможливий", async () => {
    const user = userEvent.setup();
    let finish: (response: Response) => void = () => undefined;
    const slow = new Promise<Response>((resolve) => {
      finish = resolve;
    });
    const backend = fakeBackend({ ...ANONYMOUS, "POST /api/auth/login": () => slow as unknown as Response });
    renderClient("/login", backend);

    await fillAndSubmit(user, "taras@example.com", "correct horse battery");

    const button = screen.getByRole("button", { name: "Входимо…" });
    expect((button as HTMLButtonElement).disabled).toBe(true);
    await user.click(button);
    expect(backend.mock.calls.filter(([url]) => url === "/api/auth/login")).toHaveLength(1);

    await act(async () => {
      finish(json(200, sessionBody("csrf-login")));
    });
    await screen.findByRole("banner");
  });

  test("401: одне повідомлення, пароль очищено й у фокусі, email лишився", async () => {
    const user = userEvent.setup();
    renderClient(
      "/login",
      fakeBackend({ ...ANONYMOUS, "POST /api/auth/login": () => json(401, INVALID_CREDENTIALS) }),
    );

    await fillAndSubmit(user, "taras@example.com", "wrong password here");

    expect((await screen.findByRole("alert")).textContent).toContain("Невірний email або пароль");
    expect((screen.getByLabelText("Email") as HTMLInputElement).value).toBe("taras@example.com");
    const password = screen.getByLabelText("Пароль") as HTMLInputElement;
    expect(password.value).toBe("");
    expect(document.activeElement).toBe(password);
    expect(new URL(location() ?? "", "http://app.test").pathname).toBe("/login");
  });

  test("повідомлення про помилку зникає, коли користувач пробує знову", async () => {
    const user = userEvent.setup();
    let attempts = 0;
    renderClient(
      "/login",
      fakeBackend({
        ...ANONYMOUS,
        "POST /api/auth/login": () => {
          attempts += 1;
          return attempts === 1 ? json(401, INVALID_CREDENTIALS) : json(200, sessionBody("csrf-login"));
        },
      }),
    );

    await fillAndSubmit(user, "taras@example.com", "wrong password here");
    await screen.findByRole("alert");
    await user.type(screen.getByLabelText("Пароль"), "correct horse battery");
    await user.click(screen.getByRole("button", { name: "Увійти" }));

    await screen.findByRole("banner");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  test.each([
    ["сервер відповів 500", () => Promise.resolve(json(500, { code: "internal_error", message: "x", field_errors: [], correlation_id: "c" }))],
    ["мережа недоступна", () => Promise.reject(new TypeError("Failed to fetch"))],
  ])("%s: загальне повідомлення, а не «невірний пароль»", async (_name, respond) => {
    const user = userEvent.setup();
    const backend = vi.fn<typeof fetch>((input) =>
      input === "/api/auth/me" ? Promise.resolve(json(401, NOT_AUTHENTICATED)) : respond(),
    );
    renderClient("/login", backend);

    await fillAndSubmit(user, "taras@example.com", "correct horse battery");

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Не вдалося звʼязатися з сервером. Спробуй ще раз.");
    expect(alert.textContent).not.toContain("Невірний");
    expect((screen.getByRole("button", { name: "Увійти" }) as HTMLButtonElement).disabled).toBe(false);
  });
});

describe("ліміт спроб (429)", () => {
  async function tooManyAttempts(retryAfter: Record<string, string>) {
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval", "Date"] });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderClient(
      "/login",
      fakeBackend({ ...ANONYMOUS, "POST /api/auth/login": () => json(429, TOO_MANY, retryAfter) }),
    );
    await fillAndSubmit(user, "taras@example.com", "correct horse battery");
    return await screen.findByRole("alert");
  }

  const submit = () => screen.getByRole("button", { name: "Увійти" }) as HTMLButtonElement;

  async function advance(ms: number) {
    await act(async () => {
      vi.advanceTimersByTime(ms);
    });
  }

  test("Retry-After: 600 показує «~10 хв» і вимикає кнопку", async () => {
    const alert = await tooManyAttempts({ "Retry-After": "600" });

    expect(alert.textContent).toContain("Забагато спроб, спробуй за ~10 хв");
    expect(submit().disabled).toBe(true);
  });

  test("кнопка лишається неактивною до кінця відліку, а тоді вмикається і повідомлення зникає", async () => {
    await tooManyAttempts({ "Retry-After": "600" });

    await advance(599_000);
    expect(submit().disabled).toBe(true);
    expect(screen.getByRole("alert").textContent).toContain("~1 хв");

    await advance(1_000);
    expect(submit().disabled).toBe(false);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  test("відлік зменшує число хвилин у повідомленні", async () => {
    await tooManyAttempts({ "Retry-After": "600" });

    await advance(300_000);

    expect(screen.getByRole("alert").textContent).toContain("~5 хв");
  });

  test("без заголовка Retry-After чекати пропонує ~1 хв", async () => {
    const alert = await tooManyAttempts({});

    expect(alert.textContent).toContain("~1 хв");
    expect(submit().disabled).toBe(true);
  });

  test("поки триває відлік, сабміт з клавіатури (Enter) запит не надсилає", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval", "Date"] });
    const backend = fakeBackend({ ...ANONYMOUS, "POST /api/auth/login": () => json(429, TOO_MANY, { "Retry-After": "600" }) });
    renderClient("/login", backend);
    await fillAndSubmit(user, "taras@example.com", "correct horse battery");
    await screen.findByRole("alert");

    await user.type(screen.getByLabelText("Пароль"), "another attempt{Enter}");

    expect(backend.mock.calls.filter(([url]) => url === "/api/auth/login")).toHaveLength(1);
  });
});
