import { useCallback, useEffect, useState } from "react";

import type { Application } from "../../domain/applications";
import { useApplicationsServices } from "./ApplicationsServices";

/** `application: null` — на вакансію не подавались. */
export type ApplicationState = { status: "loading" } | { status: "error" } | { status: "ready"; application: Application | null };

export interface ApplicationApi {
  state: ApplicationState;
  reload(): void;
  /** Підставляє подачу з відповіді сервера (після збереження чи переходу) без нового запиту. */
  set(application: Application): void;
}

/** Подача на вакансію; застарілу відповідь відкидає. */
export function useApplication(jobId: number): ApplicationApi {
  const services = useApplicationsServices();
  const [state, setState] = useState<ApplicationState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });
    void services.load(jobId).then((outcome) => {
      if (!cancelled) {
        setState(outcome.ok ? { status: "ready", application: outcome.application } : { status: "error" });
      }
    });
    return () => {
      cancelled = true;
    };
  }, [services, jobId, attempt]);

  const reload = useCallback(() => setAttempt((current) => current + 1), []);
  const set = useCallback((application: Application) => setState({ status: "ready", application }), []);
  return { state, reload, set };
}
