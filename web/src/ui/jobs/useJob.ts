import { useCallback, useEffect, useState } from "react";

import type { Job } from "../../domain/jobs";
import { useJobsServices } from "./JobsServices";

export type JobState = { status: "loading" } | { status: "not-found" } | { status: "error" } | { status: "ready"; job: Job };

export interface JobApi {
  state: JobState;
  reload(): void;
  /** Перечитує вакансію без скелетона: після «Не цікаво» чи «Повернути» сторінка лишається на місці. */
  refresh(): Promise<void>;
}

/** Вакансія за номером; `null` — номер не з адреси (такої вакансії нема, запиту не буде). */
export function useJob(id: number | null): JobApi {
  const services = useJobsServices();
  const [state, setState] = useState<JobState>(id === null ? { status: "not-found" } : { status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (id === null) {
      setState({ status: "not-found" });
      return;
    }
    let cancelled = false;
    setState({ status: "loading" });
    void services.load(id).then((outcome) => {
      if (!cancelled) {
        setState(outcome.ok ? { status: "ready", job: outcome.job } : { status: outcome.kind === "not-found" ? "not-found" : "error" });
      }
    });
    return () => {
      cancelled = true;
    };
  }, [services, id, attempt]);

  const reload = useCallback(() => setAttempt((current) => current + 1), []);
  const refresh = useCallback(async () => {
    if (id === null) {
      return;
    }
    const outcome = await services.load(id);
    if (outcome.ok) {
      setState({ status: "ready", job: outcome.job });
    }
  }, [services, id]);
  return { state, reload, refresh };
}
