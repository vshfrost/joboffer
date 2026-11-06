import { useCallback, useEffect, useState } from "react";

import type { MailProblem } from "../../application/mail";
import type { MailList, MailQuery } from "../../domain/mail";
import { useMailServices } from "./MailServices";

export type MailListState = { status: "loading" } | { status: "error"; problem: MailProblem } | { status: "ready"; list: MailList };

/** «Вхідні» за запитом; новий запит чи повтор показують скелетон, а застарілу відповідь відкидають. */
export function useMailList(query: MailQuery): { state: MailListState; reload(): void } {
  const services = useMailServices();
  const [state, setState] = useState<MailListState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const key = JSON.stringify(query);

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });
    void services.list(JSON.parse(key) as MailQuery).then((outcome) => {
      if (!cancelled) {
        setState(outcome.ok ? { status: "ready", list: outcome.list } : { status: "error", problem: outcome.kind });
      }
    });
    return () => {
      cancelled = true;
    };
  }, [services, key, attempt]);

  const reload = useCallback(() => setAttempt((current) => current + 1), []);
  return { state, reload };
}
