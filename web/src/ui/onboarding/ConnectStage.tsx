import { PlugZap } from "lucide-react";
import { useState } from "react";

import type { AgentKind } from "../../domain/agents";
import { agentGuides, AGENT_CHOICES, AGENT_LABELS, guideLabel } from "../../domain/onboarding";
import { AgentLogo, AGENT_TONE } from "../agents/AgentLogo";
import { Button } from "../components/button";
import { Disclosure } from "../documents/Disclosure";
import { cn } from "../lib/cn";
import { ConnectorAddress } from "./ConnectorAddress";

/** Результат перевірки підключення, який показуємо під кнопкою. */
export type CheckResult = "connected" | "missing" | "failed";

const CHECK_MESSAGES: Record<Exclude<CheckResult, "connected">, string> = {
  missing: "Підключення ще не знайдено. Додай адресу в агенті й перевір ще раз.",
  failed: "Не вдалося перевірити підключення. Спробуй ще раз.",
};

interface ConnectStageProps {
  selected: AgentKind;
  onSelect(kind: AgentKind): void;
  /** Перечитує онбординг і агентів; повертає, що знайшлося. */
  onCheck(): Promise<CheckResult>;
}

/** Етап 1: обрати агента, відкрити інструкцію саме для нього (згорнуту), скопіювати адресу MCP, перевірити підключення. */
export function ConnectStage({ selected, onSelect, onCheck }: ConnectStageProps) {
  // Адреса MCP-конектора — `/mcp` на цьому origin, незалежно від базового шляху роутера; збігається з `agent_public_url` бекенду.
  const address = `${window.location.origin}/mcp`;
  const [checking, setChecking] = useState(false);
  const [failure, setFailure] = useState<Exclude<CheckResult, "connected"> | null>(null);
  const guide = agentGuides(address)[selected];

  async function check() {
    setChecking(true);
    const result = await onCheck();
    setChecking(false);
    setFailure(result === "connected" ? null : result);
  }

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <div className="flex items-start gap-3">
        <span aria-hidden="true" className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-selected text-primary">
          <PlugZap className="size-5" />
        </span>
        <div className="min-w-0">
          <h3 className="text-section font-semibold">Підключити агента</h3>
          <p className="text-caption text-muted-foreground">Оберіть свого помічника. Він зможе працювати з вашим профілем у joboffer.</p>
        </div>
      </div>
      <div className="flex min-w-0 flex-col gap-2">
        <p className="text-caption text-muted-foreground">Ваш агент</p>
        <div className="flex min-w-0 flex-wrap gap-2">
          {AGENT_CHOICES.map((kind) => (
            <button
              key={kind}
              type="button"
              aria-pressed={kind === selected}
              onClick={() => onSelect(kind)}
              className={cn(
                "inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-xl border px-3 text-caption font-medium whitespace-nowrap",
                AGENT_TONE[kind],
                kind === selected && "ring-2 ring-current",
              )}
            >
              <AgentLogo kind={kind} />
              {AGENT_LABELS[kind]}
            </button>
          ))}
        </div>
      </div>
      <div className="rounded-lg border border-border bg-background px-3">
        <Disclosure key={selected} label={guideLabel(selected)}>
          <div className="flex min-w-0 flex-col gap-2 pb-3">
            <div className="flex flex-wrap items-center justify-between gap-2 text-caption font-medium">
              <span>{guide.agent}</span>
              {guide.link === null ? null : (
                <a href={guide.link} target="_blank" rel="noopener noreferrer" className="font-normal text-primary underline">
                  Довідка ↗
                </a>
              )}
            </div>
            <ol className="flex min-w-0 list-decimal flex-col gap-2 pl-5 text-caption">
              {guide.steps.map((step) => (
                <li key={step.text} className="min-w-0">
                  {step.text}
                  {step.command === undefined ? null : (
                    <code className="mt-1 block min-w-0 rounded-md border border-border bg-card px-2 py-1 [overflow-wrap:anywhere]">{step.command}</code>
                  )}
                </li>
              ))}
            </ol>
            <p className="text-caption text-muted-foreground">Кроки можуть відрізнятись</p>
          </div>
        </Disclosure>
      </div>
      <ConnectorAddress address={address} />
      <div className="flex min-w-0 flex-col items-start gap-2">
        <Button type="button" disabled={checking} onClick={() => void check()}>
          <PlugZap aria-hidden="true" />
          Перевірити підключення
        </Button>
        <p role="status" className="text-caption text-muted-foreground empty:hidden">
          {failure === null ? "" : CHECK_MESSAGES[failure]}
        </p>
      </div>
    </div>
  );
}
