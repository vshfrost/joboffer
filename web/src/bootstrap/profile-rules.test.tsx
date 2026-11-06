import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { FULL_PROFILE, profileBackend, validationError, type ApiProfile } from "./profileBackend";
import { json, renderClient } from "./testClient";

const KEYWORDS = "Імпортувати, якщо назва містить";
const EXCLUDE = "Не імпортувати";
const STOP = "Знижувати пріоритет";

async function openRules(profile: ApiProfile = FULL_PROFILE, overrides: Parameters<typeof profileBackend>[1] = {}) {
  const backend = profileBackend(profile, overrides);
  renderClient("/profile/rules", backend.fetchFn);
  await screen.findByRole("heading", { level: 1, name: "Правила відбору" });
  return { backend, user: userEvent.setup() };
}

const field = (label: string) => screen.getByLabelText(label) as HTMLTextAreaElement;
const saveButton = () => screen.getByRole("button", { name: "Зберегти зміни" });
const block = (label: string) => field(label).closest("section") as HTMLElement;

describe("редактор «Правила відбору»", () => {
  test("відкривається за прямою адресою й показує три окремі списки", async () => {
    await openRules();
    expect(screen.getByText("Профіль / Правила відбору")).toBeDefined();
    expect(document.title).toBe("Правила відбору · Профіль · joboffer");
    expect(field(KEYWORDS).value).toBe("backend");
    expect(field(EXCLUDE).value).toBe("junior\nintern");
    expect(field(STOP).value).toBe("crypto");
  });

  test("кожен список має пояснення", async () => {
    await openRules();
    expect(within(block(KEYWORDS)).getByText("Достатньо збігу одного слова в назві. Порожньо — без обмеження.")).toBeDefined();
    expect(within(block(EXCLUDE)).getByText("Вакансії з будь-яким із цих слів у назві з джерел не імпортуються.")).toBeDefined();
    expect(
      within(block(STOP)).getByText("Вакансії з цими словами опускаються вниз списку при аналізі, але з імпорту не виключаються."),
    ).toBeDefined();
  });

  test("пояснення й лічильник повʼязані з полем через aria-describedby", async () => {
    await openRules();
    const described = (field(KEYWORDS).getAttribute("aria-describedby") ?? "")
      .split(" ")
      .map((id) => document.getElementById(id)?.textContent ?? "");
    expect(described.join(" ")).toContain("Порожньо — без обмеження.");
    expect(described.join(" ")).toContain("1 слово");
  });

  test("лічильники: слів у кожному списку", async () => {
    await openRules();
    expect(within(block(KEYWORDS)).getByText("1 слово")).toBeDefined();
    expect(within(block(EXCLUDE)).getByText("2 слова")).toBeDefined();
    expect(within(block(STOP)).getByText("1 слово")).toBeDefined();
  });

  test("лічильник оновлюється під час набору й не рахує порожні рядки та повтори", async () => {
    const { user } = await openRules();
    await user.type(field(KEYWORDS), "\n\nPython\npython\nGo\n   ");
    expect(within(block(KEYWORDS)).getByText("3 слова")).toBeDefined();
  });

  test("порожній список слів для пошуку — «Без обмеження»", async () => {
    const empty = structuredClone(FULL_PROFILE);
    empty.rules.title_keywords = [];
    await openRules(empty);
    expect(within(block(KEYWORDS)).getByText("Без обмеження")).toBeDefined();
    expect(within(block(EXCLUDE)).getByText("2 слова")).toBeDefined();
  });

  test("порожні «Не імпортувати» і «Знижувати пріоритет» — «Порожньо»", async () => {
    const empty = structuredClone(FULL_PROFILE);
    empty.rules = { title_keywords: ["backend"], title_exclude: [], stop_words: [] };
    await openRules(empty);
    expect(within(block(EXCLUDE)).getByText("Порожньо")).toBeDefined();
    expect(within(block(STOP)).getByText("Порожньо")).toBeDefined();
  });

  test("правка вмикає «Зберегти», статус: є незбережені зміни", async () => {
    const { user } = await openRules();
    expect((saveButton() as HTMLButtonElement).disabled).toBe(true);
    await user.type(field(EXCLUDE), "\nsenior");
    expect((saveButton() as HTMLButtonElement).disabled).toBe(false);
    expect(screen.getByRole("status").textContent).toBe("Є незбережені зміни");
  });

  test("збереження «Правил» шле лише PUT /api/profile/rules; локації не змінились", async () => {
    const { backend, user } = await openRules();
    await user.clear(field(KEYWORDS));
    await user.type(field(KEYWORDS), "python\n platform ");
    await user.type(field(EXCLUDE), "\nsenior");
    await user.click(saveButton());
    await screen.findByText("Збережено");
    expect(backend.puts).toEqual([
      {
        section: "rules",
        body: {
          title_keywords: ["python", "platform"],
          title_exclude: ["junior", "intern", "senior"],
          stop_words: ["crypto"],
        },
      },
    ]);
    expect(backend.state.locations).toEqual(FULL_PROFILE.locations);
  });

  test("збереження порожніх «Слів для пошуку» знімає обмеження", async () => {
    const { backend, user } = await openRules();
    await user.clear(field(KEYWORDS));
    await user.click(saveButton());
    await screen.findByText("Збережено");
    expect(backend.puts[0]?.body).toMatchObject({ title_keywords: [] });
    expect(within(block(KEYWORDS)).getByText("Без обмеження")).toBeDefined();
  });

  test("5xx — загальна помилка, введене лишається", async () => {
    const { user } = await openRules(FULL_PROFILE, { "PUT /api/profile/rules": () => json(500, { code: "internal_error" }) });
    await user.type(field(STOP), "\ngambling");
    await user.click(saveButton());
    expect((await screen.findByRole("alert")).textContent).toContain("Не вдалося зберегти");
    expect(field(STOP).value).toBe("crypto\ngambling");
  });

  test("422 — помилка біля поля, введене лишається", async () => {
    const { user } = await openRules(FULL_PROFILE, {
      "PUT /api/profile/rules": () => validationError(["title_exclude", "Забагато слів."]),
    });
    await user.type(field(EXCLUDE), "\nx");
    await user.click(saveButton());
    expect(await within(block(EXCLUDE)).findByText("Забагато слів.")).toBeDefined();
    expect(field(EXCLUDE).getAttribute("aria-invalid")).toBe("true");
    expect(field(EXCLUDE).value).toBe("junior\nintern\nx");
    expect(document.activeElement).toBe(field(EXCLUDE));
  });

  test("«Скасувати» повертає збережені списки", async () => {
    const { user } = await openRules();
    await user.type(field(KEYWORDS), "\nextra");
    await user.click(screen.getByRole("button", { name: "Скасувати" }));
    expect(field(KEYWORDS).value).toBe("backend");
    expect(within(block(KEYWORDS)).getByText("1 слово")).toBeDefined();
  });

  test("50 слів і довгі рядки не ламають форму", async () => {
    const words = Array.from({ length: 50 }, (_, index) => `word-${index}-${"x".repeat(150)}`);
    const long = structuredClone(FULL_PROFILE);
    long.rules.title_exclude = words;
    const { backend, user } = await openRules(long);
    expect(within(block(EXCLUDE)).getByText("50 слів")).toBeDefined();
    await user.type(field(STOP), "\nmore");
    await user.click(saveButton());
    await screen.findByText("Збережено");
    expect((backend.puts[0]?.body as { title_exclude: string[] }).title_exclude).toEqual(words);
  });

  test("Tab іде за порядком списків", async () => {
    const { user } = await openRules();
    field(KEYWORDS).focus();
    await user.type(field(KEYWORDS), " ");
    await user.tab();
    expect(document.activeElement).toBe(field(EXCLUDE));
    await user.tab();
    expect(document.activeElement).toBe(field(STOP));
  });
});
