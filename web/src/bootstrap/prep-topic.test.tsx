/** «Підготовка» `/prep/{n}`: опис, вакансії з прогалинами, кроки, квіз, запити для Claude, «не знайдено», завантаження й помилки, 375 px. */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { COPIED, delegateBlocks, findDelegate, queryDelegate } from "./delegateHarness";
import { ddd, LONG_NOTE } from "./prepFixtures";
import { apiJob, apiStep, apiTopic, prepBackend, problem } from "./prepBackend";
import { openPrep, openTopic, stepOf, topicTitles } from "./prepHarness";
import { json } from "./testClient";

const location = () => screen.getByTestId("location").textContent;

const PLAN_EMPTY = "Агент складе план теми: вивчення → практика → перевірка.";
const PLAN = "Агент складе або оновить план теми.";
const QUESTIONS = "Агент складе питання квізу до теми.";
const QUIZ = "Агент проведе квіз на сьогодні з цієї теми.";

describe("шапка теми", () => {
  test("заголовок, бейдж статусу, вид, номер, дедлайн, опис і назва вкладки браузера", async () => {
    await openTopic(prepBackend({ topics: [ddd()] }), "/prep/7");

    expect(await screen.findByRole("heading", { level: 1, name: "DDD у Symfony" })).toBeDefined();
    expect(screen.getByText("Вивчаю")).toBeDefined();
    expect(screen.getByText("Технічна · тема #7 · дедлайн 2026-11-03")).toBeDefined();
    expect(screen.getByText("Навчитися визначати межі агрегатів і тримати бізнес-правила незалежними від Symfony та Doctrine.")).toBeDefined();
    expect(document.title).toBe("DDD у Symfony · joboffer");
  });

  test("без дедлайну в рядку під заголовком його нема", async () => {
    await openTopic(prepBackend({ topics: [apiTopic(7, { title: "Без дедлайну", kind: "domain" })] }), "/prep/7");

    expect(await screen.findByText("Доменна · тема #7")).toBeDefined();
  });

  test("прогрес: відсоток, виконано з усіх кроків, залишок часу й смуга з aria", async () => {
    await openTopic(prepBackend({ topics: [ddd()] }), "/prep/7");

    expect(await screen.findByText("25%")).toBeDefined();
    expect(screen.getByText("1/4 кроків")).toBeDefined();
    expect(screen.getByText("Лишилось ~210 хв")).toBeDefined();
    expect(screen.getByRole("progressbar", { name: "DDD у Symfony" }).getAttribute("aria-valuenow")).toBe("25");
  });

  test("«← Усі теми» веде на реєстр", async () => {
    await openTopic(prepBackend({ topics: [ddd()] }), "/prep/7");

    expect((await screen.findByRole("link", { name: "← Усі теми" })).getAttribute("href")).toBe("/prep");
  });

  test("у навігації «Підготовка» лишається поточним розділом", async () => {
    await openTopic(prepBackend({ topics: [ddd()] }), "/prep/7");
    await screen.findByRole("heading", { level: 1, name: "DDD у Symfony" });

    const nav = screen.getByRole("navigation", { name: "Головна навігація" });
    const current = within(nav)
      .getAllByRole("link")
      .filter((link) => link.getAttribute("aria-current") === "page");
    expect(current.map((link) => link.textContent)).toEqual(["Підготовка"]);
  });

  test("з реєстру назва теми відкриває її сторінку, а «← Усі теми» повертає назад", async () => {
    const user = userEvent.setup();
    await openPrep(prepBackend({ topics: [ddd()] }));

    await user.click(within(await screen.findByLabelText("Список тем")).getByRole("link", { name: "DDD у Symfony" }));
    expect(await screen.findByRole("heading", { level: 1, name: "DDD у Symfony" })).toBeDefined();
    expect(location()).toBe("/prep/7");

    await user.click(screen.getByRole("link", { name: "← Усі теми" }));
    expect(await topicTitles()).toEqual(["DDD у Symfony"]);
    expect(location()).toBe("/prep");
  });
});

describe("вакансії з прогалинами", () => {
  test("згорнутий розділ із кількістю; розгорнутий — посилання «назва · компанія» зі скором і прогалиною кожної", async () => {
    const user = userEvent.setup();
    await openTopic(prepBackend({ topics: [ddd()] }), "/prep/7");

    const summary = await screen.findByText("Вакансії та прогалини", { selector: "summary" });
    const section = summary.closest("details") as HTMLDetailsElement;
    expect(section.open).toBe(false);
    expect(summary.textContent).toContain("2");
    await user.click(summary);

    expect(section.open).toBe(true);
    const northstar = within(section).getByRole("link", { name: "Senior Backend Engineer · Northstar 86/100" });
    expect(northstar.getAttribute("href")).toBe("/vacancies/24");
    expect(within(section).getByRole("link", { name: "PHP Platform Engineer · Acme 79/100" }).getAttribute("href")).toBe("/vacancies/31");
    expect(within(section).getByText("Потрібно підтвердити практику Domain-Driven Design.")).toBeDefined();
    expect(within(section).getByText("Бракує прикладу оптимізації SQL.")).toBeDefined();
  });

  test("вакансія без назви й компанії — «Вакансія #N»", async () => {
    await openTopic(prepBackend({ topics: [apiTopic(7, { jobs: [apiJob(24, { title: null, company: null, score: 70 })] })] }), "/prep/7");

    expect(await screen.findByRole("link", { name: "Вакансія #24 70/100" })).toBeDefined();
  });
});

describe("кроки", () => {
  test("кожен крок: вид, хвилини; виконаний — ще й день за Мадридом", async () => {
    await openTopic(prepBackend({ topics: [ddd()] }), "/prep/7");
    await screen.findByRole("heading", { level: 2, name: "План теми" });

    expect(stepOf("Межі контекстів").querySelector("summary")?.textContent).toContain("Вивчення · ~45 хв · виконано 2026-10-25");
    expect(stepOf("Агрегати та інваріанти").querySelector("summary")?.textContent).toContain("Вивчення · ~60 хв");
    expect(stepOf("Агрегати та інваріанти").querySelector("summary")?.textContent).not.toContain("виконано");
    expect(stepOf("Змоделювати агрегат Schedule").querySelector("summary")?.textContent).toContain("Практика · ~120 хв");
    expect(stepOf("Пояснити рішення англійською").querySelector("summary")?.textContent).toContain("Перевірка · ~30 хв");
  });

  test("розкритий лише перший невиконаний крок; виконаний і решта згорнуті", async () => {
    await openTopic(prepBackend({ topics: [ddd()] }), "/prep/7");
    await screen.findByRole("heading", { level: 2, name: "План теми" });

    expect(stepOf("Межі контекстів").open).toBe(false);
    expect(stepOf("Агрегати та інваріанти").open).toBe(true);
    expect(stepOf("Змоделювати агрегат Schedule").open).toBe(false);
    expect(stepOf("Пояснити рішення англійською").open).toBe(false);
  });

  test("коли всі кроки виконано, не розкрито жоден", async () => {
    const topic = apiTopic(7, { steps: [apiStep(1, { done_at: "2026-10-25T08:00:00Z", done_on: "2026-10-25", title: "Єдиний крок" })] });
    await openTopic(prepBackend({ topics: [topic] }), "/prep/7");
    await screen.findByRole("heading", { level: 2, name: "План теми" });

    expect(stepOf("Єдиний крок").open).toBe(false);
  });

  test("крок розгортається натисканням на заголовок і показує опис", async () => {
    const user = userEvent.setup();
    await openTopic(prepBackend({ topics: [ddd()] }), "/prep/7");
    await screen.findByRole("heading", { level: 2, name: "План теми" });

    await user.click(within(stepOf("Змоделювати агрегат Schedule")).getByText("Змоделювати агрегат Schedule"));

    expect(stepOf("Змоделювати агрегат Schedule").open).toBe(true);
    expect(within(stepOf("Змоделювати агрегат Schedule")).getByText("Створи Schedule з правилом: зміни не перетинаються.")).toBeDefined();
  });

  test("ресурси кроку — зовнішні посилання з rel=noopener noreferrer, що відкриваються в новій вкладці", async () => {
    await openTopic(prepBackend({ topics: [ddd()] }), "/prep/7");
    await screen.findByRole("heading", { level: 2, name: "План теми" });

    const links = within(stepOf("Агрегати та інваріанти")).getAllByRole("link");
    expect(links.map((link) => link.getAttribute("href"))).toEqual([
      "https://martinfowler.com/bliki/DDD_Aggregate.html",
      "https://www.doctrine-project.org/projects/doctrine-orm/en/current/tutorials/embeddables.html",
    ]);
    for (const link of links) {
      expect(link.getAttribute("rel")).toBe("noopener noreferrer");
      expect(link.getAttribute("target")).toBe("_blank");
    }
    expect(links[0]?.textContent).toContain("DDD Aggregate · Martin Fowler");
  });

  test("крок без ресурсів не малює порожнього списку", async () => {
    await openTopic(prepBackend({ topics: [ddd()] }), "/prep/7");
    await screen.findByRole("heading", { level: 2, name: "План теми" });

    expect(stepOf("Змоделювати агрегат Schedule").querySelector("ul")).toBeNull();
    expect(stepOf("Агрегати та інваріанти").querySelector("ul")).not.toBeNull();
  });

  test("details і нотатка виводяться лише як текст: розмітка не стає елементами", async () => {
    const hostile = "<img src=x onerror=alert(1)><script>alert(2)</script> **не жирний**";
    const topic = apiTopic(7, { steps: [apiStep(1, { title: "Небезпечний", details: hostile, done_at: "2026-10-25T08:00:00Z", done_on: "2026-10-25", note: hostile })] });
    await openTopic(prepBackend({ topics: [topic] }), "/prep/7");
    await screen.findByRole("heading", { level: 2, name: "План теми" });

    const step = stepOf("Небезпечний");
    expect(step.querySelector("img, script")).toBeNull();
    expect(within(step).getAllByText(hostile, { selector: "p, div" })).toHaveLength(2);
  });

  test("виконаний крок показує нотатку, а без неї — «Без нотатки»", async () => {
    const topic = ddd();
    topic.steps.push(apiStep(35, { title: "Без слів", done_at: "2026-10-26T08:00:00Z", done_on: "2026-10-26" }));
    await openTopic(prepBackend({ topics: [topic] }), "/prep/7");
    await screen.findByRole("heading", { level: 2, name: "План теми" });

    expect(within(stepOf("Межі контекстів")).getByText(LONG_NOTE, { selector: "div" })).toBeDefined();
    expect(within(stepOf("Без слів")).getByText("Без нотатки")).toBeDefined();
  });

  test("тема без кроків: «Плану ще немає» і блок «Делегувати агенту», що копіює запит скласти план", async () => {
    const user = userEvent.setup();
    await openTopic(prepBackend({ topics: [apiTopic(7, { title: "Порожня" })] }), "/prep/7");
    const writeText = vi.spyOn(navigator.clipboard, "writeText");

    expect(await screen.findByRole("heading", { level: 3, name: "Плану ще немає" })).toBeDefined();
    const block = await findDelegate(PLAN_EMPTY);
    await user.click(block.getByRole("button", { name: "Копіювати промпт" }));

    expect(writeText).toHaveBeenCalledExactlyOnceWith("Create or update the plan for topic #7 in joboffer");
    expect(queryDelegate(PLAN)).toBeNull();
    expect(screen.queryByRole("button", { name: "Скопіювати запит" })).toBeNull();
    expect(screen.queryByText("Попроси Claude скласти план: вивчення → практика → перевірка.")).toBeNull();
  });
});

describe("квіз і «Делегувати агенту»", () => {
  test("лічильники теми: на повторення сьогодні / усього", async () => {
    await openTopic(prepBackend({ topics: [ddd()] }), "/prep/7");

    expect((await screen.findByRole("region", { name: "Квіз теми" })).textContent).toContain("На повторення сьогодні 4 · усього 10");
  });

  test("тема з планом і питаннями: три блоки — план, питання, квіз; старих кнопок і поля запиту нема", async () => {
    await openTopic(prepBackend({ topics: [ddd()] }), "/prep/7");

    await findDelegate(PLAN);
    await findDelegate(QUESTIONS);
    await findDelegate(QUIZ);
    expect(delegateBlocks()).toHaveLength(3);
    expect(queryDelegate(PLAN_EMPTY)).toBeNull();
    for (const name of ["Запит для Claude: план", "Скопіювати запит", "Питання для Claude", "Квіз на сьогодні"]) {
      expect(screen.queryByRole("button", { name })).toBeNull();
    }
    expect(screen.queryByRole("textbox", { name: "Запит для Claude" })).toBeNull();
  });

  test("блок плану лежить у розділі «План теми», а блоки питань і квізу — у «Квіз теми»", async () => {
    await openTopic(prepBackend({ topics: [ddd()] }), "/prep/7");

    const plan = await screen.findByRole("region", { name: "План теми" });
    const quiz = await screen.findByRole("region", { name: "Квіз теми" });
    expect(queryDelegate(PLAN, plan)).not.toBeNull();
    expect(delegateBlocks(plan)).toHaveLength(1);
    expect(queryDelegate(QUESTIONS, quiz)).not.toBeNull();
    expect(queryDelegate(QUIZ, quiz)).not.toBeNull();
    expect(delegateBlocks(quiz)).toHaveLength(2);
  });

  test("блок плану копіює запит скласти чи оновити план теми", async () => {
    const user = userEvent.setup();
    await openTopic(prepBackend({ topics: [ddd()] }), "/prep/7");
    const writeText = vi.spyOn(navigator.clipboard, "writeText");

    const block = await findDelegate(PLAN);
    await user.click(block.getByRole("button", { name: "Копіювати промпт" }));

    expect(writeText).toHaveBeenCalledExactlyOnceWith("Create or update the plan for topic #7 in joboffer");
    await waitFor(() => expect(block.getByRole("status").textContent).toBe(COPIED));
  });

  test("блок питань копіює запит скласти питання квізу до теми", async () => {
    const user = userEvent.setup();
    await openTopic(prepBackend({ topics: [ddd()] }), "/prep/7");
    const writeText = vi.spyOn(navigator.clipboard, "writeText");

    const block = await findDelegate(QUESTIONS);
    await user.click(block.getByRole("button", { name: "Копіювати промпт" }));

    expect(writeText).toHaveBeenCalledExactlyOnceWith("Write quiz questions for topic #7 in joboffer");
    await waitFor(() => expect(block.getByRole("status").textContent).toBe(COPIED));
  });

  test("є питання — блок квізу копіює запит провести квіз з цієї теми", async () => {
    const user = userEvent.setup();
    await openTopic(prepBackend({ topics: [ddd()] }), "/prep/7");
    const writeText = vi.spyOn(navigator.clipboard, "writeText");

    const block = await findDelegate(QUIZ);
    await user.click(block.getByRole("button", { name: "Копіювати промпт" }));

    expect(writeText).toHaveBeenCalledExactlyOnceWith("Run today's quiz for topic #7 in joboffer");
    await waitFor(() => expect(block.getByRole("status").textContent).toBe(COPIED));
  });

  test("питань ще нема — є блок питань без блоку квізу, а лічильники нульові", async () => {
    await openTopic(prepBackend({ topics: [apiTopic(7, { title: "Без питань" })] }), "/prep/7");

    expect((await screen.findByRole("region", { name: "Квіз теми" })).textContent).toContain("На повторення сьогодні 0 · усього 0");
    await findDelegate(QUESTIONS);
    expect(queryDelegate(QUIZ)).toBeNull();
    expect(delegateBlocks()).toHaveLength(2);
  });

  test("без доступу до буфера обміну промпт розкривається й лишається для ручного копіювання", async () => {
    const user = userEvent.setup();
    await openTopic(prepBackend({ topics: [ddd()] }), "/prep/7");
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValueOnce(new Error("denied"));

    const block = await findDelegate(PLAN);
    await user.click(block.getByRole("button", { name: "Копіювати промпт" }));

    await waitFor(() => expect(block.getByRole("status").textContent).toBe("Не вдалося скопіювати автоматично. Виділи текст промпту й скопіюй вручну."));
    expect(block.getByRole("region", { name: "Промпт" }).textContent).toContain("Create or update the plan for topic #7 in joboffer");
  });
});

describe("готовність", () => {
  test("незавершена тема: «Готовність до інтерв’ю», пояснення і «Тема готова»", async () => {
    await openTopic(prepBackend({ topics: [ddd()] }), "/prep/7");

    expect(await screen.findByRole("heading", { level: 3, name: "Готовність до інтерв’ю" })).toBeDefined();
    expect(screen.getByText("Остаточну готовність визначаєш ти.")).toBeDefined();
    expect(screen.getByRole("button", { name: "Тема готова" })).toBeDefined();
    expect(screen.queryByRole("button", { name: "Зняти позначку" })).toBeNull();
  });

  test("позначена готовою: 100 %, бейдж «Готово» і «Зняти позначку»", async () => {
    await openTopic(prepBackend({ topics: [apiTopic(7, { ...ddd(), ready: true })] }), "/prep/7");

    expect(await screen.findByRole("heading", { level: 3, name: "Тему позначено готовою" })).toBeDefined();
    expect(screen.getByText("100%")).toBeDefined();
    expect(screen.getByText("Готово")).toBeDefined();
    expect(screen.getByRole("button", { name: "Зняти позначку" })).toBeDefined();
    expect(screen.queryByRole("button", { name: "Тема готова" })).toBeNull();
  });
});

describe("тему не знайдено", () => {
  test("номера нема (404): «Тему не знайдено» і посилання «Усі теми»", async () => {
    await openTopic(prepBackend({ topics: [ddd()] }), "/prep/99");

    expect(await screen.findByRole("heading", { level: 1, name: "Тему не знайдено" })).toBeDefined();
    expect(screen.getByRole("link", { name: "Усі теми" }).getAttribute("href")).toBe("/prep");
    expect(document.title).toBe("Тему не знайдено · joboffer");
  });

  test.each(["abc", "0", "7x", "-1"])("номер «%s» — не число: те саме без жодного запиту до API", async (id) => {
    const backend = prepBackend({ topics: [ddd()] });
    await openTopic(backend, `/prep/${id}`);

    expect(await screen.findByRole("heading", { level: 1, name: "Тему не знайдено" })).toBeDefined();
    expect(backend.requests).toEqual([]);
  });
});

describe("завантаження й помилки", () => {
  test("поки тема вантажиться — статус зі скелетоном, потім тема", async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const backend = prepBackend({ topics: [ddd()] }, { topic: () => gate.then(() => json(200, ddd())) });
    await openTopic(backend, "/prep/7", "desktop", false);

    expect(await screen.findByRole("status", { name: "Завантажуємо тему" })).toBeDefined();
    release();
    expect(await screen.findByRole("heading", { level: 1, name: "DDD у Symfony" })).toBeDefined();
    expect(screen.queryByRole("status", { name: "Завантажуємо тему" })).toBeNull();
  });

  test("мережа недоступна: помилка й «Спробувати ще раз», що перезавантажує тему", async () => {
    const user = userEvent.setup();
    let fail = true;
    const backend = prepBackend({ topics: [ddd()] }, { topic: () => (fail ? problem(500, "internal", "Збій") : undefined) });
    await openTopic(backend, "/prep/7");

    expect((await screen.findByRole("alert")).textContent).toContain("Не вдалося завантажити тему");
    expect(screen.getByText("Перевір з’єднання й повтори спробу.")).toBeDefined();
    fail = false;
    await user.click(screen.getByRole("button", { name: "Спробувати ще раз" }));

    expect(await screen.findByRole("heading", { level: 1, name: "DDD у Symfony" })).toBeDefined();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(backend.requests.filter((request) => request === "GET /api/prep/topics/7")).toHaveLength(2);
  });

  test("сесія завершилась (401): підказка увійти знову, без повтору", async () => {
    await openTopic(prepBackend({ topics: [ddd()] }, { topic: () => problem(401, "not_authenticated", "Потрібен вхід") }), "/prep/7");

    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("Сесія завершилась. Увійди знову, щоб побачити тему."));
    expect(screen.queryByRole("button", { name: "Спробувати ще раз" })).toBeNull();
  });
});

describe("вузький екран (375 px)", () => {
  const LONG = "Дуже-дуже-довга-назва-яка-мусить-переноситись-а-не-розпирати-сторінку-вбік-0123456789";

  test("довгі заголовок, опис, нотатка й текст кроку переносяться", async () => {
    const topic = apiTopic(7, {
      title: LONG,
      summary: LONG,
      steps: [apiStep(1, { title: "Крок", details: LONG, done_at: "2026-10-25T08:00:00Z", done_on: "2026-10-25", note: LONG })],
    });
    await openTopic(prepBackend({ topics: [topic] }), "/prep/7", "mobile");

    expect((await screen.findByRole("heading", { level: 1, name: LONG })).className).toContain("[overflow-wrap:anywhere]");
    const texts = screen.getAllByText(LONG, { selector: "h1, p, div" });
    expect(texts.length).toBeGreaterThanOrEqual(4);
    expect(texts.every((element) => element.className.includes("[overflow-wrap:anywhere]") || element.tagName === "H1")).toBe(true);
  });

  test("сторінка не ширша за екран: scrollWidth дорівнює clientWidth", async () => {
    await openTopic(prepBackend({ topics: [ddd()] }), "/prep/7", "mobile");
    await screen.findByRole("heading", { level: 1, name: "DDD у Symfony" });

    const root = document.documentElement;
    expect(root.scrollWidth).toBe(root.clientWidth);
    const main = screen.getByRole("main");
    expect(main.scrollWidth).toBe(main.clientWidth);
  });

  test("touch-цілі від 44 px: кожен інтерактивний елемент сторінки має висоту 44 px для грубого вказівника", async () => {
    const user = userEvent.setup();
    await openTopic(prepBackend({ topics: [ddd()] }), "/prep/7", "mobile");
    await user.click(await screen.findByText("Вакансії та прогалини", { selector: "summary" }));
    await user.click(within(stepOf("Межі контекстів")).getByText("Межі контекстів"));

    const main = screen.getByRole("main");
    const targets = Array.from(main.querySelectorAll<HTMLElement>("button, a[href], select, input, summary"));
    expect(targets.length).toBeGreaterThan(15);
    const small = targets.filter((target) => !/pointer-coarse:(min-)?(h|size)-11/.test(target.className)).map((target) => target.outerHTML.slice(0, 80));
    expect(small).toEqual([]);
  });

  test("поле нотатки має шрифт від 16 px, щоб iOS не наближав сторінку", async () => {
    await openTopic(prepBackend({ topics: [ddd()] }), "/prep/7", "mobile");

    const notes = await screen.findAllByRole("textbox", { name: /Нотатка/ });
    expect(notes).toHaveLength(4);
    for (const note of notes) {
      expect(note.className).toContain("text-base");
    }
  });
});
