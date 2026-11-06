import { useCallback, useEffect, useState } from "react";

import type { RepliesProblem } from "../../application/replies";
import type { ReplyDetail } from "../../domain/replies";
import { useRepliesServices } from "./RepliesServices";

export type ReplyDetailState =
  | { status: "loading" }
  | { status: "error"; problem: RepliesProblem | "not-found" }
  | { status: "ready"; detail: ReplyDetail };

/** Відповідь із текстом; інший номер чи повтор показують «завантаження», а застарілу відповідь відкидають. */
export function useReplyDetail(id: number): { state: ReplyDetailState; reload(): void } {
  const services = useRepliesServices();
  const [state, setState] = useState<ReplyDetailState>({ status: "loading" });
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
