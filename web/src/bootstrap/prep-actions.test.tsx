/** «Підготовка» `/prep/{n}`: «Виконано» з нотаткою, «Зберегти нотатку», 422 біля поля, «Тема готова» / «Зняти позначку», збої дій. */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { ddd, LONG_NOTE } from "./prepFixtures";
import { prepBackend, problem, type PrepOverrides } from "./prepBackend";
import { openTopic, stepOf } from "./prepHarness";
import { json } from "./testClient";

async function open(overrides: PrepOverrides = {}) {
  const backend = prepBackend({ topics: [ddd()] }, overrides);
  await openTopic(backend, "/prep/7");
  await screen.findByRole("heading", { level: 2, name: "План теми" });
  return { backend, user: userEvent.setup() };
}

const result = () => screen.getByRole("status", { name: "Результат" });
const noteOf = (step: HTMLElement) => within(step).getByRole("textbox", { name: /Нотатка/ }) as HTMLTextAreaElement;

describe("«Позначити виконаним»", () => {
  test("з нотаткою: POST /prep/steps/32/done з нею, крок стає виконаним із днем за Мадридом, прогрес оновлюється", async () => {
    const { backend, user } = await open();
    const step = stepOf("Агрегати та інваріанти");

    await user.type(noteOf(step), "Розібрав межі агрегатів");
    await user.click(within(step).getByRole("button", { name: "Позначити виконаним" }));

    await waitFor(() => expect(within(step).getByRole("button", { name: "Зберегти нотатку" })).toBeDefined());
    expect(backend.bodies["POST /api/prep/steps/32/done"]).toEqual([{ note: "Розібрав межі агрегатів" }]);
    expect(step.querySelector("summary")?.textContent).toContain("виконано 2026-10-27");
    expect(within(step).getByText("Розібрав межі агрегатів", { selector: "div" })).toBeDefined();
    expect(step.open).toBe(true);
    expect(screen.getByText("50%")).toBeDefined();
    expect(screen.getByText("2/4 кроків")).toBeDefined();
    expect(screen.getByText("Лишилось ~150 хв")).toBeDefined();
    expect(result().textContent).toBe("Збережено. Прогрес і залишок часу оновлено.");
  });

  test("без нотатки: на сервер іде порожній рядок, виконаний крок показує «Без нотатки»", async () => {
    const { backend, user } = await open();
    const step = stepOf("Агрегати та інваріанти");

    await user.click(within(step).getByRole("button", { name: "Позначити виконаним" }));

    await waitFor(() => expect(within(step).getByText("Без нотатки")).toBeDefined());
    expect(backend.bodies["POST /api/prep/steps/32/done"]).toEqual([{ note: "" }]);
  });

  test("поки запит іде, кнопка вимкнена: повторне натискання не шле другий запит", async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const { backend, user } = await open({ done: () => gate.then(() => json(200, ddd())) });
    const step = stepOf("Агрегати та інваріанти");
    const button = within(step).getByRole("button", { name: "Позначити виконаним" }) as HTMLButtonElement;

    await user.click(button);
    await user.click(button);

    expect(button.disabled).toBe(true);
    expect(backend.bodies["POST /api/prep/steps/32/done"]).toHaveLength(1);
    release();
    // Після відповіді форма створюється наново, тож кнопку шукаємо знову.
    await waitFor(() => expect((within(step).getByRole("button", { name: "Позначити виконаним" }) as HTMLButtonElement).disabled).toBe(false));
  });
});

describe("«Зберегти нотатку» виконаного кроку", () => {
  test("поле має чинну нотатку; зміна замінює її, а день першого виконання лишається", async () => {
    const { backend, user } = await open();
    const step = stepOf("Межі контекстів");

    expect(noteOf(step).value).toBe(LONG_NOTE);
    await user.clear(noteOf(step));
    await user.type(noteOf(step), "Нова нотатка");
    await user.click(within(step).getByRole("button", { name: "Зберегти нотатку" }));

    await waitFor(() => expect(within(step).getByText("Нова нотатка", { selector: "div" })).toBeDefined());
    expect(backend.bodies["POST /api/prep/steps/31/done"]).toEqual([{ note: "Нова нотатка" }]);
    expect(step.querySelector("summary")?.textContent).toContain("виконано 2026-10-25");
    expect(screen.getByText("25%")).toBeDefined();
    expect(result().textContent).toBe("Збережено. Прогрес і залишок часу оновлено.");
  });

  test("порожня нотатка стару не стирає: сервер її лишає, і поле знову показує її", async () => {
    const { user } = await open();
    const step = stepOf("Межі контекстів");

    await user.clear(noteOf(step));
    await user.click(within(step).getByRole("button", { name: "Зберегти нотатку" }));

    await waitFor(() => expect(noteOf(step).value).toBe(LONG_NOTE));
    expect(within(step).getByText(LONG_NOTE, { selector: "div" })).toBeDefined();
  });
});

describe("помилки дій", () => {
  test("нотатка задовга (422): текст сервера біля поля, поле позначене помилкою, нічого не змінилось", async () => {
    const { user } = await open();
    const step = stepOf("Агрегати та інваріанти");

    await user.click(noteOf(step));
    await user.paste("a".repeat(2001));
    await user.click(within(step).getByRole("button", { name: "Позначити виконаним" }));

    const error = await within(step).findByText("Нотатка — до 2000 символів.");
    expect(error.id).not.toBe("");
    expect(noteOf(step).getAttribute("aria-invalid")).toBe("true");
    expect(noteOf(step).getAttribute("aria-describedby")).toContain(error.id);
    expect(noteOf(step).value).toHaveLength(2001);
    expect(within(step).getByRole("button", { name: "Позначити виконаним" })).toBeDefined();
    expect(screen.getByText("25%")).toBeDefined();
  });

  test("після виправлення нотатки помилка біля поля зникає", async () => {
    const { user } = await open();
    const step = stepOf("Агрегати та інваріанти");
    await user.click(noteOf(step));
    await user.paste("a".repeat(2001));
    await user.click(within(step).getByRole("button", { name: "Позначити виконаним" }));
    await within(step).findByText("Нотатка — до 2000 символів.");

    await user.clear(noteOf(step));
    await user.type(noteOf(step), "Коротко");
    await user.click(within(step).getByRole("button", { name: "Позначити виконаним" }));

    await waitFor(() => expect(within(step).queryByText("Нотатка — до 2000 символів.")).toBeNull());
    expect(noteOf(step).getAttribute("aria-invalid")).toBeNull();
    expect(within(step).getByRole("button", { name: "Зберегти нотатку" })).toBeDefined();
  });

  test("сервер недоступний: повідомлення, нотатка в полі збережена для повтору", async () => {
    const { user } = await open({ done: () => problem(500, "internal", "Збій") });
    const step = stepOf("Агрегати та інваріанти");

    await user.type(noteOf(step), "Не загубити");
    await user.click(within(step).getByRole("button", { name: "Позначити виконаним" }));

    await waitFor(() => expect(result().textContent).toBe("Не вдалося зберегти. Спробуй ще раз."));
    expect(noteOf(step).value).toBe("Не загубити");
    expect((within(step).getByRole("button", { name: "Позначити виконаним" }) as HTMLButtonElement).disabled).toBe(false);
  });

  test("сесія завершилась (401): підказка увійти знову", async () => {
    const { user } = await open({ done: () => problem(401, "not_authenticated", "Потрібен вхід") });

    await user.click(within(stepOf("Агрегати та інваріанти")).getByRole("button", { name: "Позначити виконаним" }));

    await waitFor(() => expect(result().textContent).toBe("Сесія завершилась. Увійди знову, щоб зберегти нотатку."));
  });

  test("кроку вже нема (404): повідомлення, а тема перезавантажується й показує актуальні кроки", async () => {
    const refreshed = ddd();
    refreshed.steps = refreshed.steps.filter((step) => step.step_id !== 32);
    let loads = 0;
    const { backend, user } = await open({
      topic: () => (++loads === 1 ? undefined : json(200, refreshed)),
      done: () => problem(404, "not_found", "Не знайдено"),
    });

    await user.click(within(stepOf("Агрегати та інваріанти")).getByRole("button", { name: "Позначити виконаним" }));

    await waitFor(() => expect(screen.queryByText("Агрегати та інваріанти", { selector: "strong" })).toBeNull());
    expect(result().textContent).toBe("Цього кроку вже немає — тему оновлено.");
    expect(backend.requests.filter((request) => request === "GET /api/prep/topics/7")).toHaveLength(2);
  });

  test("теми вже нема (404 і після перезавантаження): «Тему не знайдено»", async () => {
    let loads = 0;
    const { user } = await open({
      topic: () => (++loads === 1 ? undefined : problem(404, "not_found", "Не знайдено")),
      done: () => problem(404, "not_found", "Не знайдено"),
    });

    await user.click(within(stepOf("Агрегати та інваріанти")).getByRole("button", { name: "Позначити виконаним" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Тему не знайдено" })).toBeDefined();
  });
});

describe("«Тема готова» / «Зняти позначку»", () => {
  test("«Тема готова»: PUT {ready:true}, 100 %, бейдж «Готово», кроки не змінились, повідомлення в role=status", async () => {
    const { backend, user } = await open();

    await user.click(screen.getByRole("button", { name: "Тема готова" }));

    expect(await screen.findByRole("button", { name: "Зняти позначку" })).toBeDefined();
    expect(backend.bodies["PUT /api/prep/topics/7/ready"]).toEqual([{ ready: true }]);
    expect(screen.getByText("100%")).toBeDefined();
    expect(screen.getByText("Готово")).toBeDefined();
    expect(screen.getByText("1/4 кроків")).toBeDefined();
    expect(screen.getByRole("heading", { level: 3, name: "Тему позначено готовою" })).toBeDefined();
    expect(result().textContent).toBe("Тему позначено готовою.");
  });

  test("«Зняти позначку»: PUT {ready:false}, статус і % знову з кроків", async () => {
    const { backend, user } = await open();
    await user.click(screen.getByRole("button", { name: "Тема готова" }));

    await user.click(await screen.findByRole("button", { name: "Зняти позначку" }));

    expect(await screen.findByRole("button", { name: "Тема готова" })).toBeDefined();
    expect(backend.bodies["PUT /api/prep/topics/7/ready"]).toEqual([{ ready: true }, { ready: false }]);
    expect(screen.getByText("25%")).toBeDefined();
    expect(screen.getByText("Вивчаю")).toBeDefined();
    expect(result().textContent).toBe("Позначку знято. Готовність обчислено за кроками.");
  });

  test("поки запит іде, кнопка вимкнена", async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const { backend, user } = await open({ ready: () => gate.then(() => json(200, ddd())) });
    const button = screen.getByRole("button", { name: "Тема готова" }) as HTMLButtonElement;

    await user.click(button);
    await user.click(button);

    expect(button.disabled).toBe(true);
    expect(backend.bodies["PUT /api/prep/topics/7/ready"]).toHaveLength(1);
    release();
    await waitFor(() => expect(button.disabled).toBe(false));
  });

  test("сервер недоступний: повідомлення, стан теми не змінюється", async () => {
    const { user } = await open({ ready: () => problem(500, "internal", "Збій") });

    await user.click(screen.getByRole("button", { name: "Тема готова" }));

    await waitFor(() => expect(result().textContent).toBe("Не вдалося змінити готовність. Спробуй ще раз."));
    expect(screen.getByRole("button", { name: "Тема готова" })).toBeDefined();
    expect(screen.getByText("25%")).toBeDefined();
  });

  test("сесія завершилась (401): підказка увійти знову", async () => {
    const { user } = await open({ ready: () => problem(401, "not_authenticated", "Потрібен вхід") });

    await user.click(screen.getByRole("button", { name: "Тема готова" }));

    await waitFor(() => expect(result().textContent).toBe("Сесія завершилась. Увійди знову, щоб змінити готовність."));
  });

  test("теми вже нема (404): «Тему не знайдено»", async () => {
    let loads = 0;
    const { user } = await open({
      topic: () => (++loads === 1 ? undefined : problem(404, "not_found", "Не знайдено")),
      ready: () => problem(404, "not_found", "Не знайдено"),
    });

    await user.click(screen.getByRole("button", { name: "Тема готова" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Тему не знайдено" })).toBeDefined();
  });
});

describe("повідомлення про результат", () => {
  test("область role=status порожня, поки дій не було", async () => {
    await open();

    expect(result().textContent).toBe("");
  });

  test("нова дія стирає повідомлення про попередню", async () => {
    const { user } = await open();
    await user.click(screen.getByRole("button", { name: "Тема готова" }));
    await screen.findByText("Тему позначено готовою.");

    await user.click(within(stepOf("Агрегати та інваріанти")).getByRole("button", { name: "Позначити виконаним" }));

    await waitFor(() => expect(result().textContent).toBe("Збережено. Прогрес і залишок часу оновлено."));
  });
});
