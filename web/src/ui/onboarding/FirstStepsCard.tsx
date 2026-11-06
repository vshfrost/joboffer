import { useEffect, useId, useState } from "react";

import type { AgentKind } from "../../domain/agents";
import { progressOf, ROUTE_STAGES, stageOf, type Onboarding } from "../../domain/onboarding";
import { useRefreshAgents } from "../agents/AgentsServices";
import { cn } from "../lib/cn";
import { ConnectStage, type CheckResult } from "./ConnectStage";
import { useOnboardingServices } from "./OnboardingServices";
import { SetupStage, type SetupMode } from "./SetupStage";

/**
 * Картка «Перші кроки» в огляді профілю: маршрут з трьох етапів. Етап береться з сервера (агента підключено — другий);
 * третій — лише підпис: щойно обов'язкові кроки готові, картка зникає.
 */
export function FirstStepsCard() {
  const services = useOnboardingServices();
  const refreshAgents = useRefreshAgents();
  const headingId = useId();
  const [onboarding, setOnboarding] = useState<Onboarding | null>(null);
  const [selected, setSelected] = useState<AgentKind>("claude");
  const [mode, setMode] = useState<SetupMode>(null);

  useEffect(() => {
    void services.load().then((outcome) => {
      if (outcome.ok) {
        setOnboarding(outcome.onboarding);
      }
    });
  }, [services]);

  if (onboarding === null || onboarding.complete) {
    return null;
  }

  const stage = stageOf(onboarding);
  const progress = progressOf(onboarding);
  const counter = stage === 0 ? "Крок 1 із 3" : mode === "manual" ? `${progress.done} із ${progress.total} виконано` : "Крок 2 із 3";

  async function check(): Promise<CheckResult> {
    const [outcome] = await Promise.all([services.load(), refreshAgents()]);
    if (!outcome.ok) {
      return "failed";
    }
    setOnboarding(outcome.onboarding);
    return stageOf(outcome.onboarding) === 1 ? "connected" : "missing";
  }

  return (
    <section aria-labelledby={headingId} className="mb-6 min-w-0 overflow-hidden rounded-xl border border-border bg-card">
      <div className="flex min-w-0 items-start justify-between gap-3 p-5 pb-4">
        <div className="min-w-0">
          <p className="text-[0.625rem] tracking-[0.15em] text-muted-foreground">ВАШ СТАРТ У JOBOFFER</p>
          <h2 id={headingId} className="text-section font-semibold">
            Перші кроки
          </h2>
        </div>
        <span className="shrink-0 rounded-full bg-selected px-3 py-1 text-caption text-primary">{counter}</span>
      </div>
      <ol aria-label="Маршрут" className="flex gap-2 px-5 pb-5">
        {ROUTE_STAGES.map((title, index) => (
          <li
            key={title}
            aria-current={index === stage ? "step" : undefined}
            className={cn("min-w-0 flex-1 text-[0.6875rem] text-muted-foreground", index <= stage && "text-primary")}
          >
            <div aria-hidden="true" className={cn("mb-2 h-[3px] rounded-full bg-selected", index <= stage && "bg-primary")} />
            <span aria-hidden="true">{index < stage ? "✓" : index + 1}&nbsp; </span>
            {title}
          </li>
        ))}
      </ol>
      <div className="min-w-0 px-5 pb-5">
        {stage === 0 ? (
          <ConnectStage selected={selected} onSelect={setSelected} onCheck={check} />
        ) : (
          <SetupStage onboarding={onboarding} selected={selected} mode={mode} onMode={setMode} />
        )}
      </div>
    </section>
  );
}
