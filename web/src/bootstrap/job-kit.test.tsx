/** Блок «Пакет до інтерв'ю» в деталях вакансії: остання версія, три розкривні розділи, порожній стан, завантаження й помилки. */
import { act, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import { COPIED, findDelegate, queryDelegate } from "./delegateHarness";
import { jobBlocksBackend, kitSection, openJob, prepDetails } from "./jobBlocksHarness";
import { apiJob, apiKit, apiStep, apiTopic, doneStep } from "./prepBackend";

const REQUEST = "Prepare an interview kit for job #1 in joboffer";
const DELEGATE_KIT = "Агент складе питання до інтерв’ю, STAR-історії й питання до компанії.";

const KIT = apiKit(1, {
  version: 2,
  created_on: "2026-10-27",
  questions: [
    { kind: "technical", question: "How do you draw aggregate boundaries?", topic_id: 3 },
    { kind: "behavioral", question: "Tell me about a feature you owned from idea to production.", topic_id: null },
  ],
  stories: [
    { title: "Запуск сервісу", situation: "Команда готувала новий сервіс.", task: "Довести його до production.", action: "Узгодив критерії готовності.", result: "Сервіс запустили.", fact_ids: [12, 18] },
    { title: "Повільний запит", situation: "API сповільнився після росту даних.", task: "Знайти причину.", action: "Дослідив план виконання.", result: "Усунув вузьке місце.", fact_ids: [23] },
  ],
  company_questions: ["What are the biggest technical challenges for the team?", "How does the team make architecture decisions?"],
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("заголовок пакета", () => {
  test("«Пакет до інтерв'ю», номер версії й дата створення як остання версія", async () => {
    await openJob(jobBlocksBackend({ kits: [KIT] }));

    expect(await screen.findByRole("heading", { level: 2, name: "Пакет до інтерв’ю" })).toBeDefined();
    expect(await screen.findByText("v2")).toBeDefined();
    expect(await screen.findByText("2026-10-27 · остання версія")).toBeDefined();
  });

  test("інша версія й дата — з відповіді сервера", async () => {
    await openJob(jobBlocksBackend({ kits: [apiKit(1, { version: 5, created_on: "2026-11-02" })] }));

    expect(await screen.findByText("v5")).toBeDefined();
    expect(screen.getByText("2026-11-02 · остання версія")).toBeDefined();
  });
});

describe("три розділи", () => {
  test("розділи йдуть у порядку: питання, STAR-історії, питання до компанії; у кожного лічильник", async () => {
    await openJob(jobBlocksBackend({ kits: [KIT] }));

    await screen.findByText("v2");
    const titles = screen.getAllByText(/^(Ймовірні питання|STAR-історії|Питання до компанії)$/, { selector: "summary strong" }).map((title) => title.textContent);
    expect(titles).toEqual(["Ймовірні питання", "STAR-історії", "Питання до компанії"]);
    expect(within(kitSection("Ймовірні питання")).getAllByText("2", { selector: "summary .sr-count" })).toHaveLength(1);
    expect(within(kitSection("STAR-історії")).getAllByText("2", { selector: "summary .sr-count" })).toHaveLength(1);
    expect(within(kitSection("Питання до компанії")).getAllByText("2", { selector: "summary .sr-count" })).toHaveLength(1);
  });

  test("початково розкриті лише ймовірні питання", async () => {
    await openJob(jobBlocksBackend({ kits: [KIT] }));
    await screen.findByText("v2");

    expect(kitSection("Ймовірні питання").open).toBe(true);
    expect(kitSection("STAR-історії").open).toBe(false);
    expect(kitSection("Питання до компанії").open).toBe(false);
  });

  test("розділи розкриваються й згортаються окремо один від одного", async () => {
    const { user } = await openJob(jobBlocksBackend({ kits: [KIT] }));
    await screen.findByText("v2");

    await user.click(screen.getByText("STAR-історії", { selector: "summary strong" }));
    expect([kitSection("Ймовірні питання").open, kitSection("STAR-історії").open, kitSection("Питання до компанії").open]).toEqual([true, true, false]);

    await user.click(screen.getByText("Ймовірні питання", { selector: "summary strong" }));
    expect([kitSection("Ймовірні питання").open, kitSection("STAR-історії").open, kitSection("Питання до компанії").open]).toEqual([false, true, false]);

    await user.click(screen.getByText("Питання до компанії", { selector: "summary strong" }));
    expect([kitSection("Ймовірні питання").open, kitSection("STAR-історії").open, kitSection("Питання до компанії").open]).toEqual([false, true, true]);
  });
});

describe("ймовірні питання", () => {
  test("питання показує вид українською й текст питання", async () => {
    await openJob(jobBlocksBackend({ kits: [KIT] }));
    await screen.findByText("v2");

    const items = within(kitSection("Ймовірні питання")).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(within(items[0] as HTMLElement).getByText("Технічне")).toBeDefined();
    expect(within(items[0] as HTMLElement).getByText("How do you draw aggregate boundaries?")).toBeDefined();
    expect(within(items[1] as HTMLElement).getByText("Поведінкове")).toBeDefined();
    expect(within(items[1] as HTMLElement).getByText("Tell me about a feature you owned from idea to production.")).toBeDefined();
  });

  test("питання з темою має посилання на /prep/{topicId}", async () => {
    await openJob(jobBlocksBackend({ kits: [KIT] }));
    await screen.findByText("v2");

    const items = within(kitSection("Ймовірні питання")).getAllByRole("listitem");
    expect(within(items[0] as HTMLElement).getByRole("link", { name: "Тема #3" }).getAttribute("href")).toBe("/prep/3");
  });

  test("питання без теми — без посилання", async () => {
    await openJob(jobBlocksBackend({ kits: [KIT] }));
    await screen.findByText("v2");

    const items = within(kitSection("Ймовірні питання")).getAllByRole("listitem");
    expect(within(items[1] as HTMLElement).queryByRole("link")).toBeNull();
  });
});

describe("STAR-історії", () => {
  test("кожна історія розкривна: першу відкрито, решту ні", async () => {
    const { user } = await openJob(jobBlocksBackend({ kits: [KIT] }));
    await screen.findByText("v2");
    await user.click(screen.getByText("STAR-історії", { selector: "summary strong" }));

    const first = screen.getByText("Запуск сервісу", { selector: "summary strong" }).closest("details") as HTMLDetailsElement;
    const second = screen.getByText("Повільний запит", { selector: "summary strong" }).closest("details") as HTMLDetailsElement;
    expect([first.open, second.open]).toEqual([true, false]);
    await user.click(screen.getByText("Повільний запит", { selector: "summary strong" }));
    expect([first.open, second.open]).toEqual([true, true]);
  });

  test("історія показує S, T, A, R з підписами й текстами", async () => {
    await openJob(jobBlocksBackend({ kits: [KIT] }));
    await screen.findByText("v2");
    const story = within(screen.getByText("Запуск сервісу", { selector: "summary strong" }).closest("details") as HTMLElement);

    for (const [letter, label, text] of [
      ["S", "Ситуація", "Команда готувала новий сервіс."],
      ["T", "Завдання", "Довести його до production."],
      ["A", "Дії", "Узгодив критерії готовності."],
      ["R", "Результат", "Сервіс запустили."],
    ] as const) {
      expect(story.getByText(letter, { selector: "strong" })).toBeDefined();
      const part = story.getByText(label).parentElement as HTMLElement;
      expect(within(part).getByText(text)).toBeDefined();
    }
  });

  test("факти історії — бейджі #id", async () => {
    await openJob(jobBlocksBackend({ kits: [KIT] }));
    await screen.findByText("v2");
    const story = within(screen.getByText("Запуск сервісу", { selector: "summary strong" }).closest("details") as HTMLElement);

    expect(story.getByText("Підтверджені факти")).toBeDefined();
    expect(story.getByText("#12")).toBeDefined();
    expect(story.getByText("#18")).toBeDefined();
    expect(story.queryByText("#23")).toBeNull();
  });
});

describe("питання до компанії", () => {
  test("перелік питань за порядком", async () => {
    await openJob(jobBlocksBackend({ kits: [KIT] }));
    await screen.findByText("v2");

    const items = within(kitSection("Питання до компанії")).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(within(items[0] as HTMLElement).getByText("1.")).toBeDefined();
    expect(within(items[0] as HTMLElement).getByText("What are the biggest technical challenges for the team?")).toBeDefined();
    expect(within(items[1] as HTMLElement).getByText("2.")).toBeDefined();
    expect(within(items[1] as HTMLElement).getByText("How does the team make architecture decisions?")).toBeDefined();
  });
});

describe("пакета ще немає", () => {
  test("404 — порожній стан і блок «Делегувати агенту» з запитом «пакет до інтерв'ю для вакансії N»", async () => {
    const { user } = await openJob(jobBlocksBackend());
    const writeText = vi.spyOn(navigator.clipboard, "writeText");

    expect(await screen.findByText("Пакета ще немає")).toBeDefined();
    expect(screen.getByRole("heading", { level: 2, name: "Пакет до інтерв’ю" })).toBeDefined();
    const block = await findDelegate(DELEGATE_KIT, await screen.findByRole("region", { name: "Пакет до інтерв’ю" }));
    await user.click(block.getByRole("button", { name: "Копіювати промпт" }));

    expect(writeText).toHaveBeenCalledWith(REQUEST);
    await waitFor(() => expect(block.getByRole("status").textContent).toBe(COPIED));
    expect(screen.queryByRole("button", { name: "Скопіювати запит на пакет" })).toBeNull();
    expect(screen.queryByText("Попроси Claude скласти питання, STAR-історії й питання до компанії.")).toBeNull();
    expect(screen.queryByText("Ймовірні питання")).toBeNull();
  });

  test("пакет є — блоку запиту нема", async () => {
    await openJob(jobBlocksBackend({ kits: [KIT] }));

    expect(await screen.findByText("v2")).toBeDefined();
    expect(queryDelegate(DELEGATE_KIT)).toBeNull();
  });
});

describe("аналіз не потрібен", () => {
  test("пакет є, аналізу нема — пакет показано", async () => {
    await openJob(jobBlocksBackend({ analyses: [], kits: [KIT] }));

    expect(await screen.findByText("v2")).toBeDefined();
    expect(kitSection("Ймовірні питання").open).toBe(true);
    expect(screen.queryByText("Пакета ще немає")).toBeNull();
  });
});

describe("безпечний вивід", () => {
  test("HTML у тексті питань, історій і питань до компанії виводиться як текст", async () => {
    const html = '<img src=x onerror="alert(1)"> <b>жирний</b>';
    const kit = apiKit(1, {
      questions: [{ kind: "technical", question: `Питання ${html}`, topic_id: null }],
      stories: [{ title: `Історія ${html}`, situation: `S ${html}`, task: `T ${html}`, action: `A ${html}`, result: `R ${html}`, fact_ids: [] }],
      company_questions: [`Компанія ${html}`],
    });
    const { user } = await openJob(jobBlocksBackend({ kits: [kit] }));
    await screen.findByText("v2");
    await user.click(screen.getByText("Питання до компанії", { selector: "summary strong" }));

    expect(screen.getByText(`Питання ${html}`)).toBeDefined();
    expect(screen.getByText(`Історія ${html}`, { selector: "summary strong" })).toBeDefined();
    expect(screen.getByText(`Компанія ${html}`, { exact: false })).toBeDefined();
    const block = screen.getByRole("heading", { level: 2, name: "Пакет до інтерв’ю" }).closest("section") as HTMLElement;
    expect(block.querySelector("img, b")).toBeNull();
  });

  test("answer_points з відповіді сервера не показуються", async () => {
    const kit = apiKit(1, { questions: [{ kind: "technical", question: "Питання з підказкою", topic_id: null, answer_points: ["Секретна підказка відповіді"] } as never] });
    await openJob(jobBlocksBackend({ kits: [kit] }));

    expect(await screen.findByText("Питання з підказкою")).toBeDefined();
    expect(screen.queryByText(/Секретна підказка/)).toBeNull();
  });
});

describe("завантаження й помилки", () => {
  test("поки пакет вантажиться — скелетон; потім пакет", async () => {
    const backend = jobBlocksBackend({ kits: [KIT] });
    const hold = backend.hold("kit");
    await openJob(backend);

    expect(await screen.findByRole("status", { name: "Завантажуємо пакет до інтерв’ю" })).toBeDefined();
    await act(async () => hold.release());

    expect(await screen.findByText("v2")).toBeDefined();
    expect(screen.queryByRole("status", { name: "Завантажуємо пакет до інтерв’ю" })).toBeNull();
  });

  test("помилка мережі — повідомлення й повтор, що завантажує пакет", async () => {
    const backend = jobBlocksBackend({ kits: [KIT] });
    backend.failures.kit = 1;
    const { user } = await openJob(backend);

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("Не вдалося завантажити пакет до інтерв’ю.")).toBeDefined();
    expect(screen.queryByText("Пакета ще немає")).toBeNull();
    await user.click(within(alert).getByRole("button", { name: "Спробувати пакет ще раз" }));

    expect(await screen.findByText("v2")).toBeDefined();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  test("помилка пакета не чіпає підготовку й решту сторінки", async () => {
    const topics = [apiTopic(3, { title: "DDD у Symfony", jobs: [apiJob(1)], steps: [doneStep(1), apiStep(2)] })];
    const backend = jobBlocksBackend({ topics, kits: [KIT] });
    backend.failures.kit = 1;
    await openJob(backend);

    await screen.findByText("Не вдалося завантажити пакет до інтерв’ю.");
    expect(await screen.findByRole("link", { name: "DDD у Symfony" })).toBeDefined();
    expect((await prepDetails()).open).toBe(true);
    expect(screen.getByRole("heading", { level: 2, name: "Документи" })).toBeDefined();
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    await waitFor(() => expect(screen.queryByRole("status", { name: "Завантажуємо підготовку" })).toBeNull());
  });
});

describe("розкладка", () => {
  test("375 px: сторінка не ширша за екран", async () => {
    await openJob(jobBlocksBackend({ kits: [KIT] }), 1, "mobile");
    await screen.findByText("v2");

    const root = document.documentElement;
    expect(root.scrollWidth).toBe(root.clientWidth);
    const main = screen.getByRole("main");
    expect(main.scrollWidth).toBe(main.clientWidth);
  });

  test("touch-цілі від 44 px: заголовки розділів, історій і посилання теми", async () => {
    await openJob(jobBlocksBackend({ kits: [KIT] }), 1, "mobile");
    await screen.findByText("v2");

    for (const title of ["Ймовірні питання", "STAR-історії", "Питання до компанії"]) {
      expect(screen.getByText(title, { selector: "summary strong" }).closest("summary")?.className).toContain("pointer-coarse:min-h-11");
    }
    expect(screen.getByText("Запуск сервісу", { selector: "summary strong" }).closest("summary")?.className).toContain("pointer-coarse:min-h-11");
    expect(screen.getByRole("link", { name: "Тема #3" }).className).toContain("pointer-coarse:min-h-11");
  });

  test("довгі тексти переносяться, а не розпирають блок", async () => {
    const long = "Дуже-дуже-довгий-текст-без-пробілів-який-мусить-переноситись-а-не-розпирати-сторінку-вбік-0123456789";
    const kit = apiKit(1, {
      questions: [{ kind: "technical", question: `Q-${long}`, topic_id: null }],
      stories: [{ title: `T-${long}`, situation: `S-${long}`, task: "t", action: "a", result: "r", fact_ids: [] }],
      company_questions: [`C-${long}`],
    });
    await openJob(jobBlocksBackend({ kits: [kit] }), 1, "mobile");
    await screen.findByText("v2");

    for (const text of [`Q-${long}`, `T-${long}`, `S-${long}`, `C-${long}`]) {
      expect(screen.getByText(text).className).toContain("[overflow-wrap:anywhere]");
    }
  });
});
