import { Bot } from "lucide-react";
import type { CSSProperties } from "react";

import type { AgentKind } from "../../domain/agents";
import { AGENT_LOGO_FILES } from "../../domain/onboarding";

/** Колір, поверхня й рамка кнопки агента: токени `--jo-agent-*` (claude і claude_code ділять терактоту). */
export const AGENT_TONE: Record<AgentKind, string> = {
  claude: "border-agent-claude-border bg-agent-claude-surface text-agent-claude",
  claude_code: "border-agent-claude-border bg-agent-claude-surface text-agent-claude",
  chatgpt: "border-agent-chatgpt-border bg-agent-chatgpt-surface text-agent-chatgpt",
  codex: "border-agent-codex-border bg-agent-codex-surface text-agent-codex",
  other: "border-agent-other-border bg-agent-other-surface text-agent-other",
};

/** Логотип агента з `public/agents` (без CDN) як маска в кольорі тексту; «Інший агент» — іконка Lucide. */
export function AgentLogo({ kind }: { kind: AgentKind }) {
  const logo = AGENT_LOGO_FILES[kind];
  if (logo === null) {
    return <Bot aria-hidden="true" className="size-5 shrink-0" />;
  }
  const style = { "--agent-logo": `url(${import.meta.env.BASE_URL}agents/${logo})` } as CSSProperties;
  return <span aria-hidden="true" data-agent-logo="" className="agent-logo" style={style} />;
}
