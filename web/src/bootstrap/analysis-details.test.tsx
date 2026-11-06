/** Деталі вакансії: оцінка відповідності, тріаж окремо, вкладки аналізу, запит для Claude (макет A). */
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { COPIED, delegateBlocks, findDelegate, queryDelegate } from "./delegateHarness";
import { apiAnalysis, apiJob, apiTriage, jobsBackend, type ApiAnalysis, type ApiJob } from "./jobsBackend";
import { connectPrompts } from "./promptsBackend";
import { renderClient } from "./testClient";

const ANALYSE = "Агент проаналізує вакансію за підтвердженими фактами й збереже оцінку відповідності.";
const REANALYSE = "Агент оновить аналіз вакансії за актуальним профілем і фактами.";
const GAPS_PROMPT = "Clarify the open gaps of job #1 in joboffer. Call prepare_analysis to see the gaps, their questions and the answers already given, and list_facts to see what is already known. Ask me about each open gap, one at a time. If I have the experience, write each fact as one atomic claim with my numbers and names, and only after I approve the wording call answer_gap with has_experience true and those facts. If I do not, call answer_gap with has_experience false. Never ask again about a gap that already has an answer, and never invent facts.";
const NOTE = "Оцінка за рубрикою 0–100. Це не ймовірність отримати оффер.";
const JOB = apiJob(1, {
  title: "Senior Backend Engineer",
  company: "Northstar Labs",
  location: "Іспанія · Remote",
  text: "Розробка API на Python.\n\nПотрібен PostgreSQL.",
});

async function open(jobs: ApiJob[], analyses: ApiAnalysis[] = [], path = "/vacancies/1", name = "Senior Backend Engineer") {
  const backend = jobsBackend(jobs, analyses);
  connectPrompts(backend);
  const view = renderClient(path, backend.fetchFn);
  await screen.findByRole("heading", { level: 1, name });
  return { backend, view, user: userEvent.setup() };
}

const score = () => screen.getByTestId("match-score").textContent;

describe("повний аналіз", () => {
  test("головний блок: оцінка, примітка, висновок, дата аналізу", async () => {
    await open([JOB], [apiAnalysis(1, { score: 78, summary: "Сильна відповідність основному стеку." })]);
    expect(await screen.findByText("Відповідність профілю")).toBeDefined();
    await waitFor(() => expect(score()).toBe("78%"));
    expect(screen.getByText(NOTE)).toBeDefined();
    expect(screen.getByText("Сильна відповідність основному стеку.")).toBeDefined();
    expect(screen.getByText("Аналіз від 2026-10-22")).toBeDefined();
  });

  test("оцінка 0 — це оцінка, а не «Не оцінено»", async () => {
    await open([JOB], [apiAnalysis(1, { score: 0 })]);
    await waitFor(() => expect(score()).toBe("0%"));
    expect(screen.queryByText("Не оцінено")).toBeNull();
  });

  test("вакансія проходить фільтри профілю", async () => {
    await open([JOB], [apiAnalysis(1)]);
    expect(await screen.findByText("Проходить фільтри профілю")).toBeDefined();
    expect(screen.queryByText("Не підходить")).toBeNull();
  });

  test("«не підходить» показує всі flags", async () => {
    const flags = ["Формат onsite — не з профілю.", "Рівень junior — не з профілю.", "Стоп-слово: crypto."];
    await open([JOB], [apiAnalysis(1, { flags })]);
    expect(await screen.findByText("Не підходить")).toBeDefined();
    const list = screen.getByRole("list", { name: "Чому не підходить" });
    expect(within(list).getAllByRole("listitem").map((item) => item.textContent)).toEqual(flags);
    expect(screen.queryByText("Проходить фільтри профілю")).toBeNull();
  });

  test("застарілий аналіз: підсвічена дата зміни профілю", async () => {
    await open([JOB], [apiAnalysis(1, { stale_since: "2026-10-25T08:30:00Z" })]);
    const stale = await screen.findByRole("status", { name: "Аналіз застарів" });
    expect(stale.textContent).toBe("Аналіз застарів: профіль змінено 2026-10-25");
    expect(stale.className).toContain("bg-status-warning");
  });

  test("актуальний аналіз без позначки застарілості", async () => {
    await open([JOB], [apiAnalysis(1)]);
    await screen.findByText("Проходить фільтри профілю");
    expect(screen.queryByText(/Аналіз застарів/)).toBeNull();
  });

  test("вкладки: Огляд, Вимоги, Прогалини, Опис вакансії — з лічильниками", async () => {
    await open([JOB], [apiAnalysis(1)]);
    const tabs = await screen.findByRole("tablist", { name: "Розділи аналізу" });
    expect(within(tabs).getAllByRole("tab").map((tab) => tab.textContent)).toEqual(["Огляд", "Вимоги · 3", "Прогалини · 1", "Опис вакансії"]);
    expect(within(tabs).getByRole("tab", { name: "Огляд" }).getAttribute("aria-selected")).toBe("true");
  });
});

describe("вкладка «Огляд»", () => {
  test("причини, умови й ключові слова", async () => {
    await open(
      [JOB],
      [
        apiAnalysis(1, {
          reasons: ["Основний стек збігається", "Формат відповідає цілі"],
          seniority: "senior",
          work_mode: "hybrid",
          location: "Барселона",
          languages: ["English", "Español"],
          salary_min_eur: 60000,
          salary_max_eur: 80000,
          relocation: true,
          keywords: ["Python", "FastAPI"],
        }),
      ],
    );
    const panel = await screen.findByRole("tabpanel", { name: "Огляд" });
    const reasons = within(panel).getByRole("list", { name: "Що вплинуло на оцінку" });
    expect(within(reasons).getAllByRole("listitem").map((item) => item.textContent)).toEqual(["Основний стек збігається", "Формат відповідає цілі"]);
    const conditions = within(panel).getByRole("list", { name: "Умови вакансії" });
    const rows = Object.fromEntries(within(conditions).getAllByRole("listitem").map((item) => item.textContent?.split(": ", 2) as [string, string]));
    expect(rows).toEqual({
      Формат: "Hybrid",
      Рівень: "Senior",
      Локація: "Барселона",
      Мови: "English, Español",
      Зарплата: "60 000–80 000 EUR на рік",
      Переїзд: "Допомога з переїздом є",
    });
    const keywords = within(panel).getByRole("list", { name: "Ключові слова" });
    expect(within(keywords).getAllByRole("listitem").map((item) => item.textContent)).toEqual(["Python", "FastAPI"]);
  });

  test("невідомі умови — «не вказано», а не «виконано»", async () => {
    await open(
      [JOB],
      [apiAnalysis(1, { seniority: null, work_mode: null, location: null, languages: [], salary_min_eur: null, salary_max_eur: null, relocation: null, keywords: [], reasons: [] })],
    );
    const panel = await screen.findByRole("tabpanel", { name: "Огляд" });
    const conditions = within(panel).getByRole("list", { name: "Умови вакансії" });
    for (const item of within(conditions).getAllByRole("listitem")) {
      expect(item.textContent).toMatch(/: не вказано$/);
    }
    expect(within(conditions).getAllByRole("listitem")).toHaveLength(6);
    expect(panel.textContent).not.toMatch(/виконано|✓|✔/);
    expect(within(panel).getByText("Ключових слів не вказано.")).toBeDefined();
    expect(within(panel).getByText("Причин не вказано.")).toBeDefined();
  });
});

describe("вкладка «Вимоги»", () => {
  test("обов'язкові й бажані окремо, без вигаданих доказів", async () => {
    const { user } = await open([JOB], [apiAnalysis(1, { must_have: ["Python", "PostgreSQL"], nice_to_have: ["Подієва архітектура"] })]);
    await user.click(await screen.findByRole("tab", { name: "Вимоги · 3" }));
    const panel = screen.getByRole("tabpanel", { name: "Вимоги · 3" });
    const must = within(panel).getByRole("list", { name: "Обов’язкові вимоги" });
    expect(within(must).getAllByRole("listitem").map((item) => item.textContent)).toEqual(["Python", "PostgreSQL"]);
    const nice = within(panel).getByRole("list", { name: "Бажані вимоги" });
    expect(within(nice).getAllByRole("listitem").map((item) => item.textContent)).toEqual(["Подієва архітектура"]);
    expect(within(panel).getByText(/Відсутність факту не означає відсутність навички/)).toBeDefined();
    expect(panel.textContent).not.toMatch(/Підтверджено|Факт #|✓/);
  });

  test("порожня група — «не вказано»", async () => {
    const { user } = await open([JOB], [apiAnalysis(1, { must_have: [], nice_to_have: ["Go"] })]);
    await user.click(await screen.findByRole("tab", { name: "Вимоги · 1" }));
    expect(screen.getByText("Обов’язкових вимог не вказано.")).toBeDefined();
  });

  test("30 вимог з довгими текстами не ламають компонування", async () => {
    const long = `Досвід ${"надзвичайно-довгого-слова".repeat(8)} ${"і ще речення ".repeat(20)}`;
    const must = Array.from({ length: 30 }, (_, index) => `${index + 1}. ${long}`);
    const { user } = await open([JOB], [apiAnalysis(1, { must_have: must, nice_to_have: [] })]);
    await user.click(await screen.findByRole("tab", { name: "Вимоги · 30" }));
    const list = screen.getByRole("list", { name: "Обов’язкові вимоги" });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(30);
    for (const item of items) {
      expect(item.className).toContain("[overflow-wrap:anywhere]");
      expect(item.className).toContain("min-w-0");
    }
  });
});

const GAPS = [
  { number: 1, gap: "Kubernetes у production", question: "Чи працювали з Kubernetes у production?", status: "open" as const, fact_ids: [] },
  { number: 2, gap: "Kafka", question: "Чи писали консʼюмери для Kafka?", status: "closed" as const, fact_ids: [12, 15] },
  { number: 3, gap: "Rust", question: null, status: "no_experience" as const, fact_ids: [] },
];
const GAPS_DESCRIPTION = "Агент спитає про відкриті прогалини вакансії й збереже твої відповіді.";

async function openGaps(gaps = GAPS) {
  const opened = await open([JOB], [apiAnalysis(1, { gaps })]);
  await opened.user.click(await screen.findByRole("tab", { name: `Прогалини · ${gaps.length}` }));
  return opened;
}

const gapItem = (text: string) => within(screen.getByRole("list", { name: "Прогалини" })).getByRole("listitem", { name: text });

describe("вкладка «Прогалини»", () => {
  test("кожна прогалина: текст, питання й статус, в порядку аналізу", async () => {
    await openGaps();
    const list = screen.getByRole("list", { name: "Прогалини" });
    expect(within(list).getAllByRole("listitem").map((item) => item.getAttribute("aria-label"))).toEqual(["Kubernetes у production", "Kafka", "Rust"]);
    expect(within(gapItem("Kubernetes у production")).getByText("Чи працювали з Kubernetes у production?")).toBeDefined();
    expect(within(gapItem("Kafka")).getByText("Чи писали консʼюмери для Kafka?")).toBeDefined();
  });

  test("«Делегувати агенту» — окрема колонка поруч зі списком, а не під ним", async () => {
    await openGaps();
    const list = screen.getByRole("list", { name: "Прогалини" });
    await findDelegate(GAPS_DESCRIPTION);
    const block = delegateBlocks().find((candidate) => candidate.textContent?.includes(GAPS_DESCRIPTION)) as HTMLElement;

    expect(list.parentElement).not.toBe(block.parentElement);
    expect(list.parentElement?.parentElement).toBe(block.parentElement?.parentElement);
    expect(list.compareDocumentPosition(block) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  test("відкрита: статус «Відкрита», посилань на факти нема", async () => {
    await openGaps();
    const item = within(gapItem("Kubernetes у production"));
    expect(item.getByText("Відкрита")).toBeDefined();
    expect(item.queryByRole("link")).toBeNull();
  });

  test("закрита фактами: статус «Закрита фактами» і посилання на кожен факт у «Факти»", async () => {
    await openGaps();
    const item = within(gapItem("Kafka"));
    expect(item.getByText("Закрита фактами")).toBeDefined();
    const links = item.getAllByRole("link");
    expect(links.map((link) => [link.textContent, link.getAttribute("href")])).toEqual([
      ["#12", "/facts?q=%2312"],
      ["#15", "/facts?q=%2315"],
    ]);
  });

  test("нема досвіду: статус «Нема досвіду», питання немає, посилань на факти нема", async () => {
    await openGaps();
    const item = within(gapItem("Rust"));
    expect(item.getByText("Нема досвіду")).toBeDefined();
    expect(item.queryByRole("link")).toBeNull();
    expect(item.queryByText(/\?/)).toBeNull();
  });

  test("статус видно текстом: «Відкрита» лише в відкритої", async () => {
    await openGaps();
    expect(within(gapItem("Kafka")).queryByText("Відкрита")).toBeNull();
    expect(within(gapItem("Rust")).queryByText("Відкрита")).toBeNull();
    expect(within(gapItem("Rust")).queryByText("Закрита фактами")).toBeNull();
  });

  test("порожні прогалини — чесний порожній стан без блоку «Делегувати агенту»", async () => {
    await openGaps([]);
    expect(screen.getByText("Прогалин не зафіксовано")).toBeDefined();
    expect(screen.getByText(/не гарантія/)).toBeDefined();
    expect(screen.getByText(/відсутність факту не означає відсутність навички/)).toBeDefined();
    expect(queryDelegate(GAPS_DESCRIPTION)).toBeNull();
  });

  test("блок «Делегувати агенту» уточнює прогалини: копіює промпт з номером вакансії", async () => {
    const { user } = await openGaps();
    const writeText = vi.spyOn(navigator.clipboard, "writeText");
    const block = await findDelegate(GAPS_DESCRIPTION);
    await user.click(block.getByRole("button", { name: "Копіювати промпт" }));
    expect(writeText).toHaveBeenCalledExactlyOnceWith(GAPS_PROMPT);
    expect(await block.findByText(COPIED)).toBeDefined();
  });

  test("блок «Делегувати агенту» є і коли всі прогалини закриті", async () => {
    await openGaps(GAPS.slice(1, 2));
    expect(queryDelegate(GAPS_DESCRIPTION)).not.toBeNull();
  });
});

describe("вкладка «Опис вакансії»", () => {
  test("повний текст як текст, без розмітки", async () => {
    const hostile = apiJob(1, { title: "Senior Backend Engineer", text: "Рядок 1\n\nРядок 2 <b>не жирний</b>" });
    const { user } = await open([hostile], [apiAnalysis(1)]);
    await user.click(await screen.findByRole("tab", { name: "Опис вакансії" }));
    const text = screen.getByText(/Рядок 1/);
    expect(text.textContent).toBe("Рядок 1\n\nРядок 2 <b>не жирний</b>");
    expect(text.className).toContain("whitespace-pre-wrap");
    expect(document.querySelector("main b")).toBeNull();
  });

  test("з аналізом опис живе лише у вкладці, а не двічі", async () => {
    await open([JOB], [apiAnalysis(1)]);
    await screen.findByText("Проходить фільтри профілю");
    expect(screen.queryByText(/Потрібен PostgreSQL/)).toBeNull();
    expect(screen.queryByRole("heading", { name: "Про роль" })).toBeNull();
  });
});

describe("клавіатура", () => {
  test("стрілки перемикають вкладки, фокус видимий і лишається на вкладці", async () => {
    const { user } = await open([JOB], [apiAnalysis(1)]);
    const first = await screen.findByRole("tab", { name: "Огляд" });
    first.focus();
    await user.keyboard("{ArrowRight}");
    const second = screen.getByRole("tab", { name: "Вимоги · 3" });
    expect(document.activeElement).toBe(second);
    expect(second.getAttribute("aria-selected")).toBe("true");
    expect(screen.getByRole("tabpanel", { name: "Вимоги · 3" })).toBeDefined();
    await user.keyboard("{End}");
    expect(screen.getByRole("tab", { name: "Опис вакансії" }).getAttribute("aria-selected")).toBe("true");
  });

  test("тріаж розкривається нативним details/summary", async () => {
    const { user } = await open([apiJob(1, { title: "Senior Backend Engineer", triage: apiTriage() })]);
    const summary = await screen.findByText("Попередній тріаж: 86/100 · Аналізувати");
    expect(summary.tagName).toBe("SUMMARY");
    const details = summary.closest("details") as HTMLDetailsElement;
    expect(details.open).toBe(false);
    await user.click(summary);
    expect(details.open).toBe(true);
  });
});

describe("тріаж окремо від аналізу", () => {
  test("лише тріаж: згорнутий блок, «Не оцінено» і порожній стан аналізу", async () => {
    await open([apiJob(1, { title: "Senior Backend Engineer", triage: apiTriage({ score: 64, verdict: "maybe", reason: "Потрібно уточнити формат" }) })]);
    expect(await screen.findByText("Повного аналізу ще немає")).toBeDefined();
    expect(score()).toBe("Не оцінено");
    const summary = screen.getByText("Попередній тріаж: 64/100 · Можливо");
    const details = summary.closest("details") as HTMLDetailsElement;
    expect(details.open).toBe(false);
    expect(within(details).getByText("Потрібно уточнити формат")).toBeDefined();
    expect(within(details).getByText(/окремий результат швидкого відбору, не повний аналіз/)).toBeDefined();
    expect(within(details).getByText(/Вердикт не приховує вакансію/)).toBeDefined();
  });

  test("тріаж агента: у блоці сказано, що оцінив агент", async () => {
    await open([apiJob(1, { title: "Senior Backend Engineer", triage: apiTriage({ source: "agent" }) })]);
    const details = (await screen.findByText("Попередній тріаж: 86/100 · Аналізувати")).closest("details") as HTMLDetailsElement;
    expect(within(details).getByText("Оцінив агент за профілем, підтвердженими фактами й вимогами з опису.")).toBeDefined();
    expect(within(details).queryByText(/Оцінив сервер/)).toBeNull();
  });

  test("тріаж правил: у блоці сказано, що оцінив сервер за ключовими словами, без агента", async () => {
    await open([apiJob(1, { title: "Senior Backend Engineer", triage: apiTriage({ score: 45, verdict: "maybe", source: "rules" }) })]);
    const details = (await screen.findByText("Попередній тріаж: 45/100 · Можливо")).closest("details") as HTMLDetailsElement;
    expect(within(details).getByText("Оцінив сервер за тими самими правилами — за ключовими словами, без агента.")).toBeDefined();
    expect(within(details).queryByText(/Оцінив агент/)).toBeNull();
  });

  test("повний аналіз і тріаж разом: тріаж лишається окремим і згорнутим", async () => {
    await open([apiJob(1, { title: "Senior Backend Engineer", triage: apiTriage({ score: 86 }) })], [apiAnalysis(1, { score: 78 })]);
    await waitFor(() => expect(score()).toBe("78%"));
    const details = screen.getByText("Попередній тріаж: 86/100 · Аналізувати").closest("details") as HTMLDetailsElement;
    expect(details.open).toBe(false);
  });

  test("нічого немає: «Не оцінено», порожній стан із блоком «Делегувати агенту», без блоку тріажу", async () => {
    await open([JOB]);
    expect(await screen.findByText("Повного аналізу ще немає")).toBeDefined();
    await findDelegate(ANALYSE);
    expect(queryDelegate(REANALYSE)).toBeNull();
    expect(score()).toBe("Не оцінено");
    expect(screen.getByText(NOTE)).toBeDefined();
    expect(screen.queryByText(/Попередній тріаж/)).toBeNull();
  });
});

describe("вакансія без тексту", () => {
  test("аналізувати нічого: нема кнопки запиту, є пояснення", async () => {
    const waiting = apiJob(1, { title: "Python Engineer", text: null, source: "linkedin_alert" });
    await open([waiting], [], "/vacancies/1", "Python Engineer");
    expect(await screen.findByText(/Аналіз неможливий без тексту опису/)).toBeDefined();
    expect(score()).toBe("Не оцінено");
    expect(queryDelegate(ANALYSE)).toBeNull();
    expect(queryDelegate(REANALYSE)).toBeNull();
    expect(screen.queryByRole("button", { name: "Підготувати запит для Claude" })).toBeNull();
    expect(screen.queryByText("Повного аналізу ще немає")).toBeNull();
  });
});

describe("завантаження й помилки", () => {
  test("поки аналіз вантажиться — скелетон, а вакансія вже видна", async () => {
    const backend = jobsBackend([JOB], [apiAnalysis(1)]);
    const gate = backend.holdAnalysis();
    renderClient("/vacancies/1", backend.fetchFn);
    await screen.findByRole("heading", { level: 1, name: "Senior Backend Engineer" });
    expect(screen.getByRole("status", { name: "Завантажуємо аналіз" })).toBeDefined();
    gate.release();
    await waitFor(() => expect(score()).toBe("78%"));
    expect(screen.queryByRole("status", { name: "Завантажуємо аналіз" })).toBeNull();
  });

  test("помилка аналізу: сповіщення з повтором, вакансія і опис лишаються", async () => {
    const backend = jobsBackend([JOB], [apiAnalysis(1)]);
    backend.failures.analysis = 1;
    renderClient("/vacancies/1", backend.fetchFn);
    const user = userEvent.setup();
    await screen.findByRole("heading", { level: 1, name: "Senior Backend Engineer" });
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Не вдалося завантажити аналіз.");
    expect(screen.getByText(/Потрібен PostgreSQL/)).toBeDefined();
    await user.click(within(alert).getByRole("button", { name: "Спробувати ще раз" }));
    await waitFor(() => expect(score()).toBe("78%"));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  test("повторне відкриття лише читає: жодного запиту, що запускає аналіз", async () => {
    const { backend, view } = await open([JOB], [apiAnalysis(1)]);
    await waitFor(() => expect(score()).toBe("78%"));
    await act(() => view.router.navigate("/vacancies"));
    await act(() => view.router.navigate("/vacancies/1"));
    await waitFor(() => expect(score()).toBe("78%"));
    expect(backend.requests.every((request) => request.startsWith("GET "))).toBe(true);
    expect(backend.bodies).toEqual([]);
    expect(backend.requests.filter((request) => request === "GET /api/jobs/1/analysis")).toHaveLength(2);
  });
});

describe("запит аналізу: «Делегувати агенту»", () => {
  async function prepare(jobs: ApiJob[], analyses: ApiAnalysis[] = []) {
    const opened = await open(jobs, analyses);
    const writeText = vi.spyOn(navigator.clipboard, "writeText");
    return { ...opened, writeText };
  }

  test("«Копіювати промпт» копіює текст запиту й підтверджує копіювання; старої кнопки й поля запиту нема", async () => {
    const { user, writeText } = await prepare([JOB]);
    const block = await findDelegate(ANALYSE);
    await user.click(block.getByRole("button", { name: "Копіювати промпт" }));
    expect(writeText).toHaveBeenCalledExactlyOnceWith("Analyse job #1 in joboffer");
    await waitFor(() => expect(block.getByRole("status").textContent).toBe(COPIED));
    expect(screen.queryByRole("button", { name: "Підготувати запит для Claude" })).toBeNull();
    expect(screen.queryByRole("textbox", { name: "Запит для Claude" })).toBeNull();
    expect(screen.queryByText(/Аналіз виконує Claude через joboffer/)).toBeNull();
  });

  test("з аналізом є лише блок повторного аналізу, без блоку першого", async () => {
    const { user, writeText } = await prepare([JOB], [apiAnalysis(1)]);
    const block = await findDelegate(REANALYSE);
    expect(queryDelegate(ANALYSE)).toBeNull();
    await user.click(block.getByRole("button", { name: "Копіювати промпт" }));
    expect(writeText).toHaveBeenCalledExactlyOnceWith("Analyse job #1 in joboffer");
  });

  test("«Копіювати промпт» працює з клавіатури (Enter і Space)", async () => {
    const { user, writeText } = await prepare([JOB]);
    const button = (await findDelegate(ANALYSE)).getByRole("button", { name: "Копіювати промпт" });
    button.focus();
    await user.keyboard("{Enter}");
    await user.keyboard(" ");
    expect(writeText).toHaveBeenCalledTimes(2);
  });

  test("не вдалося скопіювати — промпт розкрито на екрані для ручного копіювання", async () => {
    const { user, writeText } = await prepare([JOB]);
    writeText.mockRejectedValueOnce(new Error("denied"));
    const block = await findDelegate(ANALYSE);
    await user.click(block.getByRole("button", { name: "Копіювати промпт" }));
    await waitFor(() => expect(block.getByRole("status").textContent).toBe("Не вдалося скопіювати автоматично. Виділи текст промпту й скопіюй вручну."));
    expect(block.getByRole("region", { name: "Промпт" }).textContent).toContain("Analyse job #1 in joboffer");
  });

  test("запит не запускає аналіз: лише копіювання, жодного POST", async () => {
    const { backend, user } = await prepare([JOB]);
    const block = await findDelegate(ANALYSE);
    await user.click(block.getByRole("button", { name: "Копіювати промпт" }));
    expect(backend.bodies).toEqual([]);
    expect(backend.requests.every((request) => request.startsWith("GET "))).toBe(true);
  });
});

describe("крайні випадки", () => {
  test("аналіз без тексту вакансії: у вкладці «Опис вакансії» — «Опису ще нема»", async () => {
    const odd = apiJob(1, { title: "Senior Backend Engineer", text: null, needs_text: false });
    const { user } = await open([odd], [apiAnalysis(1)]);
    await user.click(await screen.findByRole("tab", { name: "Опис вакансії" }));
    expect(screen.getByText("Опису ще нема.")).toBeDefined();
  });

  test("перехід на іншу вакансію до відповіді аналізу не змішує результати", async () => {
    const jobs = [JOB, apiJob(2, { title: "Rust Developer", text: "Rust" })];
    const backend = jobsBackend(jobs, [apiAnalysis(1, { score: 78 }), apiAnalysis(2, { score: 41 })]);
    const gate = backend.holdAnalysis();
    const view = renderClient("/vacancies/1", backend.fetchFn);
    await screen.findByRole("heading", { level: 1, name: "Senior Backend Engineer" });
    await act(() => view.router.navigate("/vacancies/2"));
    await screen.findByRole("heading", { level: 1, name: "Rust Developer" });
    await act(async () => gate.release());
    await waitFor(() => expect(score()).toBe("41%"));
  });
});
