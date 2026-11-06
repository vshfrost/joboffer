import { InvalidCredentialsError, ServiceUnavailableError, TooManyAttemptsError } from "../domain/authErrors";
import type { AuthProviders, Session } from "../domain/session";
import type { AuthApi } from "../ports/authApi";

export type LoginFailure =
  | { kind: "invalid_credentials" }
  | { kind: "too_many_attempts"; retryAfterSeconds: number }
  | { kind: "unavailable" };

export type LoginOutcome = { ok: true; session: Session } | { ok: false; failure: LoginFailure };

export interface AuthServices {
  login(email: string, password: string): Promise<LoginOutcome>;
  /** `null` — сесії нема або перевірити її не вдалося: у обох випадках далі потрібен вхід. */
  currentSession(): Promise<Session | null>;
  /** `true` — сервер підтвердив вихід. */
  logout(): Promise<boolean>;
  /** Не вдалося дізнатися — вважаємо, що лише пароль. */
  providers(): Promise<AuthProviders>;
  googleStartUrl(next: string): string;
}

export function createAuthServices(api: AuthApi): AuthServices {
  return {
    async login(email, password) {
      try {
        return { ok: true, session: await api.login(email, password) };
      } catch (error) {
        if (error instanceof InvalidCredentialsError) {
          return { ok: false, failure: { kind: "invalid_credentials" } };
        }
        if (error instanceof TooManyAttemptsError) {
          return { ok: false, failure: { kind: "too_many_attempts", retryAfterSeconds: error.retryAfterSeconds } };
        }
        if (error instanceof ServiceUnavailableError) {
          return { ok: false, failure: { kind: "unavailable" } };
        }
        throw error;
      }
    },

    async currentSession() {
      try {
        return await api.currentSession();
      } catch (error) {
        if (error instanceof ServiceUnavailableError) {
          return null;
        }
        throw error;
      }
    },

    async logout() {
      try {
        await api.logout();
        return true;
      } catch (error) {
        if (error instanceof ServiceUnavailableError) {
          return false;
        }
        throw error;
      }
    },

    async providers() {
      try {
        return await api.providers();
      } catch (error) {
        if (error instanceof ServiceUnavailableError) {
          return { google: false };
        }
        throw error;
      }
    },

    googleStartUrl(next) {
      return api.googleStartUrl(next);
    },
  };
}
