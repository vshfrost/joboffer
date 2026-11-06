import { useCallback, useEffect, useState } from "react";

import { FACT_KINDS, type Fact, type OriginalCv } from "../../domain/facts";
import { useFactsServices } from "./FactsServices";

export type LibraryState = { status: "loading" } | { status: "error" } | { status: "ready"; facts: Fact[] };

export type CvState = { status: "loading" } | { status: "error" } | { status: "ready"; cv: OriginalCv | null };

export interface FactLibrary {
  state: LibraryState;
  cv: CvState;
  /** Нове завантаження зі скелетоном (повтор після помилки). */
  reload(): void;
  /** Тихо оновлює факти з сервера, не чіпаючи екран (після 404). */
  refresh(): void;
  /** Підміняє факти (за id) відповіддю сервера: порядок категорій задає сервер, тож нові місця рахує `order`. */
  replace(facts: readonly Fact[]): void;
  /** Додає новий факт на його місце: за порядком категорій, усередині — за номером. */
  add(fact: Fact): void;
  /** Прибирає факт зі списку на місці — без нового запиту. */
  drop(id: number): void;
}

/** Факти й оригінал CV вантажаться паралельно й незалежно: збій CV не ховає факти. */
export function useFactLibrary(): FactLibrary {
  const services = useFactsServices();
  const [state, setState] = useState<LibraryState>({ status: "loading" });
  const [cv, setCv] = useState<CvState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });
    setCv({ status: "loading" });
    void services.load().then((outcome) => {
      if (!cancelled) {
        setState(outcome.ok ? { status: "ready", facts: outcome.facts } : { status: "error" });
      }
    });
    void services.originalCv().then((outcome) => {
      if (!cancelled) {
        setCv(outcome.ok ? { status: "ready", cv: outcome.cv } : { status: "error" });
      }
    });
    return () => {
      cancelled = true;
    };
  }, [services, attempt]);

  const reload = useCallback(() => setAttempt((current) => current + 1), []);

  const refresh = useCallback(() => {
    void services.load().then((outcome) => {
      if (outcome.ok) {
        setState({ status: "ready", facts: outcome.facts });
      }
    });
  }, [services]);

  const replace = useCallback(
    (changed: readonly Fact[]) =>
      setState((current) => {
        if (current.status !== "ready") {
          return current;
        }
        const byId = new Map(changed.map((fact) => [fact.id, fact]));
        return { status: "ready", facts: current.facts.map((fact) => byId.get(fact.id) ?? fact) };
      }),
    [],
  );

  const add = useCallback(
    (added: Fact) =>
      setState((current) => {
        if (current.status !== "ready") {
          return current;
        }
        const rank = (fact: Fact) => FACT_KINDS.indexOf(fact.kind);
        const facts = [...current.facts, added].sort((a, b) => rank(a) - rank(b) || a.id - b.id);
        return { status: "ready", facts };
      }),
    [],
  );

  const drop = useCallback(
    (id: number) =>
      setState((current) => (current.status === "ready" ? { status: "ready", facts: current.facts.filter((fact) => fact.id !== id) } : current)),
    [],
  );

  return { state, cv, reload, refresh, replace, add, drop };
}
