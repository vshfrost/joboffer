/** Блок «Делегувати агенту» на всіх сторінках, де він є: без агентів — «Агент не визначений» і копіювання, з агентом — відкритий агент без запису в буфер. */
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { spyLaunch } from "../ui/agents/launchHarness";
import { CLAUDE, connectAgents, type ApiAgent } from "./agentsBackend";
import { COPIED, delegateBlocks, findDelegate } from "./delegateHarness";
import { apiFact, factsBackend } from "./factsBackend";
import { jobBlocksBackend, openJob } from "./jobBlocksHarness";
import { apiAnalysis, apiDocument, apiJob, apiTriage, jobsBackend } from "./jobsBackend";
import { apiTopic, prepBackend } from "./prepBackend";
import { ddd } from "./prepFixtures";
import { openPrep, openTopic } from "./prepHarness";
import { connectPrompts, PROMPTS } from "./promptsBackend";
import { renderClient } from "./testClient";

type Scope = ReturnType<typeof within>;

interface PageCase {
  page: string;
  /** Опис під заголовком блоку «Делегувати агенту»: за ним блок відрізняють від інших на сторінці. */
  description: string;
  /** Підпис старої кнопки запиту, якої на сторінці вже нема. */
  oldLabel: string;
  prompt: string;
  /** Відкриває сторінку з цими підключеними агентами; віддає користувача й область, де шукати кнопку. */
  open(agents: ApiAgent[]): Promise<{ user: ReturnType<typeof userEvent.setup>; scope: Scope }>;
}

const body = () => within(document.body);

const JOB = apiJob(1, { title: "Senior Backend Engineer", company: "Northstar Labs", text: "Розробка API на Python." });

const REQUEST_CV =
  "Prepare a CV for job #1 in joboffer using prepare_cv. Use the confirmed facts and the rules from the brief. Save the new version with save_cv and check the ATS report. Do not add unconfirmed claims.";

const ADD_JOB_PROMPT = PROMPTS["requests/add_job"];

const PAGES: PageCase[] = [
  {
    page: "аналіз вакансії",
    description: "Агент проаналізує вакансію за підтвердженими фактами й збереже оцінку відповідності.",
    oldLabel: "Підготувати запит для Claude",
    prompt: "Analyse job #1 in joboffer",
    async open(agents) {
      const backend = jobsBackend([JOB], []);
      connectPrompts(backend);
      connectAgents(backend, agents);
      renderClient("/vacancies/1", backend.fetchFn);
      await screen.findByRole("heading", { level: 1, name: "Senior Backend Engineer" });
      return { user: userEvent.setup(), scope: body() };
    },
  },
  {
    page: "картка документа",
    description: "Агент підготує CV на основі аналізу вакансії та підтверджених фактів.",
    oldLabel: "Підготувати запит",
    prompt: REQUEST_CV,
    async open(agents) {
      const backend = jobsBackend([JOB], [], []);
      connectPrompts(backend);
      connectAgents(backend, agents);
      renderClient("/vacancies/1", backend.fetchFn);
      const card = await screen.findByRole("region", { name: "CV" });
      return { user: userEvent.setup(), scope: within(card) };
    },
  },
  {
    page: "картка документа з версіями",
    description: "Агент підготує нову версію за актуальним аналізом і підтвердженими фактами.",
    oldLabel: "Нова версія через Claude",
    prompt: REQUEST_CV,
    async open(agents) {
      const backend = jobsBackend([JOB], [], [apiDocument(1, "cv", 1)]);
      connectPrompts(backend);
      connectAgents(backend, agents);
      renderClient("/vacancies/1", backend.fetchFn);
      const card = await screen.findByRole("region", { name: "CV" });
      return { user: userEvent.setup(), scope: within(card) };
    },
  },
  {
    page: "підготовка до вакансії",
    description: "Агент запропонує теми підготовки на основі прогалин вакансії.",
    oldLabel: "Скопіювати запит для Claude",
    prompt: "Prepare me for job #1 in joboffer",
    async open(agents) {
      const backend = jobBlocksBackend();
      connectAgents(backend, agents);
      const { user } = await openJob(backend);
      return { user, scope: body() };
    },
  },
  {
    page: "пакет до інтерв’ю",
    description: "Агент складе питання до інтерв’ю, STAR-історії й питання до компанії.",
    oldLabel: "Скопіювати запит на пакет",
    prompt: "Prepare an interview kit for job #1 in joboffer",
    async open(agents) {
      const backend = jobBlocksBackend();
      connectAgents(backend, agents);
      const { user } = await openJob(backend);
      return { user, scope: body() };
    },
  },
  {
    page: "список вакансій (тріаж)",
    description: "Агент оцінить одну пачку нових вакансій (до 5) за тими самими правилами, що й автотріаж сервера, покаже підсумок і спитає, чи продовжувати.",
    oldLabel: "Запит для тріажу",
    prompt: "Triage the new jobs in joboffer",
    async open(agents) {
      const backend = jobsBackend([apiJob(1, { title: "Senior Backend Engineer", triage: apiTriage({ score: 86, verdict: "analyse" }) })], []);
      connectPrompts(backend);
      connectAgents(backend, agents);
      renderClient("/vacancies", backend.fetchFn);
      await screen.findByRole("status", { name: "Результат" });
      return { user: userEvent.setup(), scope: body() };
    },
  },
  {
    page: "реєстр підготовки",
    description: "Агент запропонує теми підготовки на основі прогалин твоїх вакансій.",
    oldLabel: "Скопіювати запит для Claude",
    prompt: "Suggest prep topics based on the gaps in my jobs in joboffer",
    async open(agents) {
      const backend = prepBackend();
      connectAgents(backend, agents);
      await openPrep(backend);
      return { user: userEvent.setup(), scope: body() };
    },
  },
  {
    page: "тема підготовки",
    description: "Агент складе або оновить план теми.",
    oldLabel: "Запит для Claude: план",
    prompt: "Create or update the plan for topic #7 in joboffer",
    async open(agents) {
      const backend = prepBackend({ topics: [ddd()] });
      connectAgents(backend, agents);
      await openTopic(backend, "/prep/7");
      return { user: userEvent.setup(), scope: body() };
    },
  },
  {
    page: "вкладка «Прогалини»",
    description: "Агент спитає про відкриті прогалини вакансії й збереже твої відповіді.",
    oldLabel: "Підготувати запит для Claude",
    prompt: "Clarify the open gaps of job #1 in joboffer. Call prepare_analysis to see the gaps, their questions and the answers already given, and list_facts to see what is already known. Ask me about each open gap, one at a time. If I have the experience, write each fact as one atomic claim with my numbers and names, and only after I approve the wording call answer_gap with has_experience true and those facts. If I do not, call answer_gap with has_experience false. Never ask again about a gap that already has an answer, and never invent facts.",
    async open(agents) {
      const backend = jobsBackend([JOB], [apiAnalysis(1)]);
      connectPrompts(backend);
      connectAgents(backend, agents);
      renderClient("/vacancies/1", backend.fetchFn);
      const user = userEvent.setup();
      await user.click(await screen.findByRole("tab", { name: "Прогалини · 1" }));
      return { user, scope: body() };
    },
  },
  {
    page: "факти",
    description: "Агент допоможе сформулювати нові факти й збереже їх після твого схвалення.",
    oldLabel: "Підготувати запит для Claude",
    prompt: "Help me add facts to my joboffer profile. Call list_facts first and do not repeat what is already saved. Ask me one question at a time about the experience, skills, projects and achievements that are missing. Write each fact as one atomic claim with my numbers, names and dates exactly as I say them, show it to me, and only after I approve the wording call save_facts with source chat and then confirm_facts for the approved facts. Never infer or invent anything.",
    async open(agents) {
      const backend = factsBackend([apiFact(1, "skill", "Python 3.14", true)], null);
      connectPrompts(backend);
      connectAgents(backend, agents);
      renderClient("/facts", backend.fetchFn);
      await screen.findByRole("heading", { level: 1, name: "Факти" });
      return { user: userEvent.setup(), scope: body() };
    },
  },
  {
    page: "додавання вакансії",
    description: "Агент попросить посилання чи текст вакансії, збереже її й запропонує аналіз",
    oldLabel: "Підготувати запит для Claude",
    prompt: ADD_JOB_PROMPT,
    async open(agents) {
      const backend = jobsBackend([JOB], []);
      connectPrompts(backend);
      connectAgents(backend, agents);
      renderClient("/vacancies/new", backend.fetchFn);
      await screen.findByRole("heading", { level: 1, name: "Додати вакансію" });
      return { user: userEvent.setup(), scope: body() };
    },
  },
];

afterEach(() => {
  vi.restoreAllMocks();
});

describe.each(PAGES)("$page", ({ description, oldLabel, prompt, open }) => {
  const encoded = encodeURIComponent(prompt);
  test("є блок «Делегувати агенту» з описом, а старої кнопки й поля запиту нема", async () => {
    const { scope } = await open([CLAUDE]);

    await findDelegate(description);
    expect(scope.queryByRole("button", { name: new RegExp(`^${oldLabel}`) })).toBeNull();
    expect(scope.queryByRole("textbox", { name: "Запит для Claude" })).toBeNull();
  });

  test("жодного агента: «Агент не визначений», кнопок запуску нема, «Копіювати промпт» копіює запит і нічого не відкриває", async () => {
    const { user } = await open([]);
    const writeText = vi.spyOn(navigator.clipboard, "writeText");
    const launch = spyLaunch();

    const block = await findDelegate(description);
    expect(await block.findByText("Агент не визначений")).toBeDefined();
    expect(block.queryAllByRole("button", { name: /^Відкрити / })).toEqual([]);
    await user.click(block.getByRole("button", { name: "Копіювати промпт" }));

    expect(writeText).toHaveBeenCalledExactlyOnceWith(prompt);
    expect(await block.findByText(COPIED)).toBeDefined();
    expect(launch.navigations).toEqual([]);
    expect(launch.open).not.toHaveBeenCalled();
    expect(screen.queryByText("Жоден агент не підключений.")).toBeNull();
  });

  test("один агент Claude: кнопка «Відкрити Claude» відкриває нову розмову із запитом у посиланні й не чіпає буфер", async () => {
    const { user } = await open([CLAUDE]);
    const writeText = vi.spyOn(navigator.clipboard, "writeText");
    const launch = spyLaunch();

    const block = await findDelegate(description);
    await user.click(await block.findByRole("button", { name: "Відкрити Claude" }));

    expect(writeText).not.toHaveBeenCalled();
    expect(launch.navigations).toEqual([`claude://claude.ai/new?q=${encoded}`]);
    expect(await block.findByText("Відкриваємо Claude…")).toBeDefined();
  });
});

describe("кілька блоків на одній сторінці", () => {
  test("список агентів запитується один раз, а кожен блок має свої кнопки агента і своє підтвердження", async () => {
    const backend = prepBackend({ topics: [ddd()] });
    const agents = connectAgents(backend, [CLAUDE]);
    await openTopic(backend, "/prep/7");
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, "writeText");
    spyLaunch();

    const plan = await findDelegate("Агент складе або оновить план теми.");
    const questions = await findDelegate("Агент складе питання квізу до теми.");
    const quiz = await findDelegate("Агент проведе квіз на сьогодні з цієї теми.");
    for (const block of [plan, questions, quiz]) {
      expect(await block.findByRole("button", { name: "Відкрити Claude" })).toBeDefined();
    }
    expect(delegateBlocks()).toHaveLength(3);
    await user.click(questions.getByRole("button", { name: "Відкрити Claude" }));

    expect(writeText).not.toHaveBeenCalled();
    await waitFor(() => expect(questions.getByRole("status").textContent).toBe("Відкриваємо Claude…"));
    expect(plan.getByRole("status").textContent).toBe("");
    expect(quiz.getByRole("status").textContent).toBe("");
    expect(agents.requests).toBe(1);
  });

  test("тема без кроків: блок плану теж має кнопку агента", async () => {
    const backend = prepBackend({ topics: [apiTopic(7, { title: "Порожня" })] });
    connectAgents(backend, [CLAUDE]);
    await openTopic(backend, "/prep/7");

    const block = await findDelegate("Агент складе план теми: вивчення → практика → перевірка.");
    expect(await block.findByRole("button", { name: "Відкрити Claude" })).toBeDefined();
  });
});

describe("список агентів між відкриттями сторінки", () => {
  test("повернувшись на сторінку, список запитується знову: щойно підключений агент зʼявляється", async () => {
    const description = "Агент оцінить одну пачку нових вакансій (до 5) за тими самими правилами, що й автотріаж сервера, покаже підсумок і спитає, чи продовжувати.";
    const connected: ApiAgent[] = [];
    const backend = jobsBackend([apiJob(1, { title: "Senior Backend Engineer", triage: apiTriage({ score: 86, verdict: "analyse" }) })], []);
    connectPrompts(backend);
    const stub = connectAgents(backend, connected);
    const view = renderClient("/vacancies", backend.fetchFn);
    await screen.findByRole("status", { name: "Результат" });
    expect(await (await findDelegate(description)).findByText("Агент не визначений")).toBeDefined();
    expect(stub.requests).toBe(1);

    await act(() => view.router.navigate("/no-such-page"));
    connected.push(CLAUDE);
    await act(() => view.router.navigate("/vacancies"));

    const block = await findDelegate(description);
    expect(await block.findByRole("button", { name: "Відкрити Claude" })).toBeDefined();
    expect(block.queryByText("Агент не визначений")).toBeNull();
    expect(stub.requests).toBe(2);
  });
});
