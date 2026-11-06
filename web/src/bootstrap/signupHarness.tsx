/** Спільне для тестів реєстрації: двійник віджета ALTCHA, відповіді API й проходження форми. */
import { act, render, screen } from "@testing-library/react";
import type userEvent from "@testing-library/user-event";
import { useEffect, type ComponentType } from "react";
import { createMemoryRouter, RouterProvider, useLocation } from "react-router";
import { vi } from "vitest";

import type { AltchaWidgetProps } from "../ui/signup/AltchaWidget";
import { Client } from "./Client";
import { fakeBackend, json, sessionBody, type Handler } from "./testClient";

export const INVITE = "inv-token_42";
export const EMAIL = "new.user@example.com";
export const PASSWORD = "Str0ng!pass";
export const SIGNUP_ID = "sg-7f3a";
export const TERMS_VERSION = "2026-10-28.1";

export const NOT_AUTHENTICATED = { code: "not_authenticated", message: "Потрібен вхід", field_errors: [], correlation_id: "c1" };
export const ANONYMOUS = { "GET /api/auth/me": () => json(401, NOT_AUTHENTICATED) };

export function apiError(status: number, code: string, message: string, extra: Record<string, unknown> = {}, headers: Record<string, string> = {}) {
  return json(status, { code, message, field_errors: [], correlation_id: "c", ...extra }, headers);
}

export function fieldError(field: string, code: string, message: string) {
  return apiError(422, code, message, { field_errors: [{ field, message }] });
}

let solutions = 0;

/** Кожне монтування віджета «розв'язує» задачу заново й дає наступний розв'язок: payload-1, payload-2… */
export function FakeAltcha({ onSolved }: AltchaWidgetProps) {
  useEffect(() => {
    solutions += 1;
    onSolved(`payload-${solutions}`);
  }, []);
  return <div data-testid="altcha-widget" />;
}

/** Розв'язок і його втрату віддає тест: так перевіряється, що без розв'язку форму не відправити. */
export function ManualAltcha({ onSolved, onReset }: AltchaWidgetProps) {
  return (
    <div data-testid="altcha-widget">
      <button
        type="button"
        onClick={() => {
          onSolved("manual-payload");
        }}
      >
        Розв'язати
      </button>
      <button type="button" onClick={onReset}>
        Прострочити
      </button>
    </div>
  );
}

export function resetAltcha() {
  solutions = 0;
}

export const SIGNUP_ROUTES: Record<string, Handler> = {
  ...ANONYMOUS,
  "GET /api/auth/signup/invite?invite=inv-token_42": () => json(200, { valid: true, expires_at: "2026-11-06T10:00:00Z" }),
  "GET /api/legal/terms": () => json(200, { doc: "terms", version: TERMS_VERSION, text: "Умови" }),
  "POST /api/auth/signup": () => json(202, { signup_id: SIGNUP_ID }),
  "POST /api/auth/signup/verify": () => json(201, sessionBody("csrf-signup")),
  "POST /api/auth/signup/resend": () => json(202, { signup_id: SIGNUP_ID }),
  // Після реєстрації відкривається профіль: його дані тут не важливі.
  "GET /api/profile": () => apiError(500, "internal_error", "x"),
};

export function signupBackend(overrides: Record<string, Handler> = {}) {
  return fakeBackend({ ...SIGNUP_ROUTES, ...overrides });
}

function LocationProbe() {
  const { pathname, search } = useLocation();
  return <span data-testid="location">{`${pathname}${search}`}</span>;
}

export function renderSignup(path: string, fetchFn: typeof fetch, widget: ComponentType<AltchaWidgetProps> = FakeAltcha) {
  const router = createMemoryRouter(
    [
      {
        path: "*",
        element: (
          <>
            <Client fetchFn={fetchFn} altchaWidget={widget} />
            <LocationProbe />
          </>
        ),
      },
    ],
    { initialEntries: [path] },
  );
  return Object.assign(render(<RouterProvider router={router} />), { router });
}

export const location = () => screen.getByTestId("location").textContent;

type User = ReturnType<typeof userEvent.setup>;

export async function fillForm(user: User, fields: { name?: string; consent?: boolean } = {}) {
  await user.type(await screen.findByLabelText("Email"), EMAIL);
  if (fields.name !== undefined) {
    await user.type(screen.getByLabelText(/Імʼя/), fields.name);
  }
  await user.type(screen.getByLabelText("Пароль"), PASSWORD);
  if (fields.consent ?? true) {
    await user.click(screen.getByRole("checkbox"));
  }
}

export const submitButton = () => screen.getByRole("button", { name: "Зареєструватися" }) as HTMLButtonElement;

/** Заповнює й відправляє форму реєстрації. */
export async function signUp(user: User, fields: { name?: string } = {}) {
  await fillForm(user, fields);
  await user.click(submitButton());
}

/** Доходить до екрана коду: реєстрація з валідним запрошенням. */
export async function reachVerify(user: User, backend: typeof fetch) {
  renderSignup(`/signup?invite=${INVITE}`, backend);
  await signUp(user);
  return await screen.findByLabelText("Код з листа");
}

export async function advance(ms: number) {
  await act(async () => {
    vi.advanceTimersByTime(ms);
  });
}

/** Лише інтервали й дата: проміси й затримки userEvent лишаються справжніми. */
export function useCountdownClock() {
  vi.useFakeTimers({ toFake: ["setInterval", "clearInterval", "Date"] });
}
