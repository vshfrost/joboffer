import { CircleAlert } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";

import type { LoginFailure } from "../../application/auth";
import { retryMinutes, safeNextPath } from "../../domain/session";
import { useAuth } from "../auth/AuthProvider";
import { GoogleLogo } from "../auth/GoogleLogo";
import { Button } from "../components/button";
import { Input } from "../components/input";
import { Spinner } from "../components/spinner";
import { useCountdown } from "../lib/useCountdown";
import { usePageTitle } from "../lib/usePageTitle";

const MESSAGES = {
  invalid_credentials: "Невірний email або пароль",
  unavailable: "Не вдалося звʼязатися з сервером. Спробуй ще раз.",
} as const;

const GOOGLE_MESSAGES: Record<string, string> = {
  email_required: "Google не передав підтверджений email — вхід неможливий",
  cancelled: "Вхід скасовано",
};
/** Кнопка за гайдлайнами Google: біла, рамка #747775, текст #1F1F1F; тема застосунку лише світла, тож темного варіанта нема. */
const GOOGLE_BUTTON =
  "inline-flex h-10 w-full items-center justify-center gap-3 rounded-lg border border-[#747775] bg-white text-nav font-medium text-[#1F1F1F] transition-colors duration-140 hover:bg-[#f1f1f1] pointer-coarse:h-11";
const GOOGLE_FAILED = "Не вдалося увійти через Google. Спробуй ще раз.";

/** Повідомлення після повернення з Google: `?error=` ставить бекенд. */
function googleMessage(error: string | null): { text: string; tone: "danger" | "warning" } | null {
  if (error === null) {
    return null;
  }
  return { text: GOOGLE_MESSAGES[error] ?? GOOGLE_FAILED, tone: error === "cancelled" ? "warning" : "danger" };
}

function messageFor(failure: LoginFailure | null, waitSeconds: number): { text: string; tone: "danger" | "warning" } | null {
  if (failure === null) {
    return null;
  }
  if (failure.kind === "too_many_attempts") {
    return waitSeconds > 0 ? { text: `Забагато спроб, спробуй за ~${retryMinutes(waitSeconds)} хв`, tone: "warning" } : null;
  }
  return { text: MESSAGES[failure.kind], tone: "danger" };
}

export function LoginPage() {
  usePageTitle("Вхід");
  const { login, providers, googleStartUrl } = useAuth();
  const [params] = useSearchParams();
  const { remaining, start } = useCountdown();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [failure, setFailure] = useState<LoginFailure | null>(null);
  const [googleEnabled, setGoogleEnabled] = useState(false);
  const [googleBusy, setGoogleBusy] = useState(false);
  const [googleError, setGoogleError] = useState<string | null>(params.get("error"));
  const passwordField = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let cancelled = false;
    void providers().then((available) => {
      if (!cancelled) {
        setGoogleEnabled(available.google);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [providers]);

  // Назад із Google браузер може показати сторінку з пам'яті: кнопка не лишається зайнятою.
  useEffect(() => {
    const reset = () => {
      setGoogleBusy(false);
    };
    window.addEventListener("pageshow", reset);
    return () => {
      window.removeEventListener("pageshow", reset);
    };
  }, []);

  const blocked = submitting || remaining > 0;
  const message = messageFor(failure, remaining) ?? googleMessage(googleError);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (blocked) {
      return;
    }
    setSubmitting(true);
    setFailure(null);
    setGoogleError(null);
    const result = await login(email, password);
    setSubmitting(false);
    if (result === null) {
      return;
    }
    setFailure(result);
    if (result.kind === "too_many_attempts") {
      start(result.retryAfterSeconds);
    }
    setPassword("");
    passwordField.current?.focus();
  }

  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-6 px-4 py-8">
      <div className="flex items-center gap-2.5">
        <img src={`${import.meta.env.BASE_URL}brand/logo.svg`} alt="" width={32} height={32} className="size-8" />
        <span className="text-2xl font-semibold tracking-tight">joboffer</span>
      </div>
      <div className="w-full max-w-sm rounded-xl border border-border bg-card p-6 md:p-8">
        <h1 className="text-page-title font-semibold tracking-tight">Вхід</h1>
        <p className="mt-1 text-sm text-muted-foreground">Увійди, щоб продовжити.</p>
        <form onSubmit={(event) => void submit(event)} className="mt-6 flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="login-email" className="text-nav font-medium">
              Email
            </label>
            <Input
              id="login-email"
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(event) => {
                setEmail(event.target.value);
              }}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="login-password" className="text-nav font-medium">
              Пароль
            </label>
            <Input
              id="login-password"
              ref={passwordField}
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => {
                setPassword(event.target.value);
              }}
            />
          </div>
          {message === null ? null : (
            <div
              role="alert"
              className={
                message.tone === "danger"
                  ? "flex items-start gap-2 rounded-lg bg-status-danger px-3 py-2 text-caption text-status-danger-foreground"
                  : "flex items-start gap-2 rounded-lg bg-status-warning px-3 py-2 text-caption text-status-warning-foreground"
              }
            >
              <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
              <span>{message.text}</span>
            </div>
          )}
          <Button type="submit" disabled={blocked} loading={submitting}>
            {submitting ? "Входимо…" : "Увійти"}
          </Button>
        </form>
        {googleEnabled ? (
          <>
            <div className="my-4 flex items-center gap-3 text-caption text-muted-foreground" aria-hidden="true">
              <hr className="flex-1 border-border" />
              або
              <hr className="flex-1 border-border" />
            </div>
            <a
              href={googleStartUrl(safeNextPath(params.get("next")))}
              aria-busy={googleBusy || undefined}
              onClick={(event) => {
                if (googleBusy) {
                  event.preventDefault();
                  return;
                }
                setGoogleBusy(true);
              }}
              className={GOOGLE_BUTTON}
            >
              {googleBusy ? <Spinner className="size-5" /> : <GoogleLogo className="size-5 shrink-0" />}
              {googleBusy ? "Переходимо до Google…" : "Увійти через Google"}
            </a>
          </>
        ) : null}
      </div>
      <nav aria-label="Правові документи" className="flex flex-wrap justify-center gap-x-4 gap-y-1 text-caption text-muted-foreground">
        <Link to="/terms" className="hover:underline">
          Умови користування
        </Link>
        <Link to="/privacy" className="hover:underline">
          Політика конфіденційності
        </Link>
      </nav>
    </main>
  );
}
