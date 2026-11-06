import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { apiFact, factsBackend, type ApiCv, type ApiFact } from "./factsBackend";
import { connectPrompts } from "./promptsBackend";
import { renderClient } from "./testClient";
import { setViewport } from "./viewport";

const FACTS: ApiFact[] = [
  apiFact(1, "skill", "Python 3.14", true),
  apiFact(2, "achievement", "Скоротив p95 затримку на 40%"),
  apiFact(3, "experience", "Backend Lead у Northstar Labs, 2022–2025", true),
  apiFact(4, "skill", "Postgres і Redis"),
  apiFact(5, "project", "Міграція черг на Kafka"),
  apiFact(6, "education", "Магістр, КПІ, 2019", true),
  apiFact(7, "language", "Англійська — B2"),
  apiFact(8, "skill", "Rust (базово)", true),
];
const CV: ApiCv = { file_name: "cv.pdf", text: "Марко Коваленко\nBackend Engineer", saved_at: "2026-10-20T08:00:00Z" };

async function openFacts(facts: ApiFact[] = FACTS, cv: ApiCv | null = CV, path = "/facts") {
  const backend = factsBackend(facts, cv);
  connectPrompts(backend);
  const view = renderClient(path, backend.fetchFn);
  await screen.findByRole("heading", { level: 1, name: "Факти" });
  await waitFor(() => expect(screen.queryByRole("status", { name: "Завантажуємо факти" })).toBeNull());
  return { backend, view, user: userEvent.setup() };
}

const item = (id: number) => screen.getByRole("listitem", { name: `Факт ${id}` });
const shownIds = () => screen.queryAllByRole("listitem", { hidden: true }).map((entry) => Number(/^Факт (\d+)$/.exec(entry.getAttribute("aria-label") ?? "")?.[1]));
const category = (name: string) => screen.getByRole("button", { name });
const search = () => screen.getByRole("searchbox", { name: "Пошук фактів" });
const status = () => screen.getByRole("combobox", { name: "Статус" });
// `hidden`: за модальним діалогом решта сторінки схована від читачів екрана, але повідомлення в DOM.
const messages = () => screen.getByRole("status", { name: "Повідомлення", hidden: true }).textContent;

describe("сторінка «Факти»", () => {
  test("має заголовок, пояснення ролі фактів і заголовок вкладки", async () => {
    await openFacts();
    expect(screen.getByRole("heading", { level: 1, name: "Факти" })).toBeDefined();
    expect(screen.getByText(/У CV потрапляють лише підтверджені факти/)).toBeDefined();
    expect(document.title).toBe("Факти · joboffer");
  });

  test("посилання з прогалини «/facts?q=%237» відкриває сторінку з пошуком #7: видно лише факт 7", async () => {
    await openFacts(FACTS, CV, "/facts?q=%237");
    expect((search() as HTMLInputElement).value).toBe("#7");
    expect(shownIds()).toEqual([7]);
  });

  test("поки факти вантажаться — скелетон зі статусом, а не порожній стан", async () => {
    const backend = factsBackend(FACTS, CV);
    const gate = backend.hold();
    renderClient("/facts", backend.fetchFn);
    const loading = await screen.findByRole("status", { name: "Завантажуємо факти" });
    expect(loading.getAttribute("aria-busy")).toBe("true");
    expect(screen.queryByText("Фактів поки немає")).toBeNull();
    await act(async () => gate.release());
    expect(await screen.findByRole("list", { name: "Факти" })).toBeDefined();
    expect(screen.queryByRole("status", { name: "Завантажуємо факти" })).toBeNull();
  });

  test("усі факти — в порядку категорій сервера; кожен має ID, категорію й текстовий статус", async () => {
    await openFacts();
    expect(shownIds()).toEqual([3, 2, 5, 1, 4, 8, 6, 7]);
    const four = within(item(4));
    expect(four.getByText("#4")).toBeDefined();
    expect(four.getByText("Скіли")).toBeDefined();
    expect(four.getByText("Postgres і Redis")).toBeDefined();
    expect(four.getByText("Потребує перевірки")).toBeDefined();
    expect(within(item(1)).getByText("Підтверджено")).toBeDefined();
  });

  test("у категоріях — точні лічильники", async () => {
    await openFacts();
    const nav = screen.getByRole("navigation", { name: "Категорії фактів" });
    expect(within(nav).getAllByRole("button").map((button) => button.textContent)).toEqual([
      "Усі8",
      "Досвід1",
      "Досягнення1",
      "Проєкти1",
      "Скіли3",
      "Освіта1",
      "Мови1",
    ]);
  });

  test("згорнутий Original CV: назва файлу, день і текст", async () => {
    await openFacts();
    expect(screen.getByText("Оригінальний CV · cv.pdf · 2026-10-20")).toBeDefined();
    const cv = screen.getByText(/Марко Коваленко/);
    expect(cv.closest("details")?.hasAttribute("open")).toBe(false);
    expect(cv.textContent).toBe("Марко Коваленко\nBackend Engineer");
  });

  test("Original CV без назви файлу показує лише день; нема CV — чесно про це каже", async () => {
    await openFacts(FACTS, { ...CV, file_name: null });
    expect(screen.getByText("Оригінальний CV · 2026-10-20")).toBeDefined();
  });

  test("Original CV ще не збережено — текст про це, без summary", async () => {
    await openFacts(FACTS, null);
    expect(screen.getByText("Оригінальний CV ще не збережено.")).toBeDefined();
    expect(screen.queryByText(/Оригінальний CV ·/)).toBeNull();
  });

  test("помилка оригіналу CV не ховає факти", async () => {
    const backend = factsBackend(FACTS, CV);
    backend.failNext("cv");
    renderClient("/facts", backend.fetchFn);
    expect(await screen.findByRole("list", { name: "Факти" })).toBeDefined();
    expect(screen.getByText("Не вдалося завантажити оригінальний CV.")).toBeDefined();
  });
});

describe("блок «на перевірці»", () => {
  test("показує, скільки фактів чекає, і веде до відфільтрованого списку", async () => {
    const { user } = await openFacts();
    const block = screen.getByRole("region", { name: "Перевірка фактів" });
    expect(within(block).getByText("4 факти потребують перевірки")).toBeDefined();
    await user.click(category("Скіли 3"));
    await user.type(search(), "rust");
    await user.click(within(block).getByRole("button", { name: "Переглянути" }));
    expect((status() as HTMLSelectElement).value).toBe("pending");
    expect(category("Усі 8").getAttribute("aria-pressed")).toBe("true");
    expect((search() as HTMLInputElement).value).toBe("");
    expect(shownIds()).toEqual([2, 5, 4, 7]);
  });

  test("коли все перевірено, замість лічильника — спокійне повідомлення", async () => {
    await openFacts(FACTS.map((fact) => ({ ...fact, confirmed: true })));
    const block = screen.getByRole("region", { name: "Перевірка фактів" });
    expect(within(block).getByText("Усі факти перевірено")).toBeDefined();
    expect(within(block).queryByRole("button", { name: "Переглянути" })).toBeNull();
  });
});

describe("пошук і фільтри", () => {
  test("статус має три значення: усі, потребують перевірки, підтверджені", async () => {
    await openFacts();
    expect(within(status()).getAllByRole("option").map((option) => option.textContent)).toEqual(["Усі", "Потребують перевірки", "Підтверджені"]);
  });

  test("пошук за текстом", async () => {
    const { user } = await openFacts();
    await user.type(search(), "kafka");
    expect(shownIds()).toEqual([5]);
  });

  test("пошук за ID: «#7» і «7»", async () => {
    const { user } = await openFacts();
    await user.type(search(), "#7");
    expect(shownIds()).toEqual([7]);
    await user.clear(search());
    await user.type(search(), "8");
    expect(shownIds()).toEqual([8]);
  });

  test("пошук, статус і категорія діють разом", async () => {
    const { user } = await openFacts();
    await user.click(category("Скіли 3"));
    await user.selectOptions(status(), "Потребують перевірки");
    expect(shownIds()).toEqual([4]);
    await user.type(search(), "redis");
    expect(shownIds()).toEqual([4]);
    await user.clear(search());
    await user.type(search(), "python");
    expect(shownIds()).toEqual([]);
  });

  test("немає результатів — повідомлення зі скиданням фільтрів, що повертає список", async () => {
    const { user } = await openFacts();
    await user.type(search(), "ґоґоль");
    expect(screen.getByText("Фактів не знайдено")).toBeDefined();
    expect(screen.queryByText("Фактів поки немає")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Скинути фільтри" }));
    expect(shownIds()).toHaveLength(8);
    expect((search() as HTMLInputElement).value).toBe("");
  });

  test("заголовок списку називає категорію й кількість показаних", async () => {
    const { user } = await openFacts();
    expect(screen.getByRole("heading", { level: 2, name: "Усі · 8" })).toBeDefined();
    await user.click(category("Скіли 3"));
    expect(screen.getByRole("heading", { level: 2, name: "Скіли · 3" })).toBeDefined();
    await user.selectOptions(status(), "Підтверджені");
    expect(screen.getByRole("heading", { level: 2, name: "Скіли · 2" })).toBeDefined();
  });
});

describe("порожні стани й помилка завантаження", () => {
  test("порожня база — підказка попросити Claude розібрати CV", async () => {
    await openFacts([], null);
    expect(screen.getByText("Фактів поки немає")).toBeDefined();
    expect(screen.getByText(/попроси Claude розібрати CV/)).toBeDefined();
    expect(screen.queryByRole("list", { name: "Факти" })).toBeNull();
  });

  test("помилка завантаження — повідомлення й «Спробувати ще», що перезавантажує", async () => {
    const backend = factsBackend(FACTS, CV);
    backend.failNext("list");
    renderClient("/facts", backend.fetchFn);
    expect((await screen.findByRole("alert")).textContent).toContain("Не вдалося завантажити факти");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Спробувати ще" }));
    expect(await screen.findByRole("list", { name: "Факти" })).toBeDefined();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("підтвердження", () => {
  test("підтвердити один факт: запит із одним id, статус текстом, лічильники точні", async () => {
    const { backend, user } = await openFacts();
    await user.click(within(item(4)).getByRole("button", { name: "Підтвердити факт 4" }));
    await waitFor(() => expect(within(item(4)).getByText("Підтверджено")).toBeDefined());
    expect(backend.bodies).toEqual([{ fact_ids: [4] }]);
    expect(within(item(4)).queryByRole("button", { name: "Підтвердити факт 4" })).toBeNull();
    expect(within(screen.getByRole("region", { name: "Перевірка фактів" })).getByText("3 факти потребують перевірки")).toBeDefined();
    expect(messages()).toBe("Факт 4 підтверджено. Тепер його можна використати у CV.");
  });

  test("підтверджені факти не мають кнопки «Підтвердити»", async () => {
    await openFacts();
    expect(within(item(1)).queryByRole("button", { name: /Підтвердити/ })).toBeNull();
    expect(within(item(1)).getByRole("button", { name: "Редагувати факт 1" })).toBeDefined();
  });

  test("масове підтвердження шле лише явно вибрані, кількість вибраних видно", async () => {
    const { backend, user } = await openFacts();
    expect(screen.getByText("Вибрано: 0")).toBeDefined();
    expect(screen.queryByRole("button", { name: /Підтвердити вибрані/ })).toBeNull();
    await user.click(screen.getByRole("checkbox", { name: "Вибрати факт 5" }));
    await user.click(screen.getByRole("checkbox", { name: "Вибрати факт 2" }));
    expect(screen.getByText("Вибрано: 2")).toBeDefined();
    await user.click(screen.getByRole("button", { name: "Підтвердити вибрані (2)" }));
    await waitFor(() => expect(screen.getByText("Вибрано: 0")).toBeDefined());
    expect(backend.bodies).toEqual([{ fact_ids: [2, 5] }]);
    expect(backend.facts.filter((fact) => fact.confirmed).map((fact) => fact.fact_id).sort()).toEqual([1, 2, 3, 5, 6, 8]);
    expect(within(item(2)).getByText("Підтверджено")).toBeDefined();
    expect(within(item(7)).getByText("Потребує перевірки")).toBeDefined();
    expect(messages()).toBe("Вибрані факти підтверджено: 2.");
  });

  test("«Зняти вибір» очищає вибір без запитів", async () => {
    const { backend, user } = await openFacts();
    await user.click(screen.getByRole("checkbox", { name: "Вибрати факт 5" }));
    await user.click(screen.getByRole("button", { name: "Зняти вибір" }));
    expect(screen.getByText("Вибрано: 0")).toBeDefined();
    expect(backend.bodies).toEqual([]);
  });

  test.each([
    ["категорії", async (user: ReturnType<typeof userEvent.setup>) => user.click(category("Скіли 3"))],
    ["статусу", async (user: ReturnType<typeof userEvent.setup>) => user.selectOptions(status(), "Потребують перевірки")],
    ["пошуку", async (user: ReturnType<typeof userEvent.setup>) => user.type(search(), "a")],
  ])("зміна %s очищає вибір, а приховані записи не підтверджуються", async (_name, change) => {
    const { backend, user } = await openFacts();
    await user.click(screen.getByRole("checkbox", { name: "Вибрати факт 5" }));
    await user.click(screen.getByRole("checkbox", { name: "Вибрати факт 2" }));
    await change(user);
    expect(screen.getByText("Вибрано: 0")).toBeDefined();
    expect(screen.queryByRole("button", { name: /Підтвердити вибрані/ })).toBeNull();
    expect(backend.bodies).toEqual([]);
    expect(backend.facts.find((fact) => fact.fact_id === 5)?.confirmed).toBe(false);
  });

  test("вибір можна зняти тим самим прапорцем", async () => {
    const { user } = await openFacts();
    const box = screen.getByRole("checkbox", { name: "Вибрати факт 5" });
    await user.click(box);
    expect(box.getAttribute("aria-checked")).toBe("true");
    await user.click(box);
    expect(screen.getByText("Вибрано: 0")).toBeDefined();
  });

  test.each([
    ["500", 500, { code: "internal_error", message: "Внутрішня помилка", field_errors: [] }],
    ["422", 422, { code: "invalid_value", message: "Не вибрано жодного факту.", field_errors: [{ field: "fact_ids", message: "Не вибрано жодного факту." }] }],
  ])("помилка %s на масовому підтвердженні: повідомлення, вибір лишився, успіх не симулюється", async (_name, code, body) => {
    const { backend, user } = await openFacts();
    await user.click(screen.getByRole("checkbox", { name: "Вибрати факт 5" }));
    backend.failNext("confirm", code, body);
    await user.click(screen.getByRole("button", { name: "Підтвердити вибрані (1)" }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain(code === 500 ? "Не вдалося підтвердити вибрані факти" : "Не вибрано жодного факту.");
    expect(screen.getByText("Вибрано: 1")).toBeDefined();
    expect(screen.getByRole("checkbox", { name: "Вибрати факт 5" }).getAttribute("aria-checked")).toBe("true");
    expect(within(item(5)).getByText("Потребує перевірки")).toBeDefined();
    expect(messages()).toBe("");
    await user.click(screen.getByRole("button", { name: "Підтвердити вибрані (1)" }));
    await waitFor(() => expect(within(item(5)).getByText("Підтверджено")).toBeDefined());
    expect(screen.queryByRole("alert")).toBeNull();
  });

  test("помилка на підтвердженні одного факту: повідомлення, статус не змінився", async () => {
    const { backend, user } = await openFacts();
    backend.failNext("confirm");
    await user.click(within(item(4)).getByRole("button", { name: "Підтвердити факт 4" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Не вдалося підтвердити факт 4");
    expect(within(item(4)).getByText("Потребує перевірки")).toBeDefined();
    expect(messages()).toBe("");
  });

  test("факт уже видалили деінде (404) — повідомлення, а список оновлюється з сервера", async () => {
    const { backend, user } = await openFacts();
    backend.facts = backend.facts.filter((fact) => fact.fact_id !== 4);
    await user.click(within(item(4)).getByRole("button", { name: "Підтвердити факт 4" }));
    expect((await screen.findByRole("alert")).textContent).toContain("не знайдено");
    await waitFor(() => expect(shownIds()).not.toContain(4));
    expect(backend.requests.filter((request) => request === "GET /api/facts")).toHaveLength(2);
  });
});

describe("редактор на місці запису", () => {
  test("відкривається в тому ж рядку: категорія, текст, зберегти, скасувати, видалити й підказка про підтвердження", async () => {
    const { user } = await openFacts();
    await user.click(within(item(4)).getByRole("button", { name: "Редагувати факт 4" }));
    const form = within(item(4)).getByRole("form", { name: "Редагування факту 4" });
    const kind = within(form).getByRole("combobox", { name: "Категорія" }) as HTMLSelectElement;
    expect(kind.value).toBe("skill");
    expect(within(kind).getAllByRole("option").map((option) => option.textContent)).toEqual(["Досвід", "Досягнення", "Проєкти", "Скіли", "Освіта", "Мови"]);
    expect((within(form).getByRole("textbox", { name: "Формулювання факту" }) as HTMLTextAreaElement).value).toBe("Postgres і Redis");
    expect(within(form).getByText(/після збереження факт стане непідтвердженим/i)).toBeDefined();
    for (const name of ["Зберегти", "Скасувати", "Видалити"]) {
      expect(within(form).getByRole("button", { name })).toBeDefined();
    }
  });

  test("фокус іде в поле тексту; «Скасувати» закриває редактор без запитів і повертає фокус на «Редагувати»", async () => {
    const { backend, user } = await openFacts();
    await user.click(within(item(4)).getByRole("button", { name: "Редагувати факт 4" }));
    expect(document.activeElement).toBe(within(item(4)).getByRole("textbox", { name: "Формулювання факту" }));
    await user.type(document.activeElement as HTMLElement, " зайве");
    await user.click(within(item(4)).getByRole("button", { name: "Скасувати" }));
    expect(within(item(4)).queryByRole("form")).toBeNull();
    expect(within(item(4)).getByText("Postgres і Redis")).toBeDefined();
    expect(document.activeElement).toBe(within(item(4)).getByRole("button", { name: "Редагувати факт 4" }));
    expect(backend.requests).not.toContain("PUT /api/facts/4");
  });

  test("зберегти: запит із видом і текстом, редактор закрито, факт непідтверджений, повідомлення про це", async () => {
    const { backend, user } = await openFacts();
    await user.click(within(item(1)).getByRole("button", { name: "Редагувати факт 1" }));
    const text = within(item(1)).getByRole("textbox", { name: "Формулювання факту" });
    await user.clear(text);
    await user.type(text, "Python 3.14 і asyncio");
    await user.click(within(item(1)).getByRole("button", { name: "Зберегти" }));
    await waitFor(() => expect(within(item(1)).queryByRole("form")).toBeNull());
    expect(backend.bodies).toEqual([{ kind: "skill", text: "Python 3.14 і asyncio" }]);
    expect(within(item(1)).getByText("Python 3.14 і asyncio")).toBeDefined();
    expect(within(item(1)).getByText("Потребує перевірки")).toBeDefined();
    expect(messages()).toBe("Факт 1 змінено — підтверди його знову.");
    expect(document.activeElement).toBe(within(item(1)).getByRole("button", { name: "Редагувати факт 1" }));
  });

  test("зміна категорії: факт опиняється в потрібній категорії й непідтверджений, лічильники точні", async () => {
    const { user } = await openFacts();
    await user.click(within(item(8)).getByRole("button", { name: "Редагувати факт 8" }));
    await user.selectOptions(within(item(8)).getByRole("combobox", { name: "Категорія" }), "Проєкти");
    await user.click(within(item(8)).getByRole("button", { name: "Зберегти" }));
    await waitFor(() => expect(within(item(8)).queryByRole("form")).toBeNull());
    expect(category("Скіли 2")).toBeDefined();
    expect(category("Проєкти 2")).toBeDefined();
    expect(within(item(8)).getByText("Проєкти")).toBeDefined();
    expect(within(item(8)).getByText("Потребує перевірки")).toBeDefined();
    await user.click(category("Проєкти 2"));
    expect(shownIds()).toEqual([5, 8]);
    expect(within(screen.getByRole("region", { name: "Перевірка фактів" })).getByText("5 фактів потребують перевірки")).toBeDefined();
  });

  test("422 від сервера: помилка біля поля, чернетка й редактор лишаються", async () => {
    const { backend, user } = await openFacts();
    await user.click(within(item(4)).getByRole("button", { name: "Редагувати факт 4" }));
    const text = within(item(4)).getByRole("textbox", { name: "Формулювання факту" });
    await user.clear(text);
    await user.click(within(item(4)).getByRole("button", { name: "Зберегти" }));
    await waitFor(() => expect(within(item(4)).getByText("Факт не може бути порожнім.")).toBeDefined());
    expect(text.getAttribute("aria-invalid")).toBe("true");
    expect(within(item(4)).getByRole("form")).toBeDefined();
    await user.type(text, "Postgres 18");
    expect(backend.facts.find((fact) => fact.fact_id === 4)?.text).toBe("Postgres і Redis");
  });

  test("422 на сторінці з довгим текстом: тест сервера про 500 символів показано біля поля", async () => {
    const { user } = await openFacts();
    await user.click(within(item(4)).getByRole("button", { name: "Редагувати факт 4" }));
    const text = within(item(4)).getByRole("textbox", { name: "Формулювання факту" });
    await user.clear(text);
    await user.click(text);
    await user.paste("x".repeat(501));
    await user.click(within(item(4)).getByRole("button", { name: "Зберегти" }));
    expect(await within(item(4)).findByText("Факт задовгий: більше 500 символів — розбий на кілька.")).toBeDefined();
  });

  test("409 (такий текст уже є): повідомлення з номером біля поля тексту, чернетка лишилась", async () => {
    const { user } = await openFacts();
    await user.click(within(item(4)).getByRole("button", { name: "Редагувати факт 4" }));
    const text = within(item(4)).getByRole("textbox", { name: "Формулювання факту" });
    await user.clear(text);
    await user.type(text, "  python 3.14 ");
    await user.click(within(item(4)).getByRole("button", { name: "Зберегти" }));
    expect(await within(item(4)).findByText("Такий факт уже є: #1.")).toBeDefined();
    expect((text as HTMLTextAreaElement).value).toBe("  python 3.14 ");
  });

  test("5xx на збереженні: загальне повідомлення, чернетка лишилась, успіх не симулюється; повтор допомагає", async () => {
    const { backend, user } = await openFacts();
    await user.click(within(item(4)).getByRole("button", { name: "Редагувати факт 4" }));
    const text = within(item(4)).getByRole("textbox", { name: "Формулювання факту" });
    await user.clear(text);
    await user.type(text, "Postgres 18");
    backend.failNext("update");
    await user.click(within(item(4)).getByRole("button", { name: "Зберегти" }));
    expect((await within(item(4)).findByRole("alert")).textContent).toBe("Не вдалося зберегти зміни. Чернетку збережено — спробуй ще раз.");
    expect((text as HTMLTextAreaElement).value).toBe("Postgres 18");
    expect(messages()).toBe("");
    expect(backend.facts.find((fact) => fact.fact_id === 4)?.text).toBe("Postgres і Redis");
    await user.click(within(item(4)).getByRole("button", { name: "Зберегти" }));
    await waitFor(() => expect(within(item(4)).queryByRole("form")).toBeNull());
    expect(within(item(4)).getByText("Postgres 18")).toBeDefined();
  });

  test("поки зберігається, кнопка «Зберегти» вимкнена: подвійний клік не шле два запити", async () => {
    const { backend, user } = await openFacts();
    await user.click(within(item(4)).getByRole("button", { name: "Редагувати факт 4" }));
    await user.type(within(item(4)).getByRole("textbox", { name: "Формулювання факту" }), "!");
    await user.dblClick(within(item(4)).getByRole("button", { name: "Зберегти" }));
    await waitFor(() => expect(within(item(4)).queryByRole("form")).toBeNull());
    expect(backend.requests.filter((request) => request === "PUT /api/facts/4")).toHaveLength(1);
  });

  test("відкрити редактор іншого факту, поки в цьому є правки, — спершу попередження", async () => {
    const { user } = await openFacts();
    await user.click(within(item(4)).getByRole("button", { name: "Редагувати факт 4" }));
    await user.type(within(item(4)).getByRole("textbox", { name: "Формулювання факту" }), "!");
    await user.click(within(item(5)).getByRole("button", { name: "Редагувати факт 5" }));
    const dialog = screen.getByRole("alertdialog", { name: "Є незбережені зміни" });
    await user.click(within(dialog).getByRole("button", { name: "Відкинути зміни" }));
    expect(within(item(4)).queryByRole("form")).toBeNull();
    expect(within(item(5)).getByRole("form", { name: "Редагування факту 5" })).toBeDefined();
  });
});

describe("зміна фільтра чи навігація під час редагування", () => {
  async function dirtyEditor() {
    const opened = await openFacts();
    await opened.user.click(within(item(4)).getByRole("button", { name: "Редагувати факт 4" }));
    await opened.user.type(within(item(4)).getByRole("textbox", { name: "Формулювання факту" }), " (нове)");
    return opened;
  }

  test("фільтр із непорожньою чернеткою питає: «Залишитись» зберігає введене й не міняє фільтр", async () => {
    const { user } = await dirtyEditor();
    await user.click(category("Мови 1"));
    const dialog = screen.getByRole("alertdialog", { name: "Є незбережені зміни" });
    expect(dialog.textContent).toContain("факту 4");
    await user.click(within(dialog).getByRole("button", { name: "Залишитись" }));
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect((within(item(4)).getByRole("textbox", { name: "Формулювання факту" }) as HTMLTextAreaElement).value).toBe("Postgres і Redis (нове)");
    expect(category("Усі 8").getAttribute("aria-pressed")).toBe("true");
  });

  test("«Відкинути зміни» застосовує фільтр і закриває редактор", async () => {
    const { user } = await dirtyEditor();
    await user.selectOptions(status(), "Підтверджені");
    await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Відкинути зміни" }));
    expect((status() as HTMLSelectElement).value).toBe("confirmed");
    expect(screen.queryByRole("form")).toBeNull();
    expect(shownIds()).toEqual([3, 1, 8, 6]);
  });

  test("пошук теж не стирає введене мовчки", async () => {
    const { user } = await dirtyEditor();
    await user.type(search(), "k");
    expect(screen.getByRole("alertdialog", { name: "Є незбережені зміни" })).toBeDefined();
    // За модальним діалогом решта сторінки схована від читачів екрана, тож поле шукаємо з `hidden`.
    expect((screen.getByRole("searchbox", { name: "Пошук фактів", hidden: true }) as HTMLInputElement).value).toBe("");
  });

  test("редактор без правок закривається при зміні фільтра без попередження", async () => {
    const { user } = await openFacts();
    await user.click(within(item(4)).getByRole("button", { name: "Редагувати факт 4" }));
    await user.click(category("Мови 1"));
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(screen.queryByRole("form")).toBeNull();
    expect(shownIds()).toEqual([7]);
  });

  test("навігація в інший розділ із правками питає; «Залишитись» лишає на «Фактах»", async () => {
    const { user } = await dirtyEditor();
    await user.click(screen.getAllByRole("link", { name: "Вакансії" })[0] as HTMLElement);
    const dialog = await screen.findByRole("alertdialog", { name: "Є незбережені зміни" });
    await user.click(within(dialog).getByRole("button", { name: "Залишитись" }));
    expect(screen.getByTestId("location").textContent).toBe("/facts");
    expect((within(item(4)).getByRole("textbox", { name: "Формулювання факту" }) as HTMLTextAreaElement).value).toBe("Postgres і Redis (нове)");
  });

  test("«Відкинути зміни» дозволяє піти", async () => {
    const { user } = await dirtyEditor();
    await user.click(screen.getAllByRole("link", { name: "Вакансії" })[0] as HTMLElement);
    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Відкинути зміни" }));
    await waitFor(() => expect(screen.getByTestId("location").textContent).toBe("/vacancies"));
  });

  test("без правок навігація вільна", async () => {
    const { user } = await openFacts();
    await user.click(within(item(4)).getByRole("button", { name: "Редагувати факт 4" }));
    await user.click(screen.getAllByRole("link", { name: "Вакансії" })[0] as HTMLElement);
    await waitFor(() => expect(screen.getByTestId("location").textContent).toBe("/vacancies"));
  });

  test("закриття вкладки з правками попереджає браузер (beforeunload), без правок — ні", async () => {
    const { user } = await openFacts();
    const fire = () => {
      const event = new Event("beforeunload", { cancelable: true });
      window.dispatchEvent(event);
      return event.defaultPrevented;
    };
    expect(fire()).toBe(false);
    await user.click(within(item(4)).getByRole("button", { name: "Редагувати факт 4" }));
    expect(fire()).toBe(false);
    await user.type(within(item(4)).getByRole("textbox", { name: "Формулювання факту" }), "!");
    expect(fire()).toBe(true);
    await user.click(within(item(4)).getByRole("button", { name: "Скасувати" }));
    expect(fire()).toBe(false);
  });
});

describe("видалення", () => {
  async function openDeleteDialog() {
    const opened = await openFacts();
    await opened.user.click(within(item(4)).getByRole("button", { name: "Редагувати факт 4" }));
    await opened.user.click(within(item(4)).getByRole("button", { name: "Видалити" }));
    return { ...opened, dialog: screen.getByRole("alertdialog", { name: "Видалити факт 4 назавжди?" }) };
  }

  test("діалог чесно каже «назавжди» і не обіцяє відновлення", async () => {
    const { dialog } = await openDeleteDialog();
    expect(dialog.textContent).toContain("Відновити його не можна");
    expect(within(dialog).queryByRole("button", { name: /Відновити|Undo/i })).toBeNull();
    expect(within(dialog).getByText("Postgres і Redis")).toBeDefined();
  });

  test("підтвердження видаляє факт, лічильники точні, повідомлення без «Відновити»", async () => {
    const { backend, user, dialog } = await openDeleteDialog();
    await user.click(within(dialog).getByRole("button", { name: "Видалити назавжди" }));
    await waitFor(() => expect(shownIds()).not.toContain(4));
    expect(backend.requests).toContain("DELETE /api/facts/4");
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(category("Скіли 2")).toBeDefined();
    expect(category("Усі 7")).toBeDefined();
    expect(within(screen.getByRole("region", { name: "Перевірка фактів" })).getByText("3 факти потребують перевірки")).toBeDefined();
    expect(messages()).toBe("Факт 4 видалено назавжди.");
    expect(screen.queryByRole("button", { name: /Відновити/ })).toBeNull();
  });

  test("«Скасувати» в діалозі лишає факт і редактор із правками", async () => {
    const { backend, user, dialog } = await openDeleteDialog();
    await user.click(within(dialog).getByRole("button", { name: "Скасувати" }));
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(within(item(4)).getByRole("form")).toBeDefined();
    expect(backend.requests).not.toContain("DELETE /api/facts/4");
  });

  test("Escape закриває діалог, фокус повертається на «Видалити»", async () => {
    const { user } = await openDeleteDialog();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(document.activeElement).toBe(within(item(4)).getByRole("button", { name: "Видалити" }));
  });

  test.each([
    ["500", 500, { code: "internal_error", message: "Внутрішня помилка", field_errors: [] }],
    ["422", 422, { code: "invalid_request", message: "Запит не пройшов перевірку", field_errors: [{ field: "fact_id", message: "x" }] }],
  ])("помилка %s: повідомлення в діалозі, факт на місці, успіх не симулюється; повтор допомагає", async (_name, code, body) => {
    const { backend, user, dialog } = await openDeleteDialog();
    backend.failNext("remove", code, body);
    await user.click(within(dialog).getByRole("button", { name: "Видалити назавжди" }));
    expect((await within(dialog).findByRole("alert")).textContent).toBe("Не вдалося видалити факт. Спробуй ще раз.");
    expect(screen.getByRole("alertdialog")).toBeDefined();
    expect(shownIds()).toContain(4);
    expect(messages()).toBe("");
    await user.click(within(dialog).getByRole("button", { name: "Видалити назавжди" }));
    await waitFor(() => expect(shownIds()).not.toContain(4));
  });

  test("факт уже зник (404) — його прибрано зі списку, діалог закрито", async () => {
    const { backend, user, dialog } = await openDeleteDialog();
    backend.facts = backend.facts.filter((fact) => fact.fact_id !== 4);
    await user.click(within(dialog).getByRole("button", { name: "Видалити назавжди" }));
    await waitFor(() => expect(shownIds()).not.toContain(4));
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  test("видалений вибраний факт зникає з вибору", async () => {
    const { user, dialog } = await openDeleteDialog();
    await user.click(within(dialog).getByRole("button", { name: "Скасувати" }));
    await user.click(within(item(4)).getByRole("button", { name: "Скасувати" }));
    await user.click(screen.getByRole("checkbox", { name: "Вибрати факт 4" }));
    await user.click(within(item(4)).getByRole("button", { name: "Редагувати факт 4" }));
    await user.click(within(item(4)).getByRole("button", { name: "Видалити" }));
    await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Видалити назавжди" }));
    await waitFor(() => expect(screen.getByText("Вибрано: 0")).toBeDefined());
  });
});

describe("довгі тексти й великі списки", () => {
  test("довгий текст без пробілів переноситься і не розпирає рядок", async () => {
    await openFacts([apiFact(1, "skill", `${"Дуже".repeat(120)}ДовгеСлово`), apiFact(2, "skill", "Коротко")]);
    const text = within(item(1)).getByText(/^Дуже/);
    expect(text.className).toContain("[overflow-wrap:anywhere]");
    expect(item(1).className).toContain("min-w-0");
  });

  // Тисяча карток у jsdom на повільному CI-раннері рендериться ~7 с: типового ліміту 5 с замало.
  test("1000 фактів: усі на місці, фільтр і підрахунок працюють", { timeout: 60_000 }, async () => {
    const kinds = ["experience", "achievement", "project", "skill", "education", "language"];
    const many = Array.from({ length: 1000 }, (_, index) => apiFact(index + 1, kinds[index % 6] as string, `Факт номер ${index + 1}`, index % 5 === 0));
    const { user } = await openFacts(many, null);
    expect(shownIds()).toHaveLength(1000);
    expect(category("Усі 1000")).toBeDefined();
    await user.click(category("Скіли 167"));
    expect(shownIds()).toHaveLength(167);
  });
});

describe("мобільний екран і доступність", () => {
  test("на вузькому екрані є ті самі категорії, фільтри й список (не таблиця)", async () => {
    setViewport("mobile");
    await openFacts();
    expect(screen.getByRole("navigation", { name: "Категорії фактів" })).toBeDefined();
    expect(screen.getByRole("list", { name: "Факти" })).toBeDefined();
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryByRole("columnheader")).toBeNull();
  });

  test("кожен керований елемент має назву, статуси — текстом", async () => {
    await openFacts();
    for (const control of [...screen.getAllByRole("button"), ...screen.getAllByRole("checkbox"), ...screen.getAllByRole("combobox"), screen.getByRole("searchbox")]) {
      expect(control.getAttribute("aria-label") ?? control.textContent ?? "").not.toBe("");
    }
    expect(within(item(2)).getByText("Потребує перевірки")).toBeDefined();
  });

  test("клавіатура: Tab доходить до пошуку, статусу, категорій і прапорців; Space вибирає, Enter відкриває редактор", async () => {
    const { user } = await openFacts();
    search().focus();
    await user.tab();
    expect(document.activeElement).toBe(status());
    await user.tab();
    expect(document.activeElement).toBe(screen.getByRole("combobox", { name: "Джерело" }));
    await user.tab();
    expect(document.activeElement).toBe(category("Усі 8"));
    category("Скіли 3").focus();
    await user.keyboard("{Enter}");
    expect(category("Скіли 3").getAttribute("aria-pressed")).toBe("true");
    const box = screen.getByRole("checkbox", { name: "Вибрати факт 4" });
    box.focus();
    await user.keyboard(" ");
    expect(screen.getByText("Вибрано: 1")).toBeDefined();
    const edit = within(item(4)).getByRole("button", { name: "Редагувати факт 4" });
    edit.focus();
    await user.keyboard("{Enter}");
    expect(within(item(4)).getByRole("form")).toBeDefined();
  });

  test("діалог видалення тримає фокус усередині й лишає «Скасувати» першою дією", async () => {
    const { user } = await openFacts();
    await user.click(within(item(4)).getByRole("button", { name: "Редагувати факт 4" }));
    await user.click(within(item(4)).getByRole("button", { name: "Видалити" }));
    const dialog = screen.getByRole("alertdialog");
    expect(dialog.contains(document.activeElement)).toBe(true);
    await user.tab();
    await user.tab();
    await user.tab();
    expect(dialog.contains(document.activeElement)).toBe(true);
  });
});

describe("джерело факту", () => {
  const MIXED: ApiFact[] = [
    apiFact(1, "skill", "Python 3.14", true),
    apiFact(2, "skill", "Вів співбесіди", true, "chat", 12),
    apiFact(3, "skill", "Docker", true, "manual"),
    apiFact(4, "project", "Бот для Telegram", false, "chat", 7),
  ];
  const sourceFilter = () => screen.getByRole("combobox", { name: "Джерело" });

  test("кожен факт має бейдж джерела: «з CV», «з чату», «вручну»", async () => {
    await openFacts(MIXED);
    expect(within(item(1)).getByText("з CV")).toBeDefined();
    expect(within(item(2)).getByText("з чату")).toBeDefined();
    expect(within(item(3)).getByText("вручну")).toBeDefined();
  });

  test("факт «з чату» має посилання на вакансію за job_id; решта — без посилання", async () => {
    await openFacts(MIXED);
    const link = within(item(2)).getByRole("link", { name: "Вакансія #12" });
    expect(link.getAttribute("href")).toBe("/vacancies/12");
    expect(within(item(4)).getByRole("link", { name: "Вакансія #7" }).getAttribute("href")).toBe("/vacancies/7");
    expect(within(item(1)).queryByRole("link")).toBeNull();
    expect(within(item(3)).queryByRole("link")).toBeNull();
  });

  test("факт «з чату» без вакансії показує бейдж без посилання", async () => {
    await openFacts([apiFact(9, "skill", "Без вакансії", true, "chat", null)]);
    expect(within(item(9)).getByText("з чату")).toBeDefined();
    expect(within(item(9)).queryByRole("link")).toBeNull();
  });

  test("фільтр за джерелом лишає лише факти цього джерела; «Усі джерела» повертає все", async () => {
    const { user } = await openFacts(MIXED);
    await user.selectOptions(sourceFilter(), "chat");
    expect(shownIds()).toEqual([4, 2]);
    await user.selectOptions(sourceFilter(), "manual");
    expect(shownIds()).toEqual([3]);
    await user.selectOptions(sourceFilter(), "cv");
    expect(shownIds()).toEqual([1]);
    await user.selectOptions(sourceFilter(), "all");
    expect(shownIds()).toEqual([4, 1, 2, 3]);
  });

  test("«Скинути фільтри» повертає і фільтр за джерелом", async () => {
    const { user } = await openFacts(MIXED);
    await user.selectOptions(sourceFilter(), "manual");
    await user.type(search(), "Python");
    await user.click(screen.getByRole("button", { name: "Скинути фільтри" }));
    expect(shownIds()).toHaveLength(4);
    expect((sourceFilter() as HTMLSelectElement).value).toBe("all");
  });
});

describe("додавання факту вручну", () => {
  const openForm = async (facts: ApiFact[] = FACTS) => {
    const opened = await openFacts(facts);
    await opened.user.click(screen.getByRole("button", { name: "Додати факт" }));
    return opened;
  };
  const form = () => screen.getByRole("form", { name: "Новий факт" });
  const fill = async (user: ReturnType<typeof userEvent.setup>, kind: string, text: string) => {
    await user.selectOptions(within(form()).getByRole("combobox", { name: "Категорія" }), kind);
    await user.type(within(form()).getByRole("textbox", { name: "Формулювання факту" }), text);
  };

  test("кнопка «Додати факт» стоїть у рядку заголовка, з іконкою «+», і ховається, поки форма відкрита", async () => {
    const { user } = await openFacts();
    const button = screen.getByRole("button", { name: "Додати факт" });

    expect(button.querySelector("svg")).not.toBeNull();
    expect(button.parentElement?.contains(screen.getByRole("heading", { level: 1, name: "Факти" }))).toBe(true);
    await user.click(button);
    expect(screen.queryByRole("button", { name: "Додати факт" })).toBeNull();
  });

  test("кнопка «Додати факт» відкриває форму з категорією й текстом", async () => {
    await openForm();
    expect(within(form()).getByRole("combobox", { name: "Категорія" })).toBeDefined();
    expect(within(form()).getByRole("textbox", { name: "Формулювання факту" })).toBeDefined();
  });

  test("успіх: POST /api/facts, факт у списку з бейджем «вручну», підтверджений, форма закрита", async () => {
    const { user, backend } = await openForm();
    await fill(user, "language", "Іспанська — C1");
    await user.click(within(form()).getByRole("button", { name: "Додати" }));
    expect(await screen.findByRole("listitem", { name: "Факт 9" })).toBeDefined();
    expect(backend.requests).toContain("POST /api/facts");
    expect(backend.bodies.at(-1)).toEqual({ kind: "language", text: "Іспанська — C1" });
    expect(within(item(9)).getByText("Іспанська — C1")).toBeDefined();
    expect(within(item(9)).getByText("вручну")).toBeDefined();
    expect(within(item(9)).getByText("Підтверджено")).toBeDefined();
    expect(screen.queryByRole("form", { name: "Новий факт" })).toBeNull();
    expect(messages()).toBe("Факт 9 додано.");
  });

  test("новий факт стає у свою категорію за порядком сервера, лічильники оновлюються", async () => {
    const { user } = await openForm();
    await fill(user, "experience", "Tech Lead у Acme");
    await user.click(within(form()).getByRole("button", { name: "Додати" }));
    await screen.findByRole("listitem", { name: "Факт 9" });
    expect(shownIds()).toEqual([3, 9, 2, 5, 1, 4, 8, 6, 7]);
    expect(within(screen.getByRole("navigation", { name: "Категорії фактів" })).getByRole("button", { name: /Досвід/ }).textContent).toContain("2");
  });

  test("422: помилка видна біля поля, форма й введене лишаються", async () => {
    const { user, backend } = await openForm();
    backend.failNext("create", 422, {
      code: "invalid_value",
      message: "Факт задовгий.",
      field_errors: [{ field: "text", message: "Факт задовгий: більше 500 символів — розбий на кілька." }],
    });
    await fill(user, "skill", "Щось");
    await user.click(within(form()).getByRole("button", { name: "Додати" }));
    const error = await within(form()).findByText("Факт задовгий: більше 500 символів — розбий на кілька.");
    const field = within(form()).getByRole("textbox", { name: "Формулювання факту" });
    expect(field.getAttribute("aria-invalid")).toBe("true");
    expect(field.getAttribute("aria-describedby")).toBe(error.id);
    expect((field as HTMLTextAreaElement).value).toBe("Щось");
  });

  test("порожній текст: сервер відхиляє, помилка біля поля, факт не додано", async () => {
    const { user } = await openForm();
    await user.click(within(form()).getByRole("button", { name: "Додати" }));
    expect(await within(form()).findByText("Факт не може бути порожнім.")).toBeDefined();
    expect(shownIds()).toHaveLength(8);
  });

  test("409: біля поля «Такий факт уже є», факт не додано", async () => {
    const { user } = await openForm();
    await fill(user, "skill", "Python 3.14");
    await user.click(within(form()).getByRole("button", { name: "Додати" }));
    expect(await within(form()).findByText(/Такий факт уже є/)).toBeDefined();
    expect(screen.getByRole("form", { name: "Новий факт" })).toBeDefined();
    expect(shownIds()).toHaveLength(8);
  });

  test("збій сервера: загальне повідомлення, введене лишається", async () => {
    const { user, backend } = await openForm();
    backend.failNext("create");
    await fill(user, "skill", "Kotlin");
    await user.click(within(form()).getByRole("button", { name: "Додати" }));
    expect((await within(form()).findByRole("alert")).textContent).toBe("Не вдалося додати факт. Чернетку збережено — спробуй ще раз.");
    expect((within(form()).getByRole("textbox", { name: "Формулювання факту" }) as HTMLTextAreaElement).value).toBe("Kotlin");
  });

  test("«Скасувати» закриває форму без запиту", async () => {
    const { user, backend } = await openForm();
    await fill(user, "skill", "Kotlin");
    await user.click(within(form()).getByRole("button", { name: "Скасувати" }));
    expect(screen.queryByRole("form", { name: "Новий факт" })).toBeNull();
    expect(backend.requests).not.toContain("POST /api/facts");
  });

  test("кнопка є і коли фактів ще немає", async () => {
    const { user } = await openFacts([]);
    await user.click(screen.getByRole("button", { name: "Додати факт" }));
    await fill(user, "skill", "Go");
    await user.click(within(form()).getByRole("button", { name: "Додати" }));
    expect(await screen.findByRole("listitem", { name: "Факт 1" })).toBeDefined();
  });
});
