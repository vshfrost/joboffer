import { useCallback, useEffect, useState } from "react";

import { NO_TAB_COUNTS, type JobList, type JobsQuery, type JobTabCounts } from "../../domain/jobs";
import { useJobsServices } from "./JobsServices";

export type ListState = { status: "loading" } | { status: "error" } | { status: "ready"; list: JobList };

export interface JobListApi {
  state: ListState;
  /** Лічильники табів з останньої відповіді сервера: лишаються, поки вантажиться інший таб. */
  counts: JobTabCounts;
  reload(): void;
  /** Прибирає вакансію зі списку на місці — без нового запиту списку й без миготіння скелетона; лічильники оновлює тихо. */
  drop(id: number): void;
}

/** Список за запитом; новий запит чи повтор показують скелетон, а застарілу відповідь відкидають. */
export function useJobList(query: JobsQuery): JobListApi {
  const services = useJobsServices();
  const [state, setState] = useState<ListState>({ status: "loading" });
  const [counts, setCounts] = useState<JobTabCounts>(NO_TAB_COUNTS);
  const [attempt, setAttempt] = useState(0);
  const key = JSON.stringify(query);

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });
    void services.list(JSON.parse(key) as JobsQuery).then((outcome) => {
      if (!cancelled) {
        setState(outcome.ok ? { status: "ready", list: outcome.list } : { status: "error" });
        if (outcome.ok) {
          setCounts(outcome.list.counts);
        }
      }
    });
    return () => {
      cancelled = true;
    };
  }, [services, key, attempt]);

  const reload = useCallback(() => setAttempt((current) => current + 1), []);
  const drop = useCallback(
    (id: number) => {
      setState((current) =>
        current.status === "ready" ? { status: "ready", list: { ...current.list, items: current.list.items.filter((item) => item.id !== id) } } : current,
      );
      // Вакансія змінила етап: лічильники беремо з сервера, а не рахуємо з рядків.
      void services.list({ ...(JSON.parse(key) as JobsQuery), limit: 1 }).then((outcome) => {
        if (outcome.ok) {
          setCounts(outcome.list.counts);
        }
      });
    },
    [services, key],
  );
  return { state, counts, reload, drop };
}
