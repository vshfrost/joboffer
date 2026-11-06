/** Реєстрація за запрошенням: що користувач вводить і що пам'ятає екран коду. */

/** Скільки цифр у коді з листа. */
export const CODE_LENGTH = 6;

/** Не раніше, ніж через стільки секунд сервер дозволяє попросити код ще раз. */
export const RESEND_WAIT_SECONDS = 60;

export interface SignupDraft {
  email: string;
  password: string;
  /** Порожнє — сервер візьме частину email до `@`. */
  displayName: string;
  invite: string;
  /** Розв'язок ALTCHA (base64-JSON віджета). */
  altcha: string;
  /** Приманка для ботів: у людини порожня. */
  website: string;
}

/** Реєстрацію розпочато: код надіслано на `email`, чекаємо його на екрані коду. */
export interface SignupProgress {
  signupId: string;
  email: string;
  /** Запрошення лишається для повернення на початок, якщо запит прострочиться. */
  invite: string;
}

/** Стан переходу на екран коду; будь-що інше (відкрито напряму, стара історія) — реєстрації нема. */
export function parseSignupProgress(state: unknown): SignupProgress | null {
  const value = state as Record<string, unknown> | null;
  const signupId = value?.["signupId"];
  const email = value?.["email"];
  const invite = value?.["invite"];
  return typeof signupId === "string" && typeof email === "string" && typeof invite === "string"
    ? { signupId, email, invite }
    : null;
}
