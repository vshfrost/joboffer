/** Блок «Делегувати агенту»: кнопки підключених агентів, «Копіювати промпт», промпт за випадашкою лише для читання. */
import { waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import { spyLaunch } from "../ui/agents/launchHarness";
import { CHATGPT, CLAUDE, CLAUDE_CODE, CODEX, CURSOR, type ApiAgent } from "./agentsBackend";
import { clipboardUser, openConnected, openDelegate } from "./firstStepsHarness";
import { PROMPTS, SETUP_PROMPT, type PromptsReply } from "./promptsBackend";

afterEach(() => {
  vi.restoreAllMocks();
});

async function openBlock(agents: readonly ApiAgent[] | "fail", prompts: PromptsReply = PROMPTS) {
  const opened = await openConnected(agents, ["claude"], prompts);
  const { user, writeText } = clipboardUser();
  const block = await openDelegate(opened.card, user);
  return { ...opened, user, writeText, block };
}

const VIEW = { name: "Переглянути промпт" };

describe("промпт за випадашкою", () => {
  test("«Переглянути промпт» закрито за замовчуванням, є позначка «Лише для читання»", async () => {
    const { block } = await openBlock([CLAUDE]);

    expect(block.getByRole("button", VIEW).getAttribute("aria-expanded")).toBe("false");
    expect(block.getByText("Лише для читання")).toBeDefined();
    expect(block.queryByText(/Set up my joboffer profile with me/)).toBeNull();
  });

  test("розкритий промпт — текст для читання й виділення: вступ, розділ Rules і блоки кроків, без поля вводу", async () => {
    const { block, user } = await openBlock([CLAUDE]);

    await user.click(block.getByRole("button", VIEW));

    expect(block.getByRole("button", VIEW).getAttribute("aria-expanded")).toBe("true");
    expect(block.getByText("Set up my joboffer profile with me, step by step, through the connected joboffer MCP connector. The profile was just created and is probably empty.")).toBeDefined();
    expect(block.getByRole("heading", { level: 4, name: "Rules" })).toBeDefined();
    expect(block.getAllByRole("listitem")).toHaveLength(6);
    expect(block.getByText("Never invent or guess data. You may suggest values from my CV, but I confirm them.")).toBeDefined();
    expect(block.getAllByRole("heading", { level: 4 }).map((heading) => heading.textContent)).toEqual([
      "Rules",
      "Step 0 — Status",
      "Step 1 — CV (required)",
      "Step 2 — Contacts for the CV header (required: full name and email)",
      "Step 3 — Career goal (required: at least one role)",
      "Step 4 — Locations and filters (required: at least one location)",
      "Step 5 — CV photo (optional)",
      "Step 6 — Job mail (optional)",
      "Finish",
    ]);
    expect(block.getByText(/^Call get_profile, get_original_cv, list_photos and get_mail_inbox\. Show a checklist of steps 1–6/)).toBeDefined();
    expect(block.queryByRole("textbox")).toBeNull();
  });

  test("повторний клік знову ховає промпт", async () => {
    const { block, user } = await openBlock([CLAUDE]);
    await user.click(block.getByRole("button", VIEW));

    await user.click(block.getByRole("button", VIEW));

    expect(block.queryByText(/Set up my joboffer profile with me/)).toBeNull();
  });
});

describe("копіювання", () => {
  test("«Копіювати промпт» копіює весь промпт, навіть коли його згорнуто", async () => {
    const { block, user, writeText } = await openBlock([CLAUDE]);
    expect(block.getByRole("button", VIEW).getAttribute("aria-expanded")).toBe("false");

    await user.click(block.getByRole("button", { name: "Копіювати промпт" }));

    expect(writeText).toHaveBeenCalledExactlyOnceWith(SETUP_PROMPT);
    expect(await block.findByText("Промпт скопійовано. Встав його у свій агент.")).toBeDefined();
    expect(block.getByRole("button", VIEW).getAttribute("aria-expanded")).toBe("false");
  });

  test("буфер недоступний — промпт розкривається й виділяється для ручного копіювання", async () => {
    const { block, user, writeText } = await openBlock([CLAUDE]);
    writeText.mockRejectedValueOnce(new Error("denied"));

    await user.click(block.getByRole("button", { name: "Копіювати промпт" }));

    expect(await block.findByText("Не вдалося скопіювати автоматично. Виділи текст промпту й скопіюй вручну.")).toBeDefined();
    expect(block.getByRole("button", VIEW).getAttribute("aria-expanded")).toBe("true");
    const selection = window.getSelection();
    expect(selection?.toString()).toContain("Set up my joboffer profile with me");
  });
});

describe("курсор кнопок блоку", () => {
  test.each(["Копіювати промпт", "Переглянути промпт"])("«%s» має вказівник-руку", async (name) => {
    const { block } = await openBlock([CLAUDE]);

    expect(block.getByRole("button", { name }).className).toContain("cursor-pointer");
  });
});

describe("кнопки агентів", () => {
  test("лише підключені агенти, по кнопці на кожного", async () => {
    const { block } = await openBlock([CLAUDE, CODEX]);

    expect(block.getByRole("button", { name: "Відкрити Claude" })).toBeDefined();
    expect(block.getByRole("button", { name: "Відкрити Codex" })).toBeDefined();
    expect(block.queryByRole("button", { name: "Відкрити ChatGPT" })).toBeNull();
    expect(block.queryByText("Агент не визначений")).toBeNull();
  });

  test("Claude: відкриває нову розмову з цим промптом у посиланні, не копіює його й пише «Відкриваємо Claude…»", async () => {
    const launch = spyLaunch();
    const { block, user, writeText } = await openBlock([CLAUDE]);

    await user.click(block.getByRole("button", { name: "Відкрити Claude" }));

    expect(writeText).not.toHaveBeenCalled();
    expect(launch.navigations).toEqual([`claude://claude.ai/new?q=${encodeURIComponent(SETUP_PROMPT)}`]);
    expect(await block.findByText("Відкриваємо Claude…")).toBeDefined();
  });

  test("промпт завеликий для посилання (Claude Code, понад 5000 знаків) — агент не відкривається, підказка вказує на «Копіювати промпт»", async () => {
    const launch = spyLaunch();
    const { block, user, writeText } = await openBlock([CLAUDE_CODE], { ...PROMPTS, "onboarding/setup": "x".repeat(5001) });

    await user.click(block.getByRole("button", { name: "Відкрити Claude Code" }));

    expect(await block.findByText("Промпт задовгий для передачі напряму — скопіюй його кнопкою «Копіювати промпт».")).toBeDefined();
    expect(launch.navigations).toEqual([]);
    expect(launch.open).not.toHaveBeenCalled();
    expect(writeText).not.toHaveBeenCalled();
  });

  test("Claude Code і Codex відкриваються своїми посиланнями", async () => {
    const launch = spyLaunch();
    const { block, user } = await openBlock([CLAUDE_CODE, CODEX]);

    await user.click(block.getByRole("button", { name: "Відкрити Claude Code" }));
    await user.click(block.getByRole("button", { name: "Відкрити Codex" }));

    expect(launch.navigations).toEqual([
      `claude://code/new?q=${encodeURIComponent(SETUP_PROMPT)}`,
      `codex://threads/new?prompt=${encodeURIComponent(SETUP_PROMPT)}`,
    ]);
  });

  test("ChatGPT відкривається в новій вкладці", async () => {
    const launch = spyLaunch();
    const { block, user } = await openBlock([CHATGPT]);

    await user.click(block.getByRole("button", { name: "Відкрити ChatGPT" }));

    expect(launch.open).toHaveBeenCalledExactlyOnceWith(`https://chatgpt.com/?q=${encodeURIComponent(SETUP_PROMPT)}`, "_blank", "noopener");
  });

  test("буфер недоступний — агент усе одно відкривається, без повідомлення про копіювання", async () => {
    const launch = spyLaunch();
    const { block, user, writeText } = await openBlock([CLAUDE]);
    writeText.mockRejectedValueOnce(new Error("denied"));

    await user.click(block.getByRole("button", { name: "Відкрити Claude" }));

    expect(await block.findByText("Відкриваємо Claude…")).toBeDefined();
    expect(launch.navigations).toHaveLength(1);
    expect(block.queryByText("Не вдалося скопіювати автоматично. Виділи текст промпту й скопіюй вручну.")).toBeNull();
    expect(block.getByRole("button", VIEW).getAttribute("aria-expanded")).toBe("false");
  });
});

describe("агент не визначений", () => {
  test.each([
    ["агент kind «other»", [CURSOR]],
    ["список агентів порожній", []],
    ["список агентів недоступний", "fail" as const],
  ])("%s — підпис «Агент не визначений», кнопок запуску нема, копіювання лишається", async (_name, agents) => {
    const { block, user, writeText } = await openBlock(agents);

    expect(await block.findByText("Агент не визначений")).toBeDefined();
    expect(block.queryAllByRole("button", { name: /^Відкрити / })).toEqual([]);
    await user.click(block.getByRole("button", { name: "Копіювати промпт" }));
    expect(writeText).toHaveBeenCalledExactlyOnceWith(SETUP_PROMPT);
  });

  test("агент kind «other» поруч із відомим не заважає: є кнопка відомого, підпису нема", async () => {
    const { block } = await openBlock([CURSOR, CLAUDE]);

    expect(block.getByRole("button", { name: "Відкрити Claude" })).toBeDefined();
    expect(block.queryByText("Агент не визначений")).toBeNull();
  });
});

test("блок має заголовок «Делегувати агенту»", async () => {
  const { block } = await openBlock([CLAUDE]);

  expect(block.getByRole("heading", { level: 3, name: "Делегувати агенту" })).toBeDefined();
  expect(within(document.body).getAllByRole("region", { name: "Делегувати агенту" })).toHaveLength(1);
});

describe("текст промпта приходить із сервера", () => {
  const SERVER = { ...PROMPTS, "onboarding/setup": "Server-side setup prompt.\n\nStep 0 — Status. Check everything." };

  test("копіюється й відкриває агента саме текст із GET /api/prompts", async () => {
    const launch = spyLaunch();
    const { block, user, writeText } = await openBlock([CLAUDE], SERVER);

    await user.click(block.getByRole("button", { name: "Копіювати промпт" }));
    expect(writeText).toHaveBeenCalledExactlyOnceWith("Server-side setup prompt.\n\nStep 0 — Status. Check everything.");
    await user.click(block.getByRole("button", { name: "Відкрити Claude" }));

    expect(launch.navigations).toEqual([`claude://claude.ai/new?q=${encodeURIComponent("Server-side setup prompt.\n\nStep 0 — Status. Check everything.")}`]);
  });

  test("показ промпта теж із сервера", async () => {
    const { block, user } = await openBlock([CLAUDE], SERVER);

    await user.click(block.getByRole("button", VIEW));

    expect(block.getByText("Server-side setup prompt.")).toBeDefined();
    expect(block.getByRole("heading", { level: 4, name: "Step 0 — Status" })).toBeDefined();
  });

  test("Claude Code відкривається з повним промптом: він вкладається в ліміт 5000 знаків", async () => {
    const launch = spyLaunch();
    const { block, user } = await openBlock([CLAUDE_CODE]);

    await user.click(block.getByRole("button", { name: "Відкрити Claude Code" }));

    expect(SETUP_PROMPT.length).toBeLessThan(5000);
    expect(launch.navigations).toEqual([`claude://code/new?q=${encodeURIComponent(SETUP_PROMPT)}`]);
  });

  test("запит текстів лише один, скільки б кнопок не було", async () => {
    const { promptsStub } = await openBlock([CLAUDE, CODEX]);

    expect(promptsStub.requests).toBe(1);
  });
});

describe("сервер не віддав промпт", () => {
  test.each([["кнопка агента", "Відкрити Claude"], ["«Копіювати промпт»", "Копіювати промпт"]])("%s: помилка, нічого не копіюється й не відкривається", async (_name, button) => {
    const launch = spyLaunch();
    const { block, user, writeText } = await openBlock([CLAUDE], "fail");

    await user.click(block.getByRole("button", { name: button }));

    expect(await block.findByText("Не вдалося отримати текст запиту. Спробуй ще раз.")).toBeDefined();
    expect(writeText).not.toHaveBeenCalled();
    expect(launch.navigations).toEqual([]);
    expect(launch.open).not.toHaveBeenCalled();
  });

  test("сервер оговтався — наступний клік копіює промпт", async () => {
    const opened = await openConnected([CLAUDE], ["claude"], "fail");
    const { user, writeText } = clipboardUser();
    const block = await openDelegate(opened.card, user);
    await user.click(block.getByRole("button", { name: "Копіювати промпт" }));
    await block.findByText("Не вдалося отримати текст запиту. Спробуй ще раз.");
    opened.promptsStub.reply = PROMPTS;

    await user.click(block.getByRole("button", { name: "Копіювати промпт" }));

    await waitFor(async () => {
      await user.click(block.getByRole("button", { name: "Копіювати промпт" }));
      expect(writeText).toHaveBeenCalledWith(SETUP_PROMPT);
    });
  });

  test("«Переглянути промпт» без тексту каже про помилку, а не показує порожнечу", async () => {
    const { block, user } = await openBlock([CLAUDE], "fail");

    await user.click(block.getByRole("button", VIEW));

    expect(within(block.getByRole("region", { name: "Промпт" })).getByText("Не вдалося отримати текст запиту. Спробуй ще раз.")).toBeDefined();
  });
});

test("поки текст промпта вантажиться, кнопки недоступні", async () => {
  const opened = await openConnected([CLAUDE], ["claude"], "hang");
  const { user } = clipboardUser();
  await user.click(await within(opened.card).findByRole("button", { name: /Завершити з агентом/ }));
  const block = within(await within(opened.card).findByRole("region", { name: "Делегувати агенту" }));

  expect((block.getByRole("button", { name: "Копіювати промпт" }) as HTMLButtonElement).disabled).toBe(true);
  expect(((await block.findByRole("button", { name: "Відкрити Claude" })) as HTMLButtonElement).disabled).toBe(true);
});

test("«Переглянути промпт», поки текст вантажиться, каже про завантаження", async () => {
  const opened = await openConnected([CLAUDE], ["claude"], "hang");
  const { user } = clipboardUser();
  await user.click(await within(opened.card).findByRole("button", { name: /Завершити з агентом/ }));
  const block = within(await within(opened.card).findByRole("region", { name: "Делегувати агенту" }));

  await user.click(block.getByRole("button", VIEW));

  expect(within(block.getByRole("region", { name: "Промпт" })).getByText("Завантажуємо промпт…")).toBeDefined();
});
