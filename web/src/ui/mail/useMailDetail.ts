import { useCallback, useEffect, useState } from "react";

import type { MailProblem } from "../../application/mail";
import type { MailDetail } from "../../domain/mail";
import { useMailServices } from "./MailServices";

export type MailDetailState =
  | { status: "loading" }
  | { status: "error"; problem: MailProblem | "not-found" }
  | { status: "ready"; detail: MailDetail };

/** Лист із текстом; інший номер чи повтор показують «завантаження», а застарілу відповідь відкидають. */
export function useMailDetail(id: number): { state: MailDetailState; reload(): void } {
  const services = useMailServices();
  const [state, setState] = useState<MailDetailState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });
    void services.get(id).then((outcome) => {
      if (!cancelled) {
        setState(outcome.ok ? { status: "ready", detail: outcome.detail } : { status: "error", problem: outcome.kind });
      }
    });
    return () => {
      cancelled = true;
    };
  }, [services, id, attempt]);

  const reload = useCallback(() => setAttempt((current) => current + 1), []);
  return { state, reload };
}
