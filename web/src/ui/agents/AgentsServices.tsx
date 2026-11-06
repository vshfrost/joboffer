import { createContext, use, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import type { AgentsServices } from "../../application/agents";
import type { Agent } from "../../domain/agents";

/** Стан списку агентів: `unavailable` — запит не вдався (кнопки працюють як раніше, лише копіюють). */
export type AgentsState = { status: "loading" } | { status: "ready"; agents: Agent[] } | { status: "unavailable" };

interface AgentsContextValue {
  state: AgentsState;
  /** Споживач з'явився на екрані; повертає відписку. Перший споживач сторінки оновлює список. */
  acquire(): () => void;
  /** Перечитує список за вимогою (наприклад, «Перевірити підключення»). */
  refresh(): Promise<void>;
}

const AgentsContext = createContext<AgentsContextValue | null>(null);

/**
 * Один список агентів на всі кнопки сторінки. Вантажиться, коли на екрані з'являється перша кнопка, а не при старті
 * застосунку, і оновлюється щоразу, як сторінка з кнопками відкривається знову: щойно підключений агент одразу видно.
 */
export function AgentsServicesProvider({ services, children }: { services: AgentsServices; children: ReactNode }) {
  const [state, setState] = useState<AgentsState>({ status: "loading" });
  const consumers = useRef(0);

  const refresh = useCallback(
    () => services.load().then((outcome) => setState(outcome.ok ? { status: "ready", agents: outcome.agents } : { status: "unavailable" })),
    [services],
  );

  const acquire = useCallback(() => {
    consumers.current += 1;
    if (consumers.current === 1) {
      void refresh();
    }
    return () => {
      consumers.current -= 1;
    };
  }, [refresh]);

  const value = useMemo(() => ({ state, acquire, refresh }), [state, acquire, refresh]);
  return <AgentsContext value={value}>{children}</AgentsContext>;
}

function useAgentsContext(): AgentsContextValue {
  const context = use(AgentsContext);
  if (context === null) {
    throw new Error("useAgents потребує AgentsServicesProvider");
  }
  return context;
}

export function useAgents(): AgentsState {
  const { state, acquire } = useAgentsContext();
  useEffect(() => acquire(), [acquire]);
  return state;
}

/** Перечитує список агентів за вимогою: після «Перевірити підключення» щойно підключений агент одразу видно. */
export function useRefreshAgents(): () => Promise<void> {
  return useAgentsContext().refresh;
}
