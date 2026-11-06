import type { AuthProviders, Session } from "../domain/session";

/** API входу. CSRF-токен — справа адаптера: у домен і UI він не виходить. */
export interface AuthApi {
  /** Кидає InvalidCredentialsError, TooManyAttemptsError або ServiceUnavailableError. */
  login(email: string, password: string): Promise<Session>;
  /** `null` — сесії нема. Інші збої кидають ServiceUnavailableError. */
  currentSession(): Promise<Session | null>;
  /** Кидає ServiceUnavailableError, якщо сервер вихід не підтвердив. */
  logout(): Promise<void>;
  /** Які способи входу ввімкнено. Кидає ServiceUnavailableError. */
  providers(): Promise<AuthProviders>;
  /** Адреса, на яку веде кнопка «Увійти через Google»: це перехід браузера, а не fetch. */
  googleStartUrl(next: string): string;
}
