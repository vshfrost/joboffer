import { describe, expect, test } from "vitest";

import { promptParts } from "./onboarding";

const PROMPT = [
  "Set up my joboffer profile with me, step by step.",
  "",
  "Rules",
  "- Talk to me in the language I write in.",
  "- Never invent or guess data.",
  "",
  "Step 0 — Status. Call get_profile and show a checklist.",
  "",
  "Step 1 — CV (required). Ask me to attach my CV. Read it in full.",
  "",
  "Finish. Call get_profile again.",
  "",
].join("\n");

describe("promptParts: показ промпта налаштування профілю", () => {
  test("вступ — перший абзац", () => {
    expect(promptParts(PROMPT).intro).toBe("Set up my joboffer profile with me, step by step.");
  });

  test("правила — пункти розділу Rules без маркерів", () => {
    expect(promptParts(PROMPT).rules).toEqual(["Talk to me in the language I write in.", "Never invent or guess data."]);
  });

  test("кроки — заголовок до першої крапки з пробілом і решта абзацу, фінал теж блок", () => {
    expect(promptParts(PROMPT).steps).toEqual([
      { title: "Step 0 — Status", body: "Call get_profile and show a checklist." },
      { title: "Step 1 — CV (required)", body: "Ask me to attach my CV. Read it in full." },
      { title: "Finish", body: "Call get_profile again." },
    ]);
  });

  test("абзац без речення — лише заголовок", () => {
    expect(promptParts("Intro.\n\nLast words").steps).toEqual([{ title: "Last words", body: "" }]);
  });

  test("без розділу Rules правил нема", () => {
    expect(promptParts("Intro.\n\nStep 0 — Status. Go.").rules).toEqual([]);
  });

  test("порожній промпт — порожній показ", () => {
    expect(promptParts("")).toEqual({ intro: "", rules: [], steps: [] });
  });
});
