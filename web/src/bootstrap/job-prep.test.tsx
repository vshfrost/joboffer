/** Блок «Підготовка» в деталях вакансії: теми вакансії, готовність у заголовку, згортання, запити для Claude, завантаження й помилки. */
import { act, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { COPIED, findDelegate, queryDelegate } from "./delegateHarness";
import { apiAnalysis, apiVacancy, jobBlocksBackend, openJob, prepDetails, prepSummary } from "./jobBlocksHarness";
import { apiJob, apiKit, apiStep, apiTopic, doneStep } from "./prepBackend";

const REQUEST = "Prepare me for job #1 in joboffer";
const DELEGATE_PREP = "Агент запропонує теми підготовки на основі прогалин вакансії.";
const GAP = "Потрібно підтвердити практику Domain-Driven Design.";

// Тема 3 — 2 кроки з 5 (Вивчаю, 40%), тема 2 — 2 з 3 з практикою (Практика, 67%): готовність вакансії (40 + 67) / 2 ≈ 54%.
const TOPICS = [
  apiTopic(3, {
    title: "DDD у Symfony",
    jobs: [apiJob(2, { gap: "Чужа прогалина." }), apiJob(1, { gap: GAP })],
    steps: [doneStep(1), doneStep(2), apiStep(3, { kind: "practice" }), apiStep(4, { kind: "practice" }), apiStep(5, { kind: "check" })],
  }),
  apiTopic(2, {
    title: "Оптимізація запитів MySQL",
    jobs: [apiJob(1, { gap: "Бракує прикладу оптимізації SQL." })],
    steps: [doneStep(6), doneStep(7, { kind: "practice" }), apiStep(8, { kind: "check" })],
  }),
  apiTopic(9, { title: "Тема іншої вакансії", jobs: [apiJob(2)], steps: [apiStep(20)] }),
];

const STORAGE = Object.getOwnPropertyDescriptor(window, "sessionStorage") as PropertyDescriptor;

beforeEach(() => {
  window.sessionStorage.clear();
});

afterEach(() => {
  Object.defineProperty(window, "sessionStorage", STORAGE);
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

async function topicsList(): Promise<HTMLElement> {
  return screen.findByRole("list", { name: "Теми вакансії" });
}

async function rowOf(title: string): Promise<HTMLElement> {
  return within(await topicsList()).getByRole("link", { name: title }).closest("li") as HTMLElement;
}

describe("теми вакансії", () => {
  test("тема показує посилання на /prep/{n}, статус, кроки, відсоток і смугу прогресу", async () => {
    await openJob(jobBlocksBackend({ topics: TOPICS }));

    const ddd = within(await rowOf("DDD у Symfony"));
    expect(ddd.getByRole("link", { name: "DDD у Symfony" }).getAttribute("href")).toBe("/prep/3");
    expect(ddd.getByText("Вивчаю")).toBeDefined();
    expect(ddd.getByText("2/5 кроків")).toBeDefined();
    expect(ddd.getByText("40%")).toBeDefined();
    expect(ddd.getByRole("progressbar", { name: "DDD у Symfony" }).getAttribute("aria-valuenow")).toBe("40");
    const sql = within(await rowOf("Оптимізація запитів MySQL"));
    expect(sql.getByRole("link", { name: "Оптимізація запитів MySQL" }).getAttribute("href")).toBe("/prep/2");
    expect(sql.getByText("Практика")).toBeDefined();
    expect(sql.getByText("2/3 кроків")).toBeDefined();
    expect(sql.getByText("67%")).toBeDefined();
  });

  test("теми інших вакансій не показуються", async () => {
    await openJob(jobBlocksBackend({ topics: TOPICS }));

    const list = await topicsList();
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(within(list).queryByText("Тема іншої вакансії")).toBeNull();
  });

  test("прогалина розкривається й показує прогалину саме цієї вакансії", async () => {
    const { user } = await openJob(jobBlocksBackend({ topics: TOPICS }));

    const row = within(await rowOf("DDD у Symfony"));
    const gap = row.getByText("Прогалина", { selector: "summary" }).closest("details") as HTMLDetailsElement;
    expect(gap.open).toBe(false);
    await user.click(row.getByText("Прогалина", { selector: "summary" }));

    expect(gap.open).toBe(true);
    expect(within(gap).getByText(GAP)).toBeDefined();
    expect(within(gap).queryByText("Чужа прогалина.")).toBeNull();
  });
});

describe("готовність у заголовку", () => {
  test("теми є — готовність вакансії з відповіді сервера", async () => {
    await openJob(jobBlocksBackend({ topics: TOPICS }));

    const summary = await prepSummary();
    await waitFor(() => expect(summary.textContent).toBe("ПідготовкаГотовність 54%"));
  });

  test("готовність 0 % — це 0 %, а не тире", async () => {
    await openJob(jobBlocksBackend({ topics: [apiTopic(1, { title: "Без плану", jobs: [apiJob(1)] })] }));

    const summary = await prepSummary();
    await waitFor(() => expect(summary.textContent).toBe("ПідготовкаГотовність 0%"));
  });

  test("тем нема — «Готовність —», а не 0 %", async () => {
    await openJob(jobBlocksBackend());

    const summary = await prepSummary();
    await waitFor(() => expect(screen.queryByRole("status", { name: "Завантажуємо підготовку" })).toBeNull());
    expect(summary.textContent).toBe("ПідготовкаГотовність —");
    expect(summary.textContent).not.toContain("0%");
  });

  test("поки підготовку не завантажено, у заголовку лише назва", async () => {
    const backend = jobBlocksBackend({ topics: TOPICS });
    const hold = backend.hold("prep");
    await openJob(backend);

    expect((await prepSummary()).textContent).toBe("Підготовка");
    await act(async () => hold.release());
  });
});

describe("тем нема", () => {
  test("аналіз є — порожній стан із блоком «Делегувати агенту» і запитом «підготуй мене до вакансії N»", async () => {
    const { user } = await openJob(jobBlocksBackend());
    const writeText = vi.spyOn(navigator.clipboard, "writeText");

    expect(await screen.findByText("Тем ще немає")).toBeDefined();
    const block = await findDelegate(DELEGATE_PREP);
    await user.click(block.getByRole("button", { name: "Копіювати промпт" }));

    expect(writeText).toHaveBeenCalledWith(REQUEST);
    await waitFor(() => expect(block.getByRole("status").textContent).toBe(COPIED));
    expect(screen.queryByRole("button", { name: "Скопіювати запит для Claude" })).toBeNull();
    expect(screen.queryByText("Claude запропонує теми на основі прогалин вакансії.")).toBeNull();
    expect(screen.queryByText("Спершу аналіз")).toBeNull();
  });

  test("запит іншої вакансії містить її номер", async () => {
    const backend = jobBlocksBackend({ jobs: [apiVacancy(7)], analyses: [apiAnalysis(7)] });
    const { user } = await openJob(backend, 7);
    const writeText = vi.spyOn(navigator.clipboard, "writeText");

    const block = await findDelegate(DELEGATE_PREP);
    await user.click(block.getByRole("button", { name: "Копіювати промпт" }));

    expect(writeText).toHaveBeenCalledWith("Prepare me for job #7 in joboffer");
  });

  test("аналізу нема — «Спершу аналіз» без блоку запиту", async () => {
    await openJob(jobBlocksBackend({ analyses: [] }));

    expect(await screen.findByText("Спершу аналіз")).toBeDefined();
    expect(screen.queryByText("Тем ще немає")).toBeNull();
    expect(queryDelegate(DELEGATE_PREP)).toBeNull();
  });

  test("вакансія без тексту (аналіз неможливий) — «Спершу аналіз»", async () => {
    await openJob(jobBlocksBackend({ jobs: [apiVacancy(1, { text: null })], analyses: [] }));

    expect(await screen.findByText("Спершу аналіз")).toBeDefined();
    expect(queryDelegate(DELEGATE_PREP)).toBeNull();
  });

  test("теми є, а аналізу нема — теми показуються, «Спершу аналіз» ні", async () => {
    await openJob(jobBlocksBackend({ analyses: [], topics: TOPICS }));

    expect(await rowOf("DDD у Symfony")).toBeDefined();
    expect(screen.queryByText("Спершу аналіз")).toBeNull();
  });
});

describe("згортання", () => {
  test("початково розгорнуто: aria-expanded=true, теми видно", async () => {
    await openJob(jobBlocksBackend({ topics: TOPICS }));

    const summary = await prepSummary();
    expect(summary.getAttribute("aria-expanded")).toBe("true");
    expect((await prepDetails()).open).toBe(true);
  });

  test("клік по заголовку згортає, повторний — розгортає; aria-expanded змінюється", async () => {
    const { user } = await openJob(jobBlocksBackend({ topics: TOPICS }));
    const summary = await prepSummary();
    const details = await prepDetails();

    await user.click(summary);
    expect(summary.getAttribute("aria-expanded")).toBe("false");
    expect(details.open).toBe(false);
    expect(within(details).getByRole("list", { name: "Теми вакансії" })).toBeDefined();

    await user.click(summary);
    expect(summary.getAttribute("aria-expanded")).toBe("true");
    expect(details.open).toBe(true);
  });

  test("згорнутий стан показує назву й готовність", async () => {
    const { user } = await openJob(jobBlocksBackend({ topics: TOPICS }));
    const summary = await prepSummary();

    await user.click(summary);

    expect(summary.textContent).toBe("ПідготовкаГотовність 54%");
  });

  test("згорнутий стан без тем показує «Готовність —»", async () => {
    const { user } = await openJob(jobBlocksBackend());
    const summary = await prepSummary();
    await screen.findByText("Тем ще немає");

    await user.click(summary);

    expect(summary.getAttribute("aria-expanded")).toBe("false");
    expect(summary.textContent).toBe("ПідготовкаГотовність —");
  });

  test("Enter на заголовку згортає й розгортає", async () => {
    const { user } = await openJob(jobBlocksBackend({ topics: TOPICS }));
    const summary = await prepSummary();
    await act(async () => summary.focus());
    expect(document.activeElement).toBe(summary);

    await user.keyboard("{Enter}");
    expect(summary.getAttribute("aria-expanded")).toBe("false");
    await user.keyboard("{Enter}");
    expect(summary.getAttribute("aria-expanded")).toBe("true");
  });

  test("Space на заголовку згортає й розгортає", async () => {
    const { user } = await openJob(jobBlocksBackend({ topics: TOPICS }));
    const summary = await prepSummary();
    await act(async () => summary.focus());

    await user.keyboard(" ");
    expect(summary.getAttribute("aria-expanded")).toBe("false");
    expect((await prepDetails()).open).toBe(false);
    await user.keyboard(" ");
    expect(summary.getAttribute("aria-expanded")).toBe("true");
  });

  test("інша клавіша на заголовку його не згортає", async () => {
    const { user } = await openJob(jobBlocksBackend({ topics: TOPICS }));
    const summary = await prepSummary();
    await act(async () => summary.focus());

    await user.keyboard("x");

    expect(summary.getAttribute("aria-expanded")).toBe("true");
  });

  test("розкриття прогалини стан «Підготовки» не змінює", async () => {
    const { user } = await openJob(jobBlocksBackend({ topics: TOPICS }));
    const row = within(await rowOf("DDD у Symfony"));

    await user.click(row.getByText("Прогалина", { selector: "summary" }));

    expect((await prepSummary()).getAttribute("aria-expanded")).toBe("true");
  });

  test("розкриття розділів пакета не скидає згорнуту «Підготовку»", async () => {
    const { user } = await openJob(jobBlocksBackend({ topics: TOPICS, kits: [apiKit(1)] }));
    await user.click(await prepSummary());

    await user.click(await screen.findByText("Ймовірні питання", { selector: "summary strong" }));
    await user.click(screen.getByText("STAR-історії", { selector: "summary strong" }));

    expect((await prepSummary()).getAttribute("aria-expanded")).toBe("false");
    expect((await prepDetails()).open).toBe(false);
  });

  test("згорнутий стан переживає перехід на /prep/{n} і повернення", async () => {
    const { user, view } = await openJob(jobBlocksBackend({ topics: TOPICS }));
    await user.click(await prepSummary());

    await user.click(within(await topicsList()).getByRole("link", { name: "DDD у Symfony" }));
    await screen.findByRole("heading", { level: 1, name: "DDD у Symfony" });
    await act(() => view.router.navigate(-1));

    await screen.findByRole("heading", { level: 1, name: "Посада 1" });
    expect((await prepSummary()).getAttribute("aria-expanded")).toBe("false");
    expect((await prepDetails()).open).toBe(false);
  });

  test("розгорнутий стан теж переживає перехід і повернення", async () => {
    const { user, view } = await openJob(jobBlocksBackend({ topics: TOPICS }));
    await user.click(await prepSummary());
    await user.click(await prepSummary());

    await user.click(within(await topicsList()).getByRole("link", { name: "DDD у Symfony" }));
    await screen.findByRole("heading", { level: 1, name: "DDD у Symfony" });
    await act(() => view.router.navigate(-1));

    await screen.findByRole("heading", { level: 1, name: "Посада 1" });
    expect((await prepSummary()).getAttribute("aria-expanded")).toBe("true");
  });

  test("сховище недоступне — блок працює, початково розгорнутий", async () => {
    Object.defineProperty(window, "sessionStorage", {
      configurable: true,
      get() {
        throw new DOMException("Доступ до сховища заборонено", "SecurityError");
      },
    });
    const { user } = await openJob(jobBlocksBackend({ topics: TOPICS }));

    const summary = await prepSummary();
    expect(summary.getAttribute("aria-expanded")).toBe("true");
    expect(await rowOf("DDD у Symfony")).toBeDefined();
    await user.click(summary);
    expect(summary.getAttribute("aria-expanded")).toBe("false");
    await user.click(summary);
    expect(summary.getAttribute("aria-expanded")).toBe("true");
  });
});

describe("завантаження й помилки", () => {
  test("поки теми вантажаться — скелетон; потім теми", async () => {
    const backend = jobBlocksBackend({ topics: TOPICS });
    const hold = backend.hold("prep");
    await openJob(backend);

    expect(await screen.findByRole("status", { name: "Завантажуємо підготовку" })).toBeDefined();
    await act(async () => hold.release());

    expect(await rowOf("DDD у Symfony")).toBeDefined();
    expect(screen.queryByRole("status", { name: "Завантажуємо підготовку" })).toBeNull();
  });

  test("помилка мережі — повідомлення й повтор, що завантажує теми", async () => {
    const backend = jobBlocksBackend({ topics: TOPICS });
    backend.failures.prep = 1;
    const { user } = await openJob(backend);

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("Не вдалося завантажити підготовку.")).toBeDefined();
    await user.click(within(alert).getByRole("button", { name: "Спробувати підготовку ще раз" }));

    expect(await rowOf("DDD у Symfony")).toBeDefined();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(backend.prep.requests.filter((request) => request === "GET /api/jobs/1/prep")).toHaveLength(1);
  });

  test("помилка підготовки не чіпає пакет і решту сторінки", async () => {
    const backend = jobBlocksBackend({ topics: TOPICS, kits: [apiKit(1)] });
    backend.failures.prep = 1;
    await openJob(backend);

    await screen.findByText("Не вдалося завантажити підготовку.");
    expect(await screen.findByText("Пакет до інтерв’ю", { selector: "h2" })).toBeDefined();
    expect(screen.getByText("v2")).toBeDefined();
    expect(screen.getByRole("heading", { level: 2, name: "Документи" })).toBeDefined();
    expect(screen.getByRole("heading", { level: 2, name: "Відповідність профілю" })).toBeDefined();
    expect(screen.getAllByRole("alert")).toHaveLength(1);
  });
});

describe("розкладка", () => {
  test("375 px: сторінка не ширша за екран", async () => {
    await openJob(jobBlocksBackend({ topics: TOPICS }), 1, "mobile");
    await rowOf("DDD у Symfony");

    const root = document.documentElement;
    expect(root.scrollWidth).toBe(root.clientWidth);
    const main = screen.getByRole("main");
    expect(main.scrollWidth).toBe(main.clientWidth);
  });

  test("touch-цілі від 44 px: заголовок, посилання теми й «Прогалина»", async () => {
    await openJob(jobBlocksBackend({ topics: TOPICS }), 1, "mobile");

    expect((await prepSummary()).className).toContain("pointer-coarse:min-h-11");
    const row = within(await rowOf("DDD у Symfony"));
    expect(row.getByRole("link", { name: "DDD у Symfony" }).className).toContain("pointer-coarse:min-h-11");
    expect(row.getByText("Прогалина", { selector: "summary" }).className).toContain("pointer-coarse:min-h-11");
  });

  test("довгі назви теми й прогалини переносяться, а не розпирають блок", async () => {
    const title = "Дуже-дуже-довга-назва-теми-яка-мусить-переноситись-а-не-розпирати-сторінку-вбік-0123456789";
    const gap = "Довга-прогалина-без-пробілів-яка-мусить-переноситись-а-не-розпирати-сторінку-вбік-0123456789";
    await openJob(jobBlocksBackend({ topics: [apiTopic(1, { title, jobs: [apiJob(1, { gap })], steps: [apiStep(1)] })] }), 1, "mobile");

    const row = await rowOf(title);
    expect(within(row).getByRole("link", { name: title }).className).toContain("[overflow-wrap:anywhere]");
    expect(within(row).getByText(gap).className).toContain("[overflow-wrap:anywhere]");
  });
});
