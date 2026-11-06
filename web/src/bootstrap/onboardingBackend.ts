/** Підроблений бекенд онбордингу: `/api/onboarding` над станом у памʼяті поверх бекенду профілю (хаб його вантажить). */
import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { profileBackend, type ProfileBackend } from "./profileBackend";
import { json, noContent, renderClient, type Handler } from "./testClient";

export const STEP_KEYS = ["goal", "locations", "contacts", "claude", "original_cv", "photo", "mail"] as const;
export const REQUIRED_KEYS = ["goal", "locations", "contacts", "claude", "original_cv"] as const;
const OPTIONAL_KEYS: readonly string[] = ["photo", "mail"];

export interface OnboardingState {
  /** Кроки, зроблені за даними користувача. */
  done?: readonly string[];
  /** Підказки, які вже показували. */
  seen?: readonly string[];
  /** Підказки, які користувач сховав (на сервері вони й побачені). */
  dismissed?: readonly string[];
}

export interface OnboardingBackend extends ProfileBackend {
  done: Set<string>;
  seen: Set<string>;
  dismissed: Set<string>;
  /** Усі запити до `/api/onboarding…` у порядку надходження: «МЕТОД /шлях». */
  calls: string[];
}

export function onboardingBody(state: { done: ReadonlySet<string>; seen: ReadonlySet<string>; dismissed: ReadonlySet<string> }) {
  return {
    steps: STEP_KEYS.map((key) => ({ key, done: state.done.has(key), optional: OPTIONAL_KEYS.includes(key) })),
    tips: STEP_KEYS.map((key) => ({
      key,
      seen: state.seen.has(key) || state.dismissed.has(key),
      dismissed: state.dismissed.has(key),
    })),
    complete: REQUIRED_KEYS.every((key) => state.done.has(key)),
  };
}

/** `overrides` замінюють відповідь за ключем «МЕТОД /шлях» (наприклад, `GET /api/onboarding`). */
export function onboardingBackend(initial: OnboardingState = {}, overrides: Record<string, Handler> = {}): OnboardingBackend {
  const calls: string[] = [];
  const state = {
    done: new Set(initial.done ?? []),
    seen: new Set(initial.seen ?? []),
    dismissed: new Set(initial.dismissed ?? []),
  };
  const track =
    (key: string, handler: Handler): Handler =>
    (init) => {
      calls.push(key);
      return handler(init);
    };
  const routes: Record<string, Handler> = {
    "GET /api/onboarding": track("GET /api/onboarding", () => json(200, onboardingBody(state), { "Cache-Control": "no-store" })),
  };
  for (const key of STEP_KEYS) {
    const seen = `POST /api/onboarding/tips/${key}/seen`;
    const dismiss = `POST /api/onboarding/tips/${key}/dismiss`;
    routes[seen] = track(seen, () => {
      state.seen.add(key);
      return noContent();
    });
    routes[dismiss] = track(dismiss, () => {
      state.dismissed.add(key);
      return noContent();
    });
  }
  const wrapped = Object.fromEntries(Object.entries(overrides).map(([key, handler]) => [key, track(key, handler)]));
  const rest = profileBackend(undefined, { ...routes, ...wrapped });
  return Object.assign(rest, state, { calls });
}

/** Хаб профілю з онбордингом; чекає, поки з'явиться картка «Перші кроки». */
export async function openHubWithOnboarding(backend: OnboardingBackend) {
  const view = renderClient("/profile", backend.fetchFn);
  const card = await screen.findByRole("region", { name: "Перші кроки" });
  return { view, card, user: userEvent.setup() };
}

/** Дає відповідям, що вже в дорозі, дійти до екрана: потрібно, щоб довести, що чогось на екрані немає. */
export async function settle() {
  await act(() => new Promise<void>((resolve) => setTimeout(resolve, 30)));
}
