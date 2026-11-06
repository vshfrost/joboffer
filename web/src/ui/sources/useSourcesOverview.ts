import { useCallback, useEffect, useRef, useState } from "react";

import type { SourcesProblem } from "../../application/sources";
import type { SourcesOverview } from "../../domain/sources";
import { useSourcesServices } from "./SourcesServices";

export type OverviewState = { status: "loading" } | { status: "error"; problem: SourcesProblem } | { status: "ready"; overview: SourcesOverview };

/**
 * Огляд джерел. `reload` показує скелетон, `refetch` мовчки оновлює дані (список лишається на екрані);
 * застаріла відповідь відкидається, `patch` правит уже завантажене після дії.
 */
export function useSourcesOverview() {
  const services = useSourcesServices();
  const [state, setState] = useState<OverviewState>({ status: "loading" });
  // Номер останнього запиту: відповідь на попередній уже нікому не потрібна.
  const latest = useRef(0);

  const load = useCallback(
    async (silent: boolean) => {
      latest.current += 1;
      const ticket = latest.current;
      if (!silent) {
        setState({ status: "loading" });
      }
      const outcome = await services.overview();
      if (ticket === latest.current) {
        setState(outcome.ok ? { status: "ready", overview: outcome.overview } : { status: "error", problem: outcome.kind });
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
  const patch = useCallback((change: (overview: SourcesOverview) => SourcesOverview) => {
    setState((current) => (current.status === "ready" ? { status: "ready", overview: change(current.overview) } : current));
  }, []);
  return { state, reload, refetch, patch };
}
