import { createContext, use, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import type { MailProblem } from "../../application/mail";
import type { MailSettings, ManualSync } from "../../domain/mail";
import { useMailServices } from "./MailServices";
import { problemText } from "./texts";

export type SettingsState = { status: "loading" } | { status: "error"; problem: MailProblem } | { status: "ready"; settings: MailSettings };

export type RotateResult = { ok: true } | { ok: false; message: string };

interface MailContextValue {
  state: SettingsState;
  reload(): void;
  /** Скільки синків вручну лишилось: відповідь сервера на запит свіжіша за налаштування. */
  manual: ManualSync | null;
  /** Лише відповідь сервера на запит синку цього візиту; `null` — запитів ще не було. */
  manualAfterSync: ManualSync | null;
  /** Запит синку цього візиту вже в черзі. */
  queued: boolean;
  requesting: boolean;
  /** Результат запиту синку, що не вдався (або ліміт). */
  syncMessage: string;
  requestSync(): Promise<void>;
  rotate(): Promise<RotateResult>;
}

const MailContext = createContext<MailContextValue | null>(null);

/** Налаштування пошти й синк на час візиту в розділ: «Вхідні» й «Налаштування» ділять один стан. */
export function MailProvider({ children }: { children: ReactNode }) {
  const services = useMailServices();
  const [state, setState] = useState<SettingsState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [manualAfterSync, setManualAfterSync] = useState<ManualSync | null>(null);
  const [queued, setQueued] = useState(false);
  const [requesting, setRequesting] = useState(false);
  const [syncMessage, setSyncMessage] = useState("");
  // Подвійний клік у межах одного кадру: стан ще старий, тож ворота — у ref.
  const inFlight = useRef(false);

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });
    void services.settings().then((outcome) => {
      if (!cancelled) {
        setState(outcome.ok ? { status: "ready", settings: outcome.settings } : { status: "error", problem: outcome.kind });
      }
    });
    return () => {
      cancelled = true;
    };
  }, [services, attempt]);

  const reload = useCallback(() => setAttempt((current) => current + 1), []);

  const requestSync = useCallback(async () => {
    if (inFlight.current) {
      return;
    }
    inFlight.current = true;
    setRequesting(true);
    setSyncMessage("");
    const outcome = await services.requestSync();
    if (outcome.ok) {
      setManualAfterSync(outcome.manual);
      setQueued(true);
    } else {
      setSyncMessage(
        outcome.kind === "limit" ? outcome.message : problemText(outcome.kind, "запитати синк", "Не вдалося запитати синк. Спробуй ще раз."),
      );
    }
    inFlight.current = false;
    setRequesting(false);
  }, [services]);

  const rotate = useCallback(async (): Promise<RotateResult> => {
    const outcome = await services.rotate();
    if (outcome.ok) {
      setState({ status: "ready", settings: outcome.settings });
      return { ok: true };
    }
    return { ok: false, message: problemText(outcome.kind, "змінити адресу", "Не вдалося змінити адресу. Спробуй ще раз.") };
  }, [services]);

  const manual = manualAfterSync ?? (state.status === "ready" ? state.settings.manual : null);
  const value = useMemo(
    () => ({ state, reload, manual, manualAfterSync, queued, requesting, syncMessage, requestSync, rotate }),
    [state, reload, manual, manualAfterSync, queued, requesting, syncMessage, requestSync, rotate],
  );
  return <MailContext value={value}>{children}</MailContext>;
}

export function useMail(): MailContextValue {
  const value = use(MailContext);
  if (value === null) {
    throw new Error("Пошта потребує MailProvider");
  }
  return value;
}
