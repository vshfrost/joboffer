import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import {
  advance,
  apiError,
  EMAIL,
  fieldError,
  INVITE,
  location,
  reachVerify,
  resetAltcha,
  SIGNUP_ID,
  signupBackend,
  useCountdownClock,
} from "./signupHarness";
import { json } from "./testClient";

beforeEach(resetAltcha);
afterEach(() => {
  vi.useRealTimers();
});

const RESEND = "Надіслати код ще раз";
const VERIFY = "POST /api/auth/signup/verify";
const RESEND_ROUTE = "POST /api/auth/signup/resend";

function bodies(backend: ReturnType<typeof signupBackend>, path: string): Record<string, unknown>[] {
  return backend.mock.calls
    .filter(([url, init]) => url === path && init?.method === "POST")
    .map(([, init]) => JSON.parse(String(init?.body)) as Record<string, unknown>);
}

async function openVerify(overrides: Parameters<typeof signupBackend>[0] = {}) {
  const user = userEvent.setup();
  const backend = signupBackend(overrides);
  const code = await reachVerify(user, backend);
  return { user, backend, code: code as HTMLInputElement };
}

describe("екран коду", () => {
  test("показує, куди надіслано код, і має поле одноразового коду", async () => {
    const { code } = await openVerify();

    expect(screen.getByRole("heading", { level: 1, name: "Підтверди email" })).toBeDefined();
    expect(screen.getByText(new RegExp(EMAIL.replace(".", "\\.")))).toBeDefined();
    expect(code.getAttribute("autocomplete")).toBe("one-time-code");
    expect(document.title).toBe("Підтвердження email · joboffer");
  });

  test("на вузькому екрані (375 px) картка не ширша за екран, відступи по краях збережено", async () => {
    await openVerify();

    expect(screen.getByRole("main").className).toContain("px-4");
    const card = screen.getByRole("heading", { level: 1 }).parentElement;
    expect(card?.className).toContain("w-full");
    expect(card?.className).toContain("max-w-sm");
  });

  test("кнопки Google нема", async () => {
    await openVerify();

    expect(screen.queryByText(/Google/)).toBeNull();
  });
});

describe("введення коду", () => {
  test("поки сервер перевіряє код, видно «Перевіряємо…» зі спінером, а поле заблоковане", async () => {
    const { user, code } = await openVerify({ [VERIFY]: () => new Promise<Response>(() => undefined) as unknown as Response });

    await user.click(code);
    await user.paste("123456");

    const status = await screen.findByRole("status");
    expect(status.textContent).toContain("Перевіряємо…");
    expect(status.getAttribute("aria-busy")).toBe("true");
    expect(status.querySelector("svg")).not.toBeNull();
    expect(code.disabled).toBe(true);
  });

  test("код, вставлений одним рухом, сам відправляється, а успіх веде на /profile", async () => {
    const { user, backend, code } = await openVerify();

    await user.click(code);
    await user.paste("123456");

    await waitFor(() => {
      expect(location()).toBe("/profile");
    });
    expect(bodies(backend, "/api/auth/signup/verify")).toEqual([{ signup_id: SIGNUP_ID, code: "123456" }]);
  });

  test("набраний вручну код відправляється на шостій цифрі, без кнопки", async () => {
    const { user, backend, code } = await openVerify();

    await user.type(code, "12345");
    expect(bodies(backend, "/api/auth/signup/verify")).toEqual([]);
    await user.type(code, "6");

    await waitFor(() => {
      expect(location()).toBe("/profile");
    });
    expect(bodies(backend, "/api/auth/signup/verify")).toEqual([{ signup_id: SIGNUP_ID, code: "123456" }]);
  });

  test("невірний код — повідомлення біля поля з кількістю спроб, поле очищено, переходу нема", async () => {
    const { user, code } = await openVerify({
      [VERIFY]: () =>
        json(
          422,
          {
            code: "code_incorrect",
            message: "Невірний код",
            field_errors: [{ field: "code", message: "Невірний код" }],
            correlation_id: "c",
            attempts_left: 3,
          },
        ),
    });

    await user.click(code);
    await user.paste("111111");

    const message = await screen.findByText("Невірний код. Залишилось спроб: 3");
    const field = screen.getByLabelText("Код з листа") as HTMLInputElement;
    expect(field.getAttribute("aria-describedby")).toContain(message.id);
    expect(field.value).toBe("");
    expect(location()).toBe("/signup/verify");
  });

  test("невірний код без кількості спроб у відповіді — повідомлення без числа", async () => {
    const { user, code } = await openVerify({ [VERIFY]: () => fieldError("code", "code_incorrect", "Невірний код") });

    await user.click(code);
    await user.paste("111111");

    expect(await screen.findByText("Невірний код.")).toBeDefined();
  });

  test("після невірного коду можна ввести правильний", async () => {
    const answers = [
      json(422, { code: "code_incorrect", message: "x", field_errors: [], correlation_id: "c", attempts_left: 2 }),
      json(201, { user: { id: "u1", email: EMAIL, display_name: "new.user" }, csrf_token: "csrf-signup" }),
    ];
    const { user, backend, code } = await openVerify({ [VERIFY]: () => answers.shift() as Response });

    await user.click(code);
    await user.paste("111111");
    await screen.findByText("Невірний код. Залишилось спроб: 2");
    await user.click(screen.getByLabelText("Код з листа"));
    await user.paste("222222");

    await waitFor(() => {
      expect(location()).toBe("/profile");
    });
    expect(bodies(backend, "/api/auth/signup/verify").map((body) => body["code"])).toEqual(["111111", "222222"]);
  });

  test("запит прострочено або спроби вичерпано (signup_expired) — екран з поверненням до початку реєстрації", async () => {
    const { user, code } = await openVerify({
      [VERIFY]: () => fieldError("signup_id", "signup_expired", "Запит недійсний"),
    });

    await user.click(code);
    await user.paste("111111");

    await screen.findByRole("heading", { level: 1, name: "Запит прострочено" });
    expect(screen.queryByLabelText("Код з листа")).toBeNull();
    expect(screen.getByRole("link", { name: "Почати спочатку" }).getAttribute("href")).toBe(`/signup?invite=${INVITE}`);
  });

  test("запрошення вже використано (409 invite_used) — екран недійсного посилання", async () => {
    const { user, code } = await openVerify({
      [VERIFY]: () => apiError(409, "invite_used", "Запрошення вже використано"),
    });

    await user.click(code);
    await user.paste("111111");

    await screen.findByRole("heading", { level: 1, name: "Посилання недійсне" });
    expect(screen.queryByLabelText("Код з листа")).toBeNull();
  });

  test.each([
    ["сервер недоступний (500)", () => apiError(500, "internal_error", "x")],
    ["відповідь не за контрактом", () => json(201, { hello: "world" })],
  ])("%s — повідомлення біля поля, а код можна ввести ще раз", async (_name, handler) => {
    const { user, code } = await openVerify({ [VERIFY]: handler });

    await user.click(code);
    await user.paste("111111");

    await screen.findByText("Не вдалося звʼязатися з сервером. Спробуй ще раз.");
    expect((screen.getByLabelText("Код з листа") as HTMLInputElement).disabled).toBe(false);
  });

  test("запит коду, що ще йде, блокує поле, а повторного запиту нема", async () => {
    const pending = new Promise<Response>(() => undefined);
    const { user, backend, code } = await openVerify({ [VERIFY]: () => pending as unknown as Response });

    await user.click(code);
    await user.paste("123456");

    await waitFor(() => {
      expect((screen.getByLabelText("Код з листа") as HTMLInputElement).disabled).toBe(true);
    });
    expect(bodies(backend, "/api/auth/signup/verify")).toHaveLength(1);
  });
});

describe("повторна відправка коду", () => {
  async function openWithClock(overrides: Parameters<typeof signupBackend>[0] = {}) {
    useCountdownClock();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const backend = signupBackend(overrides);
    await reachVerify(user, backend);
    // Поле коду з'являється раніше, ніж ефект сторінки запускає відлік (до цього кнопка вже «доступна»):
    // чекаємо його старту, інакше advance() міг би зрушити годинник ще до дедлайну.
    await screen.findByRole("button", { name: "Надіслати ще раз через 60 с" });
    return { user, backend };
  }

  const resendButton = (name: string | RegExp) => screen.getByRole("button", { name }) as HTMLButtonElement;

  test("спершу кнопка вимкнена з відліком 60 с, а по його закінченні стає доступною", async () => {
    await openWithClock();

    expect(resendButton("Надіслати ще раз через 60 с").disabled).toBe(true);
    await advance(30_000);
    expect(resendButton("Надіслати ще раз через 30 с").disabled).toBe(true);
    await advance(30_000);
    expect(resendButton(RESEND).disabled).toBe(false);
  });

  test("надсилає signup_id, показує, що код надіслано, і відлік іде знову", async () => {
    const { user, backend } = await openWithClock();
    await advance(60_000);

    await user.click(resendButton(RESEND));

    expect((await screen.findByRole("status")).textContent).toContain("Новий код надіслано");
    expect(bodies(backend, "/api/auth/signup/resend")).toEqual([{ signup_id: SIGNUP_ID }]);
    expect(resendButton("Надіслати ще раз через 60 с").disabled).toBe(true);
  });

  test("якщо сервер видав новий signup_id, наступний код іде з ним", async () => {
    const { user, backend } = await openWithClock({ [RESEND_ROUTE]: () => json(202, { signup_id: "sg-new" }) });
    await advance(60_000);

    await user.click(resendButton(RESEND));
    await screen.findByText("Новий код надіслано");
    const code = screen.getByLabelText("Код з листа");
    await user.click(code);
    await user.paste("123456");

    await waitFor(() => {
      expect(location()).toBe("/profile");
    });
    expect(bodies(backend, "/api/auth/signup/verify")).toEqual([{ signup_id: "sg-new", code: "123456" }]);
  });

  test("429 з Retry-After: 45 запускає відлік 45 с", async () => {
    const { user } = await openWithClock({
      [RESEND_ROUTE]: () => apiError(429, "too_many_attempts", "Забагато спроб", {}, { "Retry-After": "45" }),
    });
    await advance(60_000);

    await user.click(resendButton(RESEND));

    expect(await screen.findByRole("button", { name: "Надіслати ще раз через 45 с" })).toBeDefined();
    expect(resendButton("Надіслати ще раз через 45 с").disabled).toBe(true);
  });

  test("503 показує «Не вдалося надіслати лист»", async () => {
    const { user } = await openWithClock({
      [RESEND_ROUTE]: () => apiError(503, "mail_unavailable", "Лист не надіслано"),
    });
    await advance(60_000);

    await user.click(resendButton(RESEND));

    expect((await screen.findByRole("alert")).textContent).toContain("Не вдалося надіслати лист");
    expect(resendButton(RESEND).disabled).toBe(false);
  });

  test("збій мережі під час повторної відправки показує загальне повідомлення", async () => {
    const { user } = await openWithClock({ [RESEND_ROUTE]: () => Promise.reject(new TypeError("offline")) as never });
    await advance(60_000);

    await user.click(resendButton(RESEND));

    expect((await screen.findByRole("alert")).textContent).toContain("Не вдалося звʼязатися з сервером. Спробуй ще раз.");
  });

  test("запит уже недійсний (422 signup_expired) — екран з поверненням до початку реєстрації", async () => {
    const { user } = await openWithClock({
      [RESEND_ROUTE]: () => fieldError("signup_id", "signup_expired", "Запит недійсний"),
    });
    await advance(60_000);

    await user.click(resendButton(RESEND));

    await screen.findByRole("heading", { level: 1, name: "Запит прострочено" });
  });
});
