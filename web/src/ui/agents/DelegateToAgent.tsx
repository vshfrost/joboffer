import { ChevronRight, Copy, Lock, Sparkles } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import { launchOf, requestMessage, type Agent } from "../../domain/agents";
import { promptParts } from "../../domain/onboarding";
import { PROMPT_UNAVAILABLE, type PromptRequest } from "../../domain/prompts";
import { Button } from "../components/button";
import { cn } from "../lib/cn";
import { usePromptText, useRefreshPrompts } from "../prompts/PromptsServices";
import { AgentLogo, AGENT_TONE } from "./AgentLogo";
import { useAgents } from "./AgentsServices";
import { launchAgent } from "./launch";

const MANUAL = "Не вдалося скопіювати автоматично. Виділи текст промпту й скопіюй вручну.";
const LOADING = "Завантажуємо промпт…";
const COPIED = "Промпт скопійовано. Встав його у свій агент.";

interface DelegateToAgentProps {
  /** Який промпт узяти в сервера: копіюється й передається агенту цілим, навіть коли показ згорнуто. */
  request: PromptRequest;
  /** Що саме агент зробить: підпис під заголовком. */
  description: string;
}

/**
 * «Делегувати агенту»: кнопки підключених агентів відкривають нову розмову з промптом у посиланні й не чіпають буфер, лише «Копіювати промпт» копіює.
 * Сам промпт — текст для читання й виділення за випадашкою, закритою за замовчуванням.
 */
export function DelegateToAgent({ request, description }: DelegateToAgentProps) {
  const agents = useAgents();
  const promptText = usePromptText(request);
  const refreshPrompts = useRefreshPrompts();
  const panel = useId();
  const text = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [message, setMessage] = useState<{ text: string; kind: "ok" | "manual" | "error" }>({ text: "", kind: "ok" });
  const parts = promptText.status === "ready" ? promptParts(promptText.text) : null;
  const loadingText = promptText.status === "loading";

  const launchable = agents.status === "ready" ? agents.agents.filter((agent) => agent.kind !== "other") : [];
  const undetermined = agents.status === "unavailable" || (agents.status === "ready" && launchable.length === 0);

  // Копіювання не вдалося: промпт видно й виділено, щоб скопіювати вручну.
  useEffect(() => {
    if (message.kind === "manual") {
      // Промпт змонтовано: setOpen(true) і повідомлення йдуть в одному оновленні.
      window.getSelection()?.selectAllChildren(text.current as HTMLDivElement);
    }
  }, [message]);

  /** Тексту нема: нічого не копіюємо й не відкриваємо; наступний клік пробує завантажити знову. */
  function unavailable() {
    setMessage({ text: PROMPT_UNAVAILABLE, kind: "error" });
    void refreshPrompts();
  }

  /** Кнопка агента: лише відкриває нову розмову; запит завеликий для посилання — не відкриваємо, відсилаємо до копіювання. */
  function openAgent(agent: Agent) {
    if (promptText.status !== "ready") {
      unavailable();
      return;
    }
    const launch = launchOf(agent, promptText.text);
    setMessage({ text: requestMessage(agent, launch !== null), kind: launch === null ? "error" : "ok" });
    if (launch !== null) {
      launchAgent(launch);
    }
  }

  /** «Копіювати промпт»: єдине місце, де промпт потрапляє в буфер. */
  async function copy() {
    if (promptText.status !== "ready") {
      unavailable();
      return;
    }
    try {
      await navigator.clipboard.writeText(promptText.text);
      setMessage({ text: COPIED, kind: "ok" });
    } catch {
      setOpen(true);
      setMessage({ text: MANUAL, kind: "manual" });
    }
  }

  return (
    <section aria-label="Делегувати агенту" className="min-w-0 rounded-xl border border-border bg-card p-4">
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-3">
        <div className="min-w-40 flex-1">
          <h3 className="flex items-center gap-2 text-section font-semibold text-primary">
            <Sparkles aria-hidden="true" className="size-4 shrink-0" />
            Делегувати агенту
          </h3>
          <p className="text-caption text-muted-foreground">{description}</p>
        </div>
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          {undetermined ? <span className="text-caption text-muted-foreground">Агент не визначений</span> : null}
          {launchable.map((agent) => (
            <button
              key={agent.id}
              type="button"
              aria-label={`Відкрити ${agent.name}`}
              title={`Відкрити ${agent.name}`}
              onClick={() => {
                openAgent(agent);
              }}
              disabled={loadingText}
              className={cn(
                "inline-flex size-10 shrink-0 cursor-pointer items-center justify-center rounded-lg border pointer-coarse:size-11",
                AGENT_TONE[agent.kind],
              )}
            >
              <AgentLogo kind={agent.kind} />
            </button>
          ))}
          <Button type="button" variant="secondary" size="sm" disabled={loadingText} onClick={() => void copy()} className="cursor-pointer">
            <Copy aria-hidden="true" />
            Копіювати промпт
          </Button>
        </div>
      </div>
      <p role="status" className={cn("mt-2 text-caption font-medium empty:hidden", message.kind === "ok" ? "text-status-success-foreground" : "text-status-warning-foreground")}>
        {message.text}
      </p>
      <div className="mt-3 border-t border-border pt-1">
        <div className="flex items-center justify-between gap-2">
          <button
            type="button"
            aria-expanded={open}
            aria-controls={open ? panel : undefined}
            onClick={() => setOpen((current) => !current)}
            className="inline-flex min-h-10 cursor-pointer items-center gap-1 rounded-sm text-left text-caption font-medium text-primary pointer-coarse:min-h-11"
          >
            <ChevronRight aria-hidden="true" className={cn("size-4 shrink-0 transition-transform duration-140", open && "rotate-90")} />
            Переглянути промпт
          </button>
          <span className="inline-flex shrink-0 items-center gap-1 text-caption text-muted-foreground">
            <Lock aria-hidden="true" className="size-3.5" />
            Лише для читання
          </span>
        </div>
        {open ? (
          <div
            id={panel}
            ref={text}
            role="region"
            aria-label="Промпт"
            className="mt-1 min-w-0 rounded-lg border border-border bg-background p-4 text-caption select-text [overflow-wrap:anywhere]"
          >
            {parts === null ? (
              <p>{loadingText ? LOADING : PROMPT_UNAVAILABLE}</p>
            ) : (
              <>
                <p>{parts.intro}</p>
                {parts.rules.length === 0 ? null : (
                  <>
                    <h4 className="mt-3 font-semibold">Rules</h4>
                    <ul className="mt-1 flex list-disc flex-col gap-1 pl-5">
                      {parts.rules.map((rule) => (
                        <li key={rule}>{rule}</li>
                      ))}
                    </ul>
                  </>
                )}
                {parts.steps.map((step) => (
                  <div key={step.title} className="mt-3">
                    <h4 className="font-semibold">{step.title}</h4>
                    <p>{step.body}</p>
                  </div>
                ))}
              </>
            )}
          </div>
        ) : null}
      </div>
    </section>
  );
}
