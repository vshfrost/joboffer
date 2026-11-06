import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import {
  advance,
  apiError,
  EMAIL,
  fieldError,
  fillForm,
  INVITE,
  location,
  ManualAltcha,
  PASSWORD,
  renderSignup,
  resetAltcha,
  SIGNUP_ID,
  signUp,
  signupBackend,
  submitButton,
  TERMS_VERSION,
  useCountdownClock,
} from "./signupHarness";
import { json } from "./testClient";

beforeEach(resetAltcha);
afterEach(() => {
  vi.useRealTimers();
});

async function openForm(overrides: Parameters<typeof signupBackend>[0] = {}) {
  const user = userEvent.setup();
  const backend = signupBackend(overrides);
  renderSignup(`/signup?invite=${INVITE}`, backend);
  await screen.findByRole("heading", { level: 1, name: "Реєстрація" });
  return { user, backend };
}

function posted(backend: ReturnType<typeof signupBackend>, path: string): Record<string, unknown>[] {
  return backend.mock.calls
    .filter(([url, init]) => url === path && init?.method === "POST")
    .map(([, init]) => JSON.parse(String(init?.body)) as Record<string, unknown>);
}

/** Текст, на який поле посилається через aria-describedby. */
function describedBy(field: HTMLElement): string {
  return (field.getAttribute("aria-describedby") ?? "")
    .split(" ")
    .map((id) => document.getElementById(id)?.textContent ?? "")
    .join(" ");
}

describe("поля форми", () => {
  test("email, імʼя й пароль мають підписи та автозаповнення браузера", async () => {
    await openForm();

    const email = screen.getByLabelText("Email");
    const name = screen.getByLabelText(/Імʼя/);
    const password = screen.getByLabelText("Пароль");
    expect(email.getAttribute("type")).toBe("email");
    expect(email.getAttribute("autocomplete")).toBe("email");
    expect(name.getAttribute("autocomplete")).toBe("name");
    expect(password.getAttribute("type")).toBe("password");
    expect(password.getAttribute("autocomplete")).toBe("new-password");
    expect(describedBy(password)).toContain("8 символів");
  });

  test("імʼя необовʼязкове, а email і пароль обовʼязкові", async () => {
    await openForm();

    expect((screen.getByLabelText(/Імʼя/) as HTMLInputElement).required).toBe(false);
    expect((screen.getByLabelText("Email") as HTMLInputElement).required).toBe(true);
    expect((screen.getByLabelText("Пароль") as HTMLInputElement).required).toBe(true);
  });

  test("для ботів є прихована приманка website, яку людина не бачить і не пройде табом", async () => {
    await openForm();

    const decoy = document.querySelector<HTMLInputElement>('input[name="website"]');
    expect(decoy).not.toBeNull();
    expect(decoy?.tabIndex).toBe(-1);
    expect(decoy?.closest("[aria-hidden='true']")).not.toBeNull();
    expect(decoy?.getAttribute("autocomplete")).toBe("off");
  });

  test("віджет ALTCHA стоїть у формі", async () => {
    await openForm();

    expect(screen.getByTestId("altcha-widget")).toBeDefined();
  });
});

describe("згода з умовами", () => {
  test("прапорець згоди має посилання на /terms і /privacy", async () => {
    await openForm();

    const terms = screen.getByRole("link", { name: "Умовами користування" });
    const privacy = screen.getByRole("link", { name: "Політикою конфіденційності" });
    expect(terms.getAttribute("href")).toBe("/terms");
    expect(privacy.getAttribute("href")).toBe("/privacy");
    const checkbox = screen.getByRole("checkbox");
    expect(checkbox.getAttribute("aria-checked")).toBe("false");
    expect(within(document.body).getByText(/Погоджуюсь з/)).toBeDefined();
  });

  test("без згоди кнопка вимкнена; зі згодою вмикається; знята згода вимикає знову", async () => {
    const { user } = await openForm();
    await user.type(screen.getByLabelText("Email"), EMAIL);
    await user.type(screen.getByLabelText("Пароль"), PASSWORD);

    expect(submitButton().disabled).toBe(true);
    await user.click(screen.getByRole("checkbox"));
    expect(submitButton().disabled).toBe(false);
    await user.click(screen.getByRole("checkbox"));
    expect(submitButton().disabled).toBe(true);
  });

  test("поки ALTCHA не розв'язано, кнопка вимкнена, навіть зі згодою; розв'язок вмикає її, а прострочений вимикає знову", async () => {
    const user = userEvent.setup();
    renderSignup(`/signup?invite=${INVITE}`, signupBackend(), ManualAltcha);
    await screen.findByRole("heading", { level: 1, name: "Реєстрація" });
    await fillForm(user);

    expect(submitButton().disabled).toBe(true);
    await user.click(screen.getByRole("button", { name: "Розв'язати" }));
    expect(submitButton().disabled).toBe(false);
    await user.click(screen.getByRole("button", { name: "Прострочити" }));
    expect(submitButton().disabled).toBe(true);
  });
});

describe("чому кнопка вимкнена", () => {
  const CONSENT = "Погодься з умовами користування";
  const ROBOT = "Дочекайся перевірки «я не робот»";

  test("без згоди під кнопкою підказка про згоду; зі згодою зникає", async () => {
    const { user } = await openForm();
    await user.type(screen.getByLabelText("Email"), EMAIL);
    await user.type(screen.getByLabelText("Пароль"), PASSWORD);

    expect(screen.getByText(CONSENT)).toBeDefined();
    await user.click(screen.getByRole("checkbox"));
    expect(screen.queryByText(CONSENT)).toBeNull();
  });

  test("зі згодою, але без розв'язку ALTCHA — підказка про перевірку «я не робот»; розв'язок прибирає її", async () => {
    const user = userEvent.setup();
    renderSignup(`/signup?invite=${INVITE}`, signupBackend(), ManualAltcha);
    await screen.findByRole("heading", { level: 1, name: "Реєстрація" });
    await fillForm(user);

    expect(screen.getByText(ROBOT)).toBeDefined();
    expect(screen.queryByText(CONSENT)).toBeNull();
    await user.click(screen.getByRole("button", { name: "Розв'язати" }));
    expect(screen.queryByText(ROBOT)).toBeNull();
  });

  test("і згоди нема, і ALTCHA не розв'язано — спершу згода", async () => {
    const user = userEvent.setup();
    renderSignup(`/signup?invite=${INVITE}`, signupBackend(), ManualAltcha);
    await screen.findByRole("heading", { level: 1, name: "Реєстрація" });
    await fillForm(user, { consent: false });

    expect(screen.getByText(CONSENT)).toBeDefined();
    expect(screen.queryByText(ROBOT)).toBeNull();
  });
});

describe("відправлення форми", () => {
  test("поки сервер відповідає, кнопка зайнята: «Реєструємо…», aria-busy, підказок нема", async () => {
    const { user } = await openForm({ "POST /api/auth/signup": () => new Promise<Response>(() => undefined) as unknown as Response });

    await fillForm(user);
    await user.click(submitButton());

    const button = await screen.findByRole("button", { name: "Реєструємо…" });
    expect(button.getAttribute("aria-busy")).toBe("true");
    expect((button as HTMLButtonElement).disabled).toBe(true);
    expect(screen.queryByText("Погодься з умовами користування")).toBeNull();
  });

  test("надсилає дані з версією умов, розв'язком ALTCHA й запрошенням та веде на екран коду", async () => {
    const { user, backend } = await openForm();

    await signUp(user, { name: "Нова Людина" });

    await screen.findByLabelText("Код з листа");
    expect(posted(backend, "/api/auth/signup")).toEqual([
      {
        email: EMAIL,
        password: PASSWORD,
        display_name: "Нова Людина",
        invite: INVITE,
        terms_version: TERMS_VERSION,
        altcha: "payload-1",
        website: "",
      },
    ]);
    expect(location()).toBe("/signup/verify");
  });

  test("без імені надсилається порожнє display_name", async () => {
    const { user, backend } = await openForm();

    await signUp(user);

    await screen.findByLabelText("Код з листа");
    expect(posted(backend, "/api/auth/signup")[0]).toMatchObject({ display_name: "" });
  });

  test("заповнена приманка website надсилається як є", async () => {
    const { user, backend } = await openForm();
    await fillForm(user);

    const decoy = document.querySelector<HTMLInputElement>('input[name="website"]');
    await user.type(decoy as HTMLInputElement, "http://spam.example");
    await user.click(submitButton());

    await screen.findByLabelText("Код з листа");
    expect(posted(backend, "/api/auth/signup")[0]).toMatchObject({ website: "http://spam.example" });
  });

  test("версію умов бере з /legal/terms у момент відправлення", async () => {
    const { user, backend } = await openForm({
      "GET /api/legal/terms": () => json(200, { doc: "terms", version: "2027-01-05.2", text: "Умови" }),
    });

    await signUp(user);

    await screen.findByLabelText("Код з листа");
    expect(posted(backend, "/api/auth/signup")[0]).toMatchObject({ terms_version: "2027-01-05.2" });
  });

  test("поки запит іде, кнопка вимкнена й повторного запиту нема", async () => {
    const pending = new Promise<Response>(() => undefined);
    const { user, backend } = await openForm({ "POST /api/auth/signup": () => pending as unknown as Response });

    await signUp(user);
    const button = screen.getByRole("button", { name: "Реєструємо…" }) as HTMLButtonElement;
    await user.click(button);

    expect(button.disabled).toBe(true);
    expect(posted(backend, "/api/auth/signup")).toHaveLength(1);
  });
});

describe("помилки відправлення", () => {
  test("422 про пароль показано під полем пароля", async () => {
    const { user } = await openForm({
      "POST /api/auth/signup": () => fieldError("password", "password_weak", "Додай до пароля: цифру"),
    });

    await signUp(user);

    const password = screen.getByLabelText("Пароль");
    await waitFor(() => {
      expect(describedBy(password)).toContain("Додай до пароля: цифру");
    });
    expect(password.getAttribute("aria-invalid")).toBe("true");
    expect(location()).toBe(`/signup?invite=${INVITE}`);
  });

  test("422 про email показано під полем email", async () => {
    const { user } = await openForm({
      "POST /api/auth/signup": () => fieldError("email", "invalid_value", "Некоректний email"),
    });

    await signUp(user);

    const email = screen.getByLabelText("Email");
    await waitFor(() => {
      expect(describedBy(email)).toContain("Некоректний email");
    });
    expect(email.getAttribute("aria-invalid")).toBe("true");
  });

  test("422 про імʼя показано під полем імені", async () => {
    const { user } = await openForm({
      "POST /api/auth/signup": () => fieldError("display_name", "invalid_value", "Імʼя без пробілів на початку й у кінці"),
    });

    await signUp(user, { name: "Нова" });

    const name = screen.getByLabelText(/Імʼя/);
    await waitFor(() => {
      expect(describedBy(name)).toContain("Імʼя без пробілів на початку й у кінці");
    });
  });

  test("422 про версію умов показано біля згоди", async () => {
    const { user } = await openForm({
      "POST /api/auth/signup": () => fieldError("terms_version", "invalid_value", "Потрібна згода з поточною версією умов"),
    });

    await signUp(user);

    const checkbox = screen.getByRole("checkbox");
    await waitFor(() => {
      expect(describedBy(checkbox)).toContain("Потрібна згода з поточною версією умов");
    });
  });

  test("422 без відомого поля показано повідомленням форми", async () => {
    const { user } = await openForm({
      "POST /api/auth/signup": () => fieldError("something_else", "invalid_request", "Невірний запит"),
    });

    await signUp(user);

    expect((await screen.findByRole("alert")).textContent).toContain("Невірний запит");
  });

  test("422 з порожнім переліком полів показує повідомлення сервера на всю форму", async () => {
    const { user } = await openForm({
      "POST /api/auth/signup": () => apiError(422, "invalid_request", "Невірний запит"),
    });

    await signUp(user);

    expect((await screen.findByRole("alert")).textContent).toContain("Невірний запит");
  });

  test("422 без розбірливого тіла показує «Перевір введені дані.»", async () => {
    const { user } = await openForm({ "POST /api/auth/signup": () => new Response("oops", { status: 422 }) });

    await signUp(user);

    expect((await screen.findByRole("alert")).textContent).toContain("Перевір введені дані.");
  });

  test("422 challenge_failed просить пройти перевірку ще раз і дає віджету нову задачу", async () => {
    const answers = [apiError(422, "challenge_failed", "Перевірку не пройдено"), json(202, { signup_id: SIGNUP_ID })];
    const { user, backend } = await openForm({ "POST /api/auth/signup": () => answers.shift() as Response });

    await signUp(user);

    expect((await screen.findByRole("alert")).textContent).toContain("Перевірку не пройдено. Спробуй ще раз.");
    // Розв'язок одноразовий: віджет стартує заново, і наступна відправка йде вже з новим.
    await waitFor(() => {
      expect(submitButton().disabled).toBe(false);
    });
    await user.click(submitButton());
    await screen.findByLabelText("Код з листа");
    expect(posted(backend, "/api/auth/signup").map((body) => body["altcha"])).toEqual(["payload-1", "payload-2"]);
  });

  test("після будь-якої відмови нова відправка використовує новий розв'язок ALTCHA", async () => {
    const answers = [
      fieldError("password", "password_weak", "Додай до пароля: цифру"),
      json(202, { signup_id: SIGNUP_ID }),
    ];
    const { user, backend } = await openForm({ "POST /api/auth/signup": () => answers.shift() as Response });

    await signUp(user);
    await screen.findByText("Додай до пароля: цифру");
    await user.click(submitButton());

    await screen.findByLabelText("Код з листа");
    expect(posted(backend, "/api/auth/signup").map((body) => body["altcha"])).toEqual(["payload-1", "payload-2"]);
  });

  test("503 показує «Не вдалося надіслати лист»", async () => {
    const { user } = await openForm({
      "POST /api/auth/signup": () => apiError(503, "mail_unavailable", "Лист не надіслано"),
    });

    await signUp(user);

    expect((await screen.findByRole("alert")).textContent).toContain("Не вдалося надіслати лист");
    expect(location()).toBe(`/signup?invite=${INVITE}`);
  });

  test("503 registration_closed — загальне повідомлення про збій, а не про лист", async () => {
    const { user } = await openForm({
      "POST /api/auth/signup": () => apiError(503, "registration_closed", "Реєстрацію закрито"),
    });

    await signUp(user);

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Не вдалося звʼязатися з сервером. Спробуй ще раз.");
    expect(alert.textContent).not.toContain("лист");
  });

  test("404 invite_invalid під час відправлення веде на екран недійсного посилання", async () => {
    const { user } = await openForm({
      "POST /api/auth/signup": () => apiError(404, "invite_invalid", "Запрошення недійсне"),
    });

    await signUp(user);

    await screen.findByRole("heading", { level: 1, name: "Посилання недійсне" });
    expect(screen.queryByLabelText("Email")).toBeNull();
  });

  test("збій мережі показує загальне повідомлення", async () => {
    const { user } = await openForm({ "POST /api/auth/signup": () => Promise.reject(new TypeError("offline")) as never });

    await signUp(user);

    expect((await screen.findByRole("alert")).textContent).toContain("Не вдалося звʼязатися з сервером. Спробуй ще раз.");
  });

  test("відповідь 202 без signup_id — загальне повідомлення", async () => {
    const { user } = await openForm({ "POST /api/auth/signup": () => json(202, { hello: "world" }) });

    await signUp(user);

    expect((await screen.findByRole("alert")).textContent).toContain("Не вдалося звʼязатися з сервером. Спробуй ще раз.");
    expect(location()).toBe(`/signup?invite=${INVITE}`);
  });

  test("не вдалося дізнатися версію умов — загальне повідомлення, реєстрація не надсилається", async () => {
    const { user, backend } = await openForm({ "GET /api/legal/terms": () => apiError(500, "internal_error", "x") });

    await signUp(user);

    expect((await screen.findByRole("alert")).textContent).toContain("Не вдалося звʼязатися з сервером. Спробуй ще раз.");
    expect(posted(backend, "/api/auth/signup")).toEqual([]);
  });
});

describe("ліміт реєстрацій (429)", () => {
  async function tooMany(retryAfter: Record<string, string>) {
    useCountdownClock();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const backend = signupBackend({
      "POST /api/auth/signup": () => apiError(429, "too_many_attempts", "Забагато спроб", {}, retryAfter),
    });
    renderSignup(`/signup?invite=${INVITE}`, backend);
    await screen.findByRole("heading", { level: 1, name: "Реєстрація" });
    await signUp(user);
    return { alert: await screen.findByRole("alert"), backend };
  }

  test("Retry-After: 600 показує «~10 хв» і вимикає кнопку", async () => {
    const { alert } = await tooMany({ "Retry-After": "600" });

    expect(alert.textContent).toContain("Забагато спроб, спробуй за ~10 хв");
    expect(submitButton().disabled).toBe(true);
  });

  test("без Retry-After відлік — 1 хвилина", async () => {
    const { alert } = await tooMany({});

    expect(alert.textContent).toContain("Забагато спроб, спробуй за ~1 хв");
  });

  test("по закінченні відліку повідомлення зникає, а кнопка знову доступна", async () => {
    await tooMany({ "Retry-After": "120" });

    await advance(60_000);
    expect(screen.getByRole("alert").textContent).toContain("~1 хв");
    expect(submitButton().disabled).toBe(true);

    await advance(60_000);
    expect(screen.queryByRole("alert")).toBeNull();
    await waitFor(() => {
      expect(submitButton().disabled).toBe(false);
    });
  });
});
