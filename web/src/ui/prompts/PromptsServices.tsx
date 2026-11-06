import { createContext, use, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import type { PromptsServices } from "../../application/prompts";
import { fillPrompt, type PromptRequest, type Prompts } from "../../domain/prompts";

/** Стан текстів запитів: `unavailable` — запит не вдався, кнопки показують помилку й нічого не копіюють. */
export type PromptsState = { status: "loading" } | { status: "ready"; prompts: Prompts } | { status: "unavailable" };

/** Текст одного запиту з підставленими номерами. */
export type PromptText = { status: "loading" } | { status: "ready"; text: string } | { status: "unavailable" };

interface PromptsContextValue {
  state: PromptsState;
  /** Споживач з'явився на екрані; повертає відписку. Перший споживач вантажить тексти, якщо їх ще нема. */
  acquire(): () => void;
  /** Перечитує тексти за вимогою: після помилки наступний клік пробує знову. */
  refresh(): Promise<void>;
}

const PromptsContext = createContext<PromptsContextValue | null>(null);

/**
 * Одні тексти запитів на всі кнопки: вантажаться, коли на екрані з'являється перша кнопка, а не при старті
 * (до входу їх не віддадуть). Вдале завантаження не повторюється: тексти не міняються, поки працює клієнт.
 */
export function PromptsServicesProvider({ services, children }: { services: PromptsServices; children: ReactNode }) {
  const [state, setState] = useState<PromptsState>({ status: "loading" });
  const loaded = useRef(false);
  const consumers = useRef(0);

  const refresh = useCallback(
    () =>
      services.load().then((outcome) => {
        loaded.current = outcome.ok;
        setState(outcome.ok ? { status: "ready", prompts: outcome.prompts } : { status: "unavailable" });
      }),
    [services],
  );

  const acquire = useCallback(() => {
    consumers.current += 1;
    if (consumers.current === 1 && !loaded.current) {
      void refresh();
    }
    return () => {
      consumers.current -= 1;
    };
  }, [refresh]);

  const value = useMemo(() => ({ state, acquire, refresh }), [state, acquire, refresh]);
  return <PromptsContext value={value}>{children}</PromptsContext>;
}

function usePromptsContext(hook: string): PromptsContextValue {
  const context = use(PromptsContext);
  if (context === null) {
    throw new Error(`${hook} потребує PromptsServicesProvider`);
  }
  return context;
}

/** Текст запиту з підставленими номерами; з'являючись на екрані, запускає завантаження текстів. */
export function usePromptText(request: PromptRequest): PromptText {
  const { state, acquire } = usePromptsContext("usePromptText");
  useEffect(() => acquire(), [acquire]);
  return state.status === "ready" ? { status: "ready", text: fillPrompt(state.prompts[request.key], request.values) } : state;
}

/** Перечитує тексти за вимогою: клік після помилки пробує знову. */
export function useRefreshPrompts(): () => Promise<void> {
  return usePromptsContext("useRefreshPrompts").refresh;
}
