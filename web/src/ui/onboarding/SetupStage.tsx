import { ArrowRight, Check, SlidersHorizontal, Sparkles } from "lucide-react";
import { Link } from "react-router";

import type { AgentKind } from "../../domain/agents";
import { MANUAL_STEPS, namedAgent, STEP_INFO, type Onboarding } from "../../domain/onboarding";
import { REQUESTS } from "../../domain/prompts";
import { DelegateToAgent } from "../agents/DelegateToAgent";
import { useAgents } from "../agents/AgentsServices";
import { Button } from "../components/button";
import { cn } from "../lib/cn";

/** Як користувач завершує налаштування; вибір живе лише в клієнті, на сервер не йде. */
export type SetupMode = "agent" | "manual" | null;

interface SetupStageProps {
  onboarding: Onboarding;
  /** Агент, обраний на першому етапі: його називаємо, якщо він серед підключених. */
  selected: AgentKind;
  mode: SetupMode;
  onMode(mode: Exclude<SetupMode, null>): void;
}

/** Етап 2: агента підключено — завершити з агентом («Делегувати агенту») або вручну (стан кроків із сервера). */
export function SetupStage({ onboarding, selected, mode, onMode }: SetupStageProps) {
  const agents = useAgents();
  const named = agents.status === "ready" ? namedAgent(agents.agents, selected) : null;
  const lead =
    agents.status === "loading" ? "" : named === null ? "MCP працює. Назву агента не визначено. " : `Ваш ${named.name} готовий допомогти. `;

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <div className="flex items-start gap-3">
        <span aria-hidden="true" className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-selected text-primary">
          <Check className="size-5" />
        </span>
        <div className="min-w-0">
          <h3 className="text-section font-semibold">Агента підключено</h3>
          <p className="text-caption text-muted-foreground">{`${lead}Як продовжимо?`}</p>
        </div>
      </div>
      {mode === null ? (
        <div className="grid min-w-0 gap-2 sm:grid-cols-[1.2fr_1fr]">
          <button
            type="button"
            onClick={() => onMode("agent")}
            className="flex min-w-0 cursor-pointer items-start gap-3 rounded-xl border border-primary bg-selected p-4 text-left"
          >
            <Sparkles aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-primary" />
            <span className="min-w-0 flex-1">
              <strong className="block text-caption font-medium">Завершити з агентом</strong>
              <span className="block text-caption text-muted-foreground">Короткий діалог замість форм</span>
            </span>
            <ArrowRight aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-primary" />
          </button>
          <button
            type="button"
            onClick={() => onMode("manual")}
            className="flex min-w-0 cursor-pointer items-start gap-3 rounded-xl border border-border bg-card p-4 text-left"
          >
            <SlidersHorizontal aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
            <span className="min-w-0 flex-1">
              <strong className="block text-caption font-medium">Налаштувати вручну</strong>
              <span className="block text-caption text-muted-foreground">Заповнити у своєму темпі</span>
            </span>
          </button>
        </div>
      ) : mode === "agent" ? (
        <>
          <DelegateToAgent request={REQUESTS.setup} description="Завершити налаштування профілю" />
          <Button type="button" variant="ghost" size="sm" className="self-start text-muted-foreground" onClick={() => onMode("manual")}>
            Налаштувати вручну
          </Button>
        </>
      ) : (
        <>
          <ul aria-label="Налаштування профілю" className="divide-y divide-border">
            {MANUAL_STEPS.map((key) => {
              const info = STEP_INFO[key];
              const done = onboarding.steps.some((step) => step.key === key && step.done);
              return (
                <li key={key} className="flex min-w-0 items-center gap-3 py-3 text-nav">
                  {/* info.to у ручних кроків завжди є: це сторінки застосунку */}
                  <Link to={info.to as string} className={cn("min-w-0 flex-1 font-medium hover:text-primary", done && "text-muted-foreground")}>
                    {info.title}
                  </Link>
                  <span className={cn("shrink-0 text-caption", done ? "text-status-success-foreground" : "text-muted-foreground")}>{done ? "Готово" : "Заповнити"}</span>
                </li>
              );
            })}
          </ul>
          <div className="rounded-lg bg-background px-4 py-3 text-caption text-muted-foreground">
            Додаткові можливості
            <span className="mt-1 block">Фото для CV · Підключення пошти · Можна пізніше</span>
          </div>
          <Button type="button" variant="ghost" size="sm" className="self-start text-muted-foreground" onClick={() => onMode("agent")}>
            <Sparkles aria-hidden="true" />
            Продовжити з агентом
          </Button>
        </>
      )}
    </div>
  );
}
