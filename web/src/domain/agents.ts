/** Підключені агенти користувача (`/api/agents`): кнопки запитів відкривають агента з готовим запитом. */

export const AGENT_KINDS = ["claude", "claude_code", "chatgpt", "codex", "other"] as const;
export type AgentKind = (typeof AGENT_KINDS)[number];

export interface Agent {
  id: string;
  kind: AgentKind;
  name: string;
}

/** Як відкрити агента: `navigate` — рідне посилання застосунку (claude://, codex://), `open` — нова вкладка. */
export interface Launch {
  how: "navigate" | "open";
  url: string;
}

/** Довжина запиту, понад яку сам застосунок його обрізає: тоді посилання не даємо, запит копіюють кнопкою «Копіювати промпт». */
const PROMPT_LIMITS: Partial<Record<AgentKind, number>> = { claude: 14000, claude_code: 5000 };

/** Посилання, що відкриває НОВУ розмову агента із запитом; `null` — агент без посилання чи запит завеликий. */
export function launchOf(agent: Agent, prompt: string): Launch | null {
  const limit = PROMPT_LIMITS[agent.kind];
  if (limit !== undefined && prompt.length > limit) {
    return null;
  }
  const encoded = encodeURIComponent(prompt);
  switch (agent.kind) {
    case "claude":
      return { how: "navigate", url: `claude://claude.ai/new?q=${encoded}` };
    case "claude_code":
      return { how: "navigate", url: `claude://code/new?q=${encoded}` };
    case "codex":
      return { how: "navigate", url: `codex://threads/new?prompt=${encoded}` };
    case "chatgpt":
      return { how: "open", url: `https://chatgpt.com/?q=${encoded}` };
    case "other":
      return null;
  }
}

/** Повідомлення після кліку на агента: відкриваємо його або (запит завеликий для посилання) відсилаємо до «Копіювати промпт». */
export function requestMessage(agent: Agent, launched: boolean): string {
  return launched ? `Відкриваємо ${agent.name}…` : "Промпт задовгий для передачі напряму — скопіюй його кнопкою «Копіювати промпт».";
}
