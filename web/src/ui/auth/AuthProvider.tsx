import { createContext, use, useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import type { AuthServices, LoginFailure } from "../../application/auth";
import type { AuthProviders, Session, User } from "../../domain/session";

export type AuthState =
  | { status: "loading" }
  /** `justSignedOut`: вихід щойно підтверджено — після нього `next` не запамʼятовується. */
  | { status: "anonymous"; justSignedOut: boolean }
  | { status: "authenticated"; user: User };

interface Auth {
  state: AuthState;
  /** `null` — вхід вдався. */
  login(email: string, password: string): Promise<LoginFailure | null>;
  /** `true` — вихід підтверджено сервером. */
  logout(): Promise<boolean>;
  /** Сесію вже відкрито поза входом (реєстрація за кодом): далі застосунок вважає користувача увійшлим. */
  adopt(session: Session): void;
  /** Екран входу показано після виходу: далі гард знову запамʼятовує `next`. */
  acknowledgeSignOut(): void;
  providers(): Promise<AuthProviders>;
  googleStartUrl(next: string): string;
}

const AuthContext = createContext<Auth | null>(null);

/** Стан сесії для UI. Сесію визначає `GET /auth/me` при монтуванні; токени сюди не потрапляють. */
export function AuthProvider({ services, children }: { services: AuthServices; children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    void services.currentSession().then((session) => {
      if (!cancelled) {
        setState(
          session === null
            ? { status: "anonymous", justSignedOut: false }
            : { status: "authenticated", user: session.user },
        );
      }
    });
    return () => {
      cancelled = true;
    };
  }, [services]);

  const login = useCallback(
    async (email: string, password: string) => {
      const outcome = await services.login(email, password);
      if (!outcome.ok) {
        return outcome.failure;
      }
      setState({ status: "authenticated", user: outcome.session.user });
      return null;
    },
    [services],
  );

  const logout = useCallback(async () => {
    const confirmed = await services.logout();
    if (confirmed) {
      setState({ status: "anonymous", justSignedOut: true });
    }
    return confirmed;
  }, [services]);

  const adopt = useCallback((session: Session) => {
    setState({ status: "authenticated", user: session.user });
  }, []);

  const acknowledgeSignOut = useCallback(() => {
    setState((current) =>
      current.status === "anonymous" && current.justSignedOut ? { status: "anonymous", justSignedOut: false } : current,
    );
  }, []);

  const value = useMemo(
    () => ({
      state,
      login,
      logout,
      adopt,
      acknowledgeSignOut,
      providers: () => services.providers(),
      googleStartUrl: (next: string) => services.googleStartUrl(next),
    }),
    [state, login, logout, adopt, acknowledgeSignOut, services],
  );
  return <AuthContext value={value}>{children}</AuthContext>;
}

export function useAuth(): Auth {
  const auth = use(AuthContext);
  if (auth === null) {
    throw new Error("useAuth потребує AuthProvider");
  }
  return auth;
}
