/** Перші кроки: дані онбордингу з API (`/api/onboarding`). Кроки рахує сервер за реальними даними користувача. */
import { AGENT_KINDS, type Agent, type AgentKind } from "./agents";

/** Кроки, які знає клієнт, у порядку показу. */
export const STEP_KEYS = ["goal", "locations", "contacts", "claude", "original_cv", "photo", "mail"] as const;
export type StepKey = (typeof STEP_KEYS)[number];

export interface OnboardingStep {
  key: StepKey;
  done: boolean;
  /** Необов'язковий крок не заважає завершенню. */
  optional: boolean;
}

/** @deprecated Підказки не показуємо; поле лишається, бо сервер ще віддає їх у відповіді. */
export interface OnboardingTip {
  key: StepKey;
  seen: boolean;
  /** Користувач сховав підказку; стан на сервері, а не в браузері. */
  dismissed: boolean;
}

export interface Onboarding {
  steps: OnboardingStep[];
  tips: OnboardingTip[];
  /** Усі обов'язкові кроки зроблено. */
  complete: boolean;
}

export interface StepInfo {
  title: string;
  /** Куди вести; `null` — крок виконується не в застосунку. */
  to: string | null;
}

export const STEP_INFO: Record<StepKey, StepInfo> = {
  goal: {
    title: "Задати ціль пошуку",
    to: "/profile/target",
  },
  locations: {
    title: "Додати локації",
    to: "/profile/locations",
  },
  contacts: {
    title: "Заповнити контакти для CV",
    to: "/profile/contacts",
  },
  claude: {
    title: "Підключити агента",
    to: null,
  },
  original_cv: {
    title: "Додати оригінальне CV",
    to: "/facts",
  },
  photo: {
    title: "Додати фото для CV",
    to: "/profile/photos",
  },
  mail: {
    title: "Підключити пошту",
    to: "/profile/mail",
  },
};

/** Крок інструкції підключення: пояснення й, за потреби, команда для терміналу. */
export interface GuideStep {
  text: string;
  command?: string;
}

export interface AgentGuide {
  /** Заголовок інструкції: повна назва застосунку агента. */
  agent: string;
  steps: GuideStep[];
  /** Офіційна довідка агента; `null` — немає. */
  link: string | null;
}

/** Назви агентів, як на кнопках вибору. */
export const AGENT_LABELS: Record<AgentKind, string> = {
  claude: "Claude",
  claude_code: "Claude Code",
  chatgpt: "ChatGPT",
  codex: "Codex",
  other: "Інший агент",
};

/** Агенти для вибору в порядку показу. */
export const AGENT_CHOICES: readonly AgentKind[] = AGENT_KINDS;

/** Файл логотипа в `public/agents`; `null` — своєї марки нема, показуємо іконку Lucide. */
export const AGENT_LOGO_FILES: Record<AgentKind, string | null> = {
  claude: "claude.svg",
  claude_code: "claudecode.svg",
  chatgpt: "openai.svg",
  codex: "codex.svg",
  other: null,
};

/** Інструкції для кожного агента; команди містять реальну адресу конектора. */
export function agentGuides(address: string): Record<AgentKind, AgentGuide> {
  return {
    claude: {
      agent: "Claude (веб і десктоп)",
      steps: [
        { text: "Відкрий Налаштування → Конектори." },
        { text: "Натисни «Додати власний конектор» і встав адресу." },
        { text: "Натисни «Підключити» й увійди в joboffer." },
      ],
      link: "https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp",
    },
    claude_code: {
      agent: "Claude Code",
      steps: [
        { text: "Додай конектор командою в терміналі:", command: `claude mcp add --transport http joboffer ${address}` },
        { text: "У Claude Code виконай /mcp, обери joboffer і натисни Authenticate, потім увійди в joboffer." },
      ],
      link: "https://code.claude.com/docs/en/mcp",
    },
    chatgpt: {
      agent: "ChatGPT (веб)",
      steps: [
        { text: "Відкрий Налаштування → Apps → Розширені налаштування й увімкни режим розробника." },
        { text: "Натисни «Створити», встав адресу, автентифікація — OAuth." },
        { text: "Увійди в joboffer." },
      ],
      link: "https://help.openai.com/en/articles/12584461-developer-mode-and-full-mcp-connectors-in-chatgpt",
    },
    codex: {
      agent: "Codex (CLI)",
      steps: [
        { text: "Додай конектор командою:", command: `codex mcp add joboffer --url ${address}` },
        { text: "Увійди командою:", command: "codex mcp login joboffer" },
      ],
      link: "https://developers.openai.com/codex/mcp/",
    },
    other: {
      agent: "Інший агент",
      steps: [
        { text: "Додай віддалений MCP-сервер (Streamable HTTP) з цією адресою." },
        { text: "Коли відкриється браузер — увійди в joboffer. Так працює в Cursor, Gemini CLI та інших." },
      ],
      link: null,
    },
  };
}

/** Підпис кнопки інструкції: «Як підключити Claude», для невідомого агента — «Як підключити свого агента». */
export function guideLabel(kind: AgentKind): string {
  return kind === "other" ? "Як підключити свого агента" : `Як підключити ${AGENT_LABELS[kind]}`;
}

/** Етапи маршруту «Перших кроків»; третій — лише підпис: коли обов'язкові кроки готові, картки вже нема. */
export const ROUTE_STAGES = ["Підключити агента", "Налаштувати профіль", "Готово до пошуку"] as const;

/** Кроки сервера, які показує ручне налаштування; фото й пошта — «додаткові можливості» без пунктів. */
export const MANUAL_STEPS = ["goal", "locations", "contacts", "original_cv"] as const satisfies readonly StepKey[];

/** Поточний етап маршруту: перший, доки сервер не бачить підключеного агента, далі другий. */
export function stageOf(onboarding: Onboarding): 0 | 1 {
  return onboarding.steps.some((step) => step.key === "claude" && step.done) ? 1 : 0;
}

/** Агент, якого називаємо після підключення: обраний на першому етапі, інакше перший у списку; `null` — назви нема. */
export function namedAgent(agents: readonly Agent[], selected: AgentKind): Agent | null {
  const found = agents.find((agent) => agent.kind === selected) ?? agents[0];
  return found === undefined || found.kind === "other" ? null : found;
}

/** Крок промпта: заголовок («Step 1 — CV (required)», «Finish») і решта його абзацу. */
export interface PromptStep {
  title: string;
  body: string;
}

export interface PromptParts {
  intro: string;
  /** Пункти розділу «Rules» без маркерів. */
  rules: string[];
  steps: PromptStep[];
}

const RULES_HEADING = "Rules\n";
const RULE_MARKER = "- ";

/** Розкладає промпт на вступ, правила й блоки кроків для читабельного показу; копіюється завжди сам текст. */
export function promptParts(prompt: string): PromptParts {
  const [intro = "", ...blocks] = prompt
    .split("\n\n")
    .map((block) => block.trim())
    .filter((block) => block !== "");
  const rules = blocks.find((block) => block.startsWith(RULES_HEADING));
  return {
    intro,
    rules: rules === undefined ? [] : rules.split("\n").filter((line) => line.startsWith(RULE_MARKER)).map((line) => line.slice(RULE_MARKER.length)),
    steps: blocks.filter((block) => block !== rules).map(stepOf),
  };
}

/** Заголовок — до першої крапки з пробілом; абзац без речення — самий заголовок. */
function stepOf(block: string): PromptStep {
  const end = block.indexOf(". ");
  return end === -1 ? { title: block, body: "" } : { title: block.slice(0, end), body: block.slice(end + 2) };
}

export interface Progress {
  done: number;
  total: number;
}

/** Прогрес — за обов'язковими кроками: необов'язкові ні рахуються, ні гальмують завершення. */
export function progressOf(onboarding: Onboarding): Progress {
  const required = onboarding.steps.filter((step) => !step.optional);
  return { done: required.filter((step) => step.done).length, total: required.length };
}
