import { describe, expect, test } from "vitest";

import { launchOf, requestMessage, type Agent } from "./agents";

const CLAUDE: Agent = { id: "a1", kind: "claude", name: "Claude" };
const CLAUDE_CODE: Agent = { id: "a2", kind: "claude_code", name: "Claude Code" };
const CODEX: Agent = { id: "a3", kind: "codex", name: "Codex" };
const CHATGPT: Agent = { id: "a4", kind: "chatgpt", name: "ChatGPT" };
const CURSOR: Agent = { id: "a5", kind: "other", name: "Cursor" };

describe("посилання запуску агента", () => {
  test("claude — рідне посилання на нову розмову із запитом", () => {
    expect(launchOf(CLAUDE, "Проаналізуй вакансію #1 у joboffer")).toEqual({
      how: "navigate",
      url: "claude://claude.ai/new?q=%D0%9F%D1%80%D0%BE%D0%B0%D0%BD%D0%B0%D0%BB%D1%96%D0%B7%D1%83%D0%B9%20%D0%B2%D0%B0%D0%BA%D0%B0%D0%BD%D1%81%D1%96%D1%8E%20%231%20%D1%83%20joboffer",
    });
  });

  test("claude_code — рідне посилання на нову сесію коду", () => {
    expect(launchOf(CLAUDE_CODE, "fix the bug")).toEqual({ how: "navigate", url: "claude://code/new?q=fix%20the%20bug" });
  });

  test("codex — рідне посилання на нову гілку з параметром prompt", () => {
    expect(launchOf(CODEX, "fix the bug")).toEqual({ how: "navigate", url: "codex://threads/new?prompt=fix%20the%20bug" });
  });

  test("chatgpt — вебадреса для нової вкладки", () => {
    expect(launchOf(CHATGPT, "fix the bug")).toEqual({ how: "open", url: "https://chatgpt.com/?q=fix%20the%20bug" });
  });

  test("інший агент — посилання нема, запит лише копіюється", () => {
    expect(launchOf(CURSOR, "fix the bug")).toBeNull();
  });

  test("рядки, амперсанд і решітка в запиті кодуються, щоб не зламати посилання", () => {
    expect(launchOf(CLAUDE, "A&B #1\nдруга")?.url).toBe("claude://claude.ai/new?q=A%26B%20%231%0A%D0%B4%D1%80%D1%83%D0%B3%D0%B0");
  });
});

describe("запит завдовжки понад межу застосунку — посилання не даємо", () => {
  test("claude: 14000 символів ще відкривається, 14001 — ні", () => {
    expect(launchOf(CLAUDE, "x".repeat(14000))).not.toBeNull();
    expect(launchOf(CLAUDE, "x".repeat(14001))).toBeNull();
  });

  test("claude_code: 5000 символів ще відкривається, 5001 — ні", () => {
    expect(launchOf(CLAUDE_CODE, "x".repeat(5000))).not.toBeNull();
    expect(launchOf(CLAUDE_CODE, "x".repeat(5001))).toBeNull();
  });
});

describe("повідомлення після кліку на агента", () => {
  test("агента запущено — «Відкриваємо …» без згадки буфера", () => {
    expect(requestMessage(CODEX, true)).toBe("Відкриваємо Codex…");
  });

  test("запит завеликий для передачі напряму — просимо скопіювати його кнопкою", () => {
    expect(requestMessage(CURSOR, false)).toBe("Промпт задовгий для передачі напряму — скопіюй його кнопкою «Копіювати промпт».");
  });
});
