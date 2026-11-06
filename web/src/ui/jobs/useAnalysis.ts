import { useCallback, useEffect, useState } from "react";

import type { JobAnalysis } from "../../domain/analysis";
import { useJobsServices } from "./JobsServices";

export type AnalysisState =
  | { status: "loading" }
  /** Вакансії без тексту аналізувати нічого: запиту до сервера нема. */
  | { status: "unavailable-for-job" }
  /** Аналізу ще нема: стан даних, не збій. */
  | { status: "none" }
  | { status: "error" }
  | { status: "ready"; analysis: JobAnalysis };

export interface AnalysisApi {
  state: AnalysisState;
  reload(): void;
}

/** Збережений аналіз вакансії. Лише читає: аналіз запускає Claude через MCP, не цей хук. */
export function useAnalysis(id: number, enabled: boolean): AnalysisApi {
  const services = useJobsServices();
  const [state, setState] = useState<AnalysisState>(enabled ? { status: "loading" } : { status: "unavailable-for-job" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!enabled) {
      setState({ status: "unavailable-for-job" });
      return;
    }
    let cancelled = false;
    setState({ status: "loading" });
    void services.loadAnalysis(id).then((outcome) => {
      if (cancelled) {
        return;
      }
      if (outcome.ok) {
        setState({ status: "ready", analysis: outcome.analysis });
      } else {
        setState({ status: outcome.kind === "none" ? "none" : "error" });
      }
    });
    return () => {
      cancelled = true;
    };
  }, [services, id, enabled, attempt]);

  const reload = useCallback(() => setAttempt((current) => current + 1), []);
  return { state, reload };
}
