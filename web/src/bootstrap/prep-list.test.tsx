/** «Підготовка» `/prep`: реєстр тем за пріоритетом, рядок квізу, порожній стан, завантаження й помилки. */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { COPIED, delegateBlocks, findDelegate } from "./delegateHarness";
import { apiJob, apiStep, apiTopic, doneStep, prepBackend, problem } from "./prepBackend";
import { openPrep, rowOf, topicList, topicTitles } from "./prepHarness";
import { json, renderClient } from "./testClient";
import { setViewport } from "./viewport";

const QUIZ = "Агент проведе квіз на сьогодні з усіх тем.";
const TOPICS_REQUEST = "Агент запропонує теми підготовки на основі прогалин твоїх вакансій.";

// Порядок у відповіді сервера — за пріоритетом, а не за номером: веб його не змінює.
const TOPICS = [
  apiTopic(3, {
    title: "DDD у Symfony",
    kind: "tech",
    deadline: "2026-11-03",
    jobs: [apiJob(24, { company: "Northstar", score: 86 }), apiJob(31, { company: "Acme", score: 79 })],
    steps: [
      doneStep(1, { minutes: 45 }),
      doneStep(2, { minutes: 60 }),
      apiStep(3, { kind: "practice", minutes: 120 }),
      apiStep(4, { kind: "practice", minutes: 90 }),
      apiStep(5, { kind: "check", minutes: 30 }),
    ],
    quiz: { total: 10, due: 4 },
  }),
  apiTopic(1, {
    title: "Оптимізація запитів MySQL",
    deadline: "2026-11-05",
    steps: [doneStep(6), doneStep(7, { kind: "practice" }), apiStep(8, { kind: "check", minutes: 30 })],
    quiz: { total: 8, due: 3 },
  }),
  apiTopic(2, { title: "System design: надійний backend", steps: [apiStep(9, { minutes: 45 }), apiStep(10, { kind: "practice", minutes: 90 })] }),
  apiTopic(5, {
    title: "STAR: відповідальність за результат",
    kind: "behavioral",
    steps: [doneStep(11, { minutes: 15 }), apiStep(12, { minutes: 30 }), apiStep(13, { minutes: 30 })],
    ready: true,
    quiz: { total: 10, due: 2 },
  }),
  apiTopic(4, { title: "Домен workforce management", kind: "domain", jobs: [apiJob(31, { title: null, company: null, score: 79 })] }),
];

const location = () => screen.getByTestId("location").textContent;

describe("сторінка", () => {
  test("заголовок, опис і назва вкладки браузера", async () => {
    await openPrep(prepBackend({ topics: TOPICS }));

    expect(screen.getByText("Теми закривають прогалини вакансій. Вище — потрібніші вакансіям із кращим скором.")).toBeDefined();
    expect(document.title).toBe("Підготовка · joboffer");
  });

  test("«Підготовка» у навігації веде на справжню сторінку, а не на «Розділ ще в розробці»", async () => {
    setViewport("desktop");
    const backend = prepBackend({ topics: TOPICS });
    renderClient("/vacancies", backend.fetchFn);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("link", { name: "Підготовка" }));

    expect(await screen.findByLabelText("Список тем")).toBeDefined();
    expect(screen.queryByText("Розділ ще в розробці")).toBeNull();
    expect(location()).toBe("/prep");
  });

  test("поки теми вантажаться — статус зі скелетоном, потім реєстр", async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const backend = prepBackend({ topics: TOPICS }, { topics: () => gate.then(() => json(200, { topics: [], quiz: { total: 0, due: 0 } })) });
    await openPrep(backend, "/prep", "desktop", false);

    expect(screen.getByRole("status", { name: "Завантажуємо теми" })).toBeDefined();
    release();
    expect(await screen.findByRole("heading", { level: 2, name: "Тем ще немає" })).toBeDefined();
    expect(screen.queryByRole("status", { name: "Завантажуємо теми" })).toBeNull();
  });
});

describe("реєстр", () => {
  test("теми — у порядку сервера (за пріоритетом), без пересортування", async () => {
    await openPrep(prepBackend({ topics: TOPICS }));

    expect(await topicTitles()).toEqual([
      "DDD у Symfony",
      "Оптимізація запитів MySQL",
      "System design: надійний backend",
      "STAR: відповідальність за результат",
      "Домен workforce management",
    ]);
  });

  test("назва теми веде на її сторінку", async () => {
    await openPrep(prepBackend({ topics: TOPICS }));

    expect(within(await rowOf("DDD у Symfony")).getByRole("link", { name: "DDD у Symfony" }).getAttribute("href")).toBe("/prep/3");
    expect(within(await rowOf("Домен workforce management")).getByRole("link", { name: "Домен workforce management" }).getAttribute("href")).toBe("/prep/4");
  });

  test.each([
    ["DDD у Symfony", "Вивчаю"],
    ["Оптимізація запитів MySQL", "Практика"],
    ["System design: надійний backend", "Заплановано"],
    ["STAR: відповідальність за результат", "Готово"],
    ["Домен workforce management", "Без плану"],
  ])("«%s» має бейдж статусу «%s»", async (title, badge) => {
    await openPrep(prepBackend({ topics: TOPICS }));

    expect(within(await rowOf(title)).getByText(badge)).toBeDefined();
  });

  test.each([
    ["DDD у Symfony", "Технічна"],
    ["STAR: відповідальність за результат", "Поведінкова"],
    ["Домен workforce management", "Доменна"],
  ])("«%s» — вид «%s»", async (title, kind) => {
    await openPrep(prepBackend({ topics: TOPICS }));

    expect(within(await rowOf(title)).getByText(kind)).toBeDefined();
  });

  test("прогрес: відсоток, виконано з усіх кроків і «Лишилось ~N хв» за невиконаними кроками", async () => {
    await openPrep(prepBackend({ topics: TOPICS }));

    const row = within(await rowOf("DDD у Symfony"));
    expect(row.getByText("40%")).toBeDefined();
    expect(row.getByText(/2\/5/)).toBeDefined();
    expect(row.getByText("Лишилось ~240 хв")).toBeDefined();
    const bar = row.getByRole("progressbar", { name: "DDD у Symfony" });
    expect(bar.getAttribute("aria-valuenow")).toBe("40");
    expect(bar.getAttribute("aria-valuemin")).toBe("0");
    expect(bar.getAttribute("aria-valuemax")).toBe("100");
  });

  test("позначена готовою тема показує 100 % при невиконаних кроках", async () => {
    await openPrep(prepBackend({ topics: TOPICS }));

    const row = within(await rowOf("STAR: відповідальність за результат"));
    expect(row.getByText("100%")).toBeDefined();
    expect(row.getByText(/1\/3/)).toBeDefined();
    expect(row.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("100");
  });

  test("тема без плану: 0 %, 0/0 і «Плану ще немає» замість нуля хвилин", async () => {
    await openPrep(prepBackend({ topics: TOPICS }));

    const row = within(await rowOf("Домен workforce management"));
    expect(row.getByText("0%")).toBeDefined();
    expect(row.getByText(/0\/0/)).toBeDefined();
    expect(row.getByText("Плану ще немає")).toBeDefined();
    expect(row.queryByText(/Лишилось/)).toBeNull();
  });

  test("дедлайн — день, без дедлайну — «—»", async () => {
    await openPrep(prepBackend({ topics: TOPICS }));

    expect(within(await rowOf("Оптимізація запитів MySQL")).getByText("2026-11-05")).toBeDefined();
    expect(within(await rowOf("System design: надійний backend")).getByText("—")).toBeDefined();
  });

  test("вакансії теми — посилання зі скором на сторінку вакансії", async () => {
    await openPrep(prepBackend({ topics: TOPICS }));

    const row = within(await rowOf("DDD у Symfony"));
    expect(row.getByRole("link", { name: "Northstar 86" }).getAttribute("href")).toBe("/vacancies/24");
    expect(row.getByRole("link", { name: "Acme 79" }).getAttribute("href")).toBe("/vacancies/31");
  });

  test("вакансія без назви й компанії підписана номером", async () => {
    await openPrep(prepBackend({ topics: TOPICS }));

    expect(within(await rowOf("Домен workforce management")).getByRole("link", { name: "Вакансія #31 79" }).getAttribute("href")).toBe("/vacancies/31");
  });
});

describe("квіз", () => {
  test("рядок «Квіз: на повторення сьогодні N (усього M)» — загальні лічильники по всіх темах", async () => {
    await openPrep(prepBackend({ topics: TOPICS }));

    expect((await screen.findByRole("region", { name: "Квіз" })).textContent).toContain("Квіз: на повторення сьогодні 9 (усього 28)");
  });

  test("є що повторювати — блок «Делегувати агенту» в області «Квіз» копіює запит провести квіз на сьогодні й підтверджує це", async () => {
    await openPrep(prepBackend({ topics: TOPICS }));
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, "writeText");

    const block = await findDelegate(QUIZ, await screen.findByRole("region", { name: "Квіз" }));
    await user.click(block.getByRole("button", { name: "Копіювати промпт" }));

    expect(writeText).toHaveBeenCalledExactlyOnceWith("Run today's quiz in joboffer");
    await waitFor(() => expect(block.getByRole("status").textContent).toBe(COPIED));
    expect(screen.queryByRole("button", { name: "Квіз на сьогодні" })).toBeNull();
    expect(delegateBlocks()).toHaveLength(1);
  });

  test("нічого повторювати — блоку нема, а рядок показує нулі", async () => {
    await openPrep(prepBackend({ topics: [apiTopic(1, { title: "Тема", quiz: { total: 5, due: 0 } })] }));

    expect((await screen.findByRole("region", { name: "Квіз" })).textContent).toContain("Квіз: на повторення сьогодні 0 (усього 5)");
    expect(delegateBlocks()).toHaveLength(0);
    expect(screen.queryByRole("button", { name: "Квіз на сьогодні" })).toBeNull();
  });
});

describe("порожній стан", () => {
  test("без тем: підказка й блок «Делегувати агенту», що копіює запит запропонувати теми", async () => {
    await openPrep(prepBackend());
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, "writeText");

    expect(await screen.findByRole("heading", { level: 2, name: "Тем ще немає" })).toBeDefined();
    const block = await findDelegate(TOPICS_REQUEST);
    await user.click(block.getByRole("button", { name: "Копіювати промпт" }));

    expect(writeText).toHaveBeenCalledExactlyOnceWith("Suggest prep topics based on the gaps in my jobs in joboffer");
    expect(screen.queryByLabelText("Список тем")).toBeNull();
    expect(screen.queryByRole("button", { name: "Скопіювати запит для Claude" })).toBeNull();
    expect(screen.queryByText("Claude запропонує теми на основі прогалин вакансій.")).toBeNull();
  });
});

describe("помилки", () => {
  test("мережа недоступна: повідомлення про помилку й «Спробувати ще раз», що перезавантажує реєстр", async () => {
    const user = userEvent.setup();
    let fail = true;
    const backend = prepBackend({ topics: TOPICS }, { topics: () => (fail ? problem(500, "internal", "Збій") : undefined) });
    await openPrep(backend);

    expect((await screen.findByRole("alert")).textContent).toContain("Не вдалося завантажити теми");
    expect(screen.getByText("Перевір з’єднання й повтори спробу.")).toBeDefined();
    expect(screen.queryByLabelText("Список тем")).toBeNull();
    fail = false;
    await user.click(screen.getByRole("button", { name: "Спробувати ще раз" }));

    expect(await topicTitles()).toHaveLength(5);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(backend.requests.filter((request) => request === "GET /api/prep/topics")).toHaveLength(2);
  });

  test("збій самого запиту (fetch відхилено) — та сама помилка з повтором", async () => {
    const backend = prepBackend({ topics: TOPICS });
    const original = backend.fetchFn;
    backend.fetchFn = vi.fn<typeof fetch>((input, init) => (String(input).startsWith("/api/prep") ? Promise.reject(new TypeError("network")) : original(input, init)));
    await openPrep(backend);

    expect((await screen.findByRole("alert")).textContent).toContain("Не вдалося завантажити теми");
    expect(screen.getByRole("button", { name: "Спробувати ще раз" })).toBeDefined();
  });

  test("сесія завершилась (401): підказка увійти знову, без повтору", async () => {
    await openPrep(prepBackend({ topics: TOPICS }, { topics: () => problem(401, "not_authenticated", "Потрібен вхід") }));

    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("Сесія завершилась. Увійди знову, щоб побачити теми."));
    expect(screen.queryByRole("button", { name: "Спробувати ще раз" })).toBeNull();
  });
});

describe("широкий екран", () => {
  test("реєстр — таблиця із заголовками стовпців, без списку карток", async () => {
    await openPrep(prepBackend({ topics: TOPICS }), "/prep", "desktop");

    const table = await topicList();
    expect(table.tagName).toBe("TABLE");
    expect(within(table).getAllByRole("columnheader").map((header) => header.textContent)).toEqual(["Тема · за пріоритетом", "Прогрес", "Дедлайн", "Вакансії · скор"]);
    expect(screen.getAllByLabelText("Список тем")).toHaveLength(1);
  });
});

describe("вузький екран (375 px)", () => {
  test("реєстр — список карток із тими самими даними, таблиці в DOM нема", async () => {
    await openPrep(prepBackend({ topics: TOPICS }), "/prep", "mobile");

    const list = await topicList();
    expect(list.tagName).toBe("UL");
    expect(screen.queryByRole("table")).toBeNull();
    expect(within(list).getAllByRole("listitem")).toHaveLength(5);
    expect(await topicTitles()).toHaveLength(5);
    const card = within(await rowOf("DDD у Symfony"));
    expect(card.getByText("Вивчаю")).toBeDefined();
    expect(card.getByText("Технічна")).toBeDefined();
    expect(card.getByText("40%")).toBeDefined();
    expect(card.getByText("Лишилось ~240 хв")).toBeDefined();
    expect(card.getByText(/Дедлайн/).textContent).toContain("2026-11-03");
    expect(card.getByRole("link", { name: "Northstar 86" }).getAttribute("href")).toBe("/vacancies/24");
    expect(within(await rowOf("System design: надійний backend")).getByText(/Дедлайн/).textContent).toContain("—");
  });

  test("сторінка не ширша за екран: scrollWidth дорівнює clientWidth", async () => {
    await openPrep(prepBackend({ topics: TOPICS }), "/prep", "mobile");
    await topicList();

    const root = document.documentElement;
    expect(root.scrollWidth).toBe(root.clientWidth);
    const main = screen.getByRole("main");
    expect(main.scrollWidth).toBe(main.clientWidth);
  });

  test("довгі назви теми переносяться й не розпирають картку", async () => {
    const title = "Дуже-дуже-довга-назва-теми-яка-мусить-переноситись-а-не-розпирати-сторінку-вбік-0123456789";
    await openPrep(prepBackend({ topics: [apiTopic(1, { title })] }), "/prep", "mobile");

    const link = within(await rowOf(title)).getByRole("link", { name: title });
    expect(link.className).toContain("[overflow-wrap:anywhere]");
    expect((await rowOf(title)).className).toContain("min-w-0");
  });

  test("touch-цілі від 44 px: кожен інтерактивний елемент сторінки має висоту 44 px для грубого вказівника", async () => {
    await openPrep(prepBackend({ topics: TOPICS }), "/prep", "mobile");
    await topicList();

    const main = screen.getByRole("main");
    const targets = Array.from(main.querySelectorAll<HTMLElement>("button, a[href], select, input, summary"));
    expect(targets.length).toBeGreaterThan(10);
    const small = targets.filter((target) => !/pointer-coarse:(min-)?(h|size)-11/.test(target.className)).map((target) => target.outerHTML.slice(0, 80));
    expect(small).toEqual([]);
  });
});
