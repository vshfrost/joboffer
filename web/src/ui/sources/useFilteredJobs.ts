import { useCallback, useEffect, useRef, useState } from "react";

import type { SourcesProblem } from "../../application/sources";
import type { FilteredJob } from "../../domain/sources";
import { useSourcesServices } from "./SourcesServices";

export type FilteredState = { status: "loading" } | { status: "error"; problem: SourcesProblem } | { status: "ready"; jobs: FilteredJob[] };

/** Вакансії, що не проходять фільтр. `reload` показує скелетон, `refetch` мовчки оновлює; `remove` прибирає сховані номери. */
export function useFilteredJobs() {
  const services = useSourcesServices();
  const [state, setState] = useState<FilteredState>({ status: "loading" });
  // Номер останнього запиту: відповідь на попередній уже нікому не потрібна.
  const latest = useRef(0);

  const load = useCallback(
    async (silent: boolean) => {
      latest.current += 1;
      const ticket = latest.current;
      if (!silent) {
        setState({ status: "loading" });
      }
      const outcome = await services.filtered();
      if (ticket === latest.current) {
        setState(outcome.ok ? { status: "ready", jobs: outcome.jobs } : { status: "error", problem: outcome.kind });
      }
    },
    [services],
  );

  useEffect(() => {
    void load(false);
    return () => {
      latest.current += 1;
    };
  }, [load]);

  const reload = useCallback(() => void load(false), [load]);
  const refetch = useCallback(() => load(true), [load]);
  const remove = useCallback((numbers: readonly number[]) => {
    setState((current) => (current.status === "ready" ? { status: "ready", jobs: current.jobs.filter((job) => !numbers.includes(job.number)) } : current));
  }, []);
  return { state, reload, refetch, remove };
}
