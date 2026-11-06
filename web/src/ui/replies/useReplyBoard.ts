import { useCallback, useEffect, useState } from "react";

import type { RepliesProblem } from "../../application/replies";
import type { ReplyBoard, ReplyCounts, ReplyQuery } from "../../domain/replies";
import { useRepliesServices } from "./RepliesServices";

export type ReplyBoardState = { status: "loading" } | { status: "error"; problem: RepliesProblem } | { status: "ready"; board: ReplyBoard };

/** Черга за запитом; новий запит чи повтор показують скелетон, а застарілу відповідь відкидають. Лічильники лишаються з останньої відповіді. */
export function useReplyBoard(query: ReplyQuery): { state: ReplyBoardState; counts: ReplyCounts | null; reload(): void } {
  const services = useRepliesServices();
  const [state, setState] = useState<ReplyBoardState>({ status: "loading" });
  const [counts, setCounts] = useState<ReplyCounts | null>(null);
  const [attempt, setAttempt] = useState(0);
  const key = JSON.stringify(query);

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });
    void services.board(JSON.parse(key) as ReplyQuery).then((outcome) => {
      if (cancelled) {
        return;
      }
      if (outcome.ok) {
        setCounts(outcome.board.counts);
        setState({ status: "ready", board: outcome.board });
      } else {
        setState({ status: "error", problem: outcome.kind });
      }
    });
    return () => {
      cancelled = true;
    };
  }, [services, key, attempt]);

  const reload = useCallback(() => setAttempt((current) => current + 1), []);
  return { state, counts, reload };
}
