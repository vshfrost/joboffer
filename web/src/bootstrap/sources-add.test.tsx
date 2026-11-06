/** «Додати джерело»: компанія чи RSS-стрічка, помилки 422 біля поля, форма лишається заповненою, діалог «Закрити форму?». */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { detailsOf, openSources, rowOf, sourceNames } from "./sourcesHarness";
import { apiCompany, apiFeed, problem, sourceId, sourcesBackend } from "./sourcesBackend";
import { json, renderClient } from "./testClient";
import { setViewport } from "./viewport";

const location = () => screen.getByTestId("location").textContent;

async function openForm(backend = sourcesBackend({ companies: [apiCompany(1, { name: "Northstar" })], feeds: [apiFeed(21)] }), path = "/sources/new") {
  setViewport("desktop");
  renderClient(path, backend.fetchFn);
  await screen.findByRole("heading", { level: 1, name: "Додати джерело" });
  return backend;
}

const slugField = () => screen.getByRole("textbox", { name: "Слаг компанії" }) as HTMLInputElement;
const nameField = () => screen.getByRole("textbox", { name: "Назва компанії · необов’язково" }) as HTMLInputElement;
const queryField = () => screen.getByRole("textbox", { name: "Параметри запиту" }) as HTMLInputElement;

describe("форма", () => {
  test("із посилання «Додати джерело»: заголовок, «← До джерел», тип «Компанія» вибрано", async () => {
    setViewport("desktop");
    const user = userEvent.setup();
    const backend = sourcesBackend({ companies: [apiCompany(1)] });
    renderClient("/sources", backend.fetchFn);
    await user.click(await screen.findByRole("link", { name: "Додати джерело" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Додати джерело" })).toBeDefined();
    expect(location()).toBe("/sources/new");
    expect(document.title).toBe("Додати джерело · joboffer");
    expect(screen.getByText("Компанію перед додаванням перевіряє пробний запит до платформи.")).toBeDefined();
    const types = screen.getByRole("tablist", { name: "Тип нового джерела" });
    expect(within(types).getByRole("tab", { name: "Компанія", selected: true })).toBeDefined();
    expect(within(types).getByRole("tab", { name: "RSS-стрічка", selected: false })).toBeDefined();
  });

  test("компанія: платформа, слаг з підказкою, необов’язкова назва, кнопки", async () => {
    await openForm();

    const platform = screen.getByRole("combobox", { name: "ATS-платформа" });
    expect(within(platform).getAllByRole("option").map((option) => option.textContent)).toEqual(["Greenhouse", "Ashby", "Lever"]);
    expect(slugField().getAttribute("aria-describedby")).not.toBeNull();
    expect(screen.getByText("Остання частина адреси сторінки вакансій. Наприклад, jobs.ashbyhq.com/acme → acme.")).toBeDefined();
    expect(screen.getByText("Без назви буде використано слаг.")).toBeDefined();
    expect(screen.getByRole("button", { name: "Перевірити й додати" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Скасувати" })).toBeDefined();
    expect(screen.getByRole("button", { name: "← До джерел" })).toBeDefined();
  });

  test("RSS-стрічка: джерело DOU / Djinni й параметри запиту з підказкою", async () => {
    const user = userEvent.setup();
    await openForm();

    await user.click(screen.getByRole("tab", { name: "RSS-стрічка" }));

    const source = screen.getByRole("combobox", { name: "RSS-джерело" });
    expect(within(source).getAllByRole("option").map((option) => option.textContent)).toEqual(["DOU", "Djinni"]);
    expect(queryField().getAttribute("placeholder")).toBe("category=Python&remote");
    expect(screen.getByText("Без пробілів. DOU: category=Python&remote · Djinni: primary_keyword=Python&exp_level=5y")).toBeDefined();
    expect(screen.getByRole("button", { name: "Додати стрічку" })).toBeDefined();
    expect(screen.queryByRole("textbox", { name: "Слаг компанії" })).toBeNull();
    await user.selectOptions(source, "Djinni");
    expect(queryField().getAttribute("placeholder")).toBe("primary_keyword=Python");
  });

  test("вкладка зі списку (?tab=feeds) відкриває форму стрічки", async () => {
    await openForm(undefined, "/sources/new?tab=feeds");

    expect(screen.getByRole("tab", { name: "RSS-стрічка", selected: true })).toBeDefined();
    expect(queryField()).toBeDefined();
  });

  test("перемикання типу очищає введене й помилки", async () => {
    const user = userEvent.setup();
    await openForm();
    await user.type(slugField(), "missing-co");
    await user.click(screen.getByRole("button", { name: "Перевірити й додати" }));
    await screen.findByText("Компанії зі слагом «missing-co» на greenhouse не знайдено.");

    await user.click(screen.getByRole("tab", { name: "RSS-стрічка" }));
    await user.click(screen.getByRole("tab", { name: "Компанія" }));

    expect(slugField().value).toBe("");
    expect(slugField().getAttribute("aria-invalid")).toBeNull();
    expect(screen.queryByText("Компанії зі слагом «missing-co» на greenhouse не знайдено.")).toBeNull();
  });
});

describe("додати компанію", () => {
  test("успіх: POST із полями форми, список компаній із новою розгорнутою у стані «Ще не оновлювалось»", async () => {
    const user = userEvent.setup();
    const backend = await openForm();
    await user.selectOptions(screen.getByRole("combobox", { name: "ATS-платформа" }), "Ashby");
    await user.type(slugField(), "acme");
    await user.type(nameField(), "Acme Inc");

    await user.click(screen.getByRole("button", { name: "Перевірити й додати" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Джерела вакансій" })).toBeDefined();
    expect(backend.bodies["POST /api/sources/companies"]).toEqual([{ platform: "ashby", slug: "acme", name: "Acme Inc" }]);
    expect(location()).toBe(`/sources?open=${sourceId(101)}`);
    expect(await sourceNames()).toEqual(["Northstar", "Acme Inc"]);
    const toggle = within(await rowOf("Acme Inc")).getByRole("button", { name: "Acme Inc" });
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(within(await detailsOf("Acme Inc")).getByText("Ще не оновлювалось")).toBeDefined();
    expect(screen.getByRole("status", { name: "Результат" }).textContent).toBe("Джерело додано. Перший прогін ще не виконувався.");
    expect(screen.getByRole("tab", { name: "Компанії · 2" })).toBeDefined();
  });

  test("без назви використовується слаг; пробіли навколо значень обрізаються", async () => {
    const user = userEvent.setup();
    const backend = await openForm();
    await user.type(slugField(), "  acme  ");

    await user.click(screen.getByRole("button", { name: "Перевірити й додати" }));

    await screen.findByRole("heading", { level: 1, name: "Джерела вакансій" });
    expect(backend.bodies["POST /api/sources/companies"]).toEqual([{ platform: "greenhouse", slug: "acme", name: "" }]);
    expect(await sourceNames()).toContain("acme");
  });

  test("Enter у полі відправляє форму", async () => {
    const user = userEvent.setup();
    const backend = await openForm();

    await user.type(slugField(), "acme{Enter}");

    await screen.findByRole("heading", { level: 1, name: "Джерела вакансій" });
    expect(backend.bodies["POST /api/sources/companies"]).toHaveLength(1);
  });

  test("422: текст сервера біля слагу з aria-invalid, aria-describedby і фокусом; форма лишається заповненою", async () => {
    const user = userEvent.setup();
    const backend = await openForm();
    await user.selectOptions(screen.getByRole("combobox", { name: "ATS-платформа" }), "Lever");
    await user.type(slugField(), "missing-co");
    await user.type(nameField(), "Missing Co");

    await user.click(screen.getByRole("button", { name: "Перевірити й додати" }));

    const text = await screen.findByText("Компанії зі слагом «missing-co» на lever не знайдено.");
    const field = slugField();
    expect(field.getAttribute("aria-invalid")).toBe("true");
    const describedBy = (field.getAttribute("aria-describedby") ?? "").split(" ");
    expect(describedBy).toContain(text.id);
    expect(document.activeElement).toBe(field);
    expect(field.value).toBe("missing-co");
    expect(nameField().value).toBe("Missing Co");
    expect((screen.getByRole("combobox", { name: "ATS-платформа" }) as HTMLSelectElement).value).toBe("lever");
    expect(location()).toBe("/sources/new");
    expect(backend.companies).toHaveLength(1);
  });

  test("422 про недоступну перевірку (таймаут) показується біля слагу так само", async () => {
    const user = userEvent.setup();
    await openForm();
    await user.type(slugField(), "slow-co");

    await user.click(screen.getByRole("button", { name: "Перевірити й додати" }));

    expect(await screen.findByText("Не вдалося перевірити слаг (timeout) — спробуй пізніше.")).toBeDefined();
    expect(slugField().getAttribute("aria-invalid")).toBe("true");
  });

  test("422 про дубль і про неприпустимий слаг", async () => {
    const user = userEvent.setup();
    await openForm(sourcesBackend({ companies: [apiCompany(1, { slug: "northstar-eng" })] }));
    await user.type(slugField(), "northstar-eng");
    await user.click(screen.getByRole("button", { name: "Перевірити й додати" }));
    expect(await screen.findByText("Така компанія вже є в списку.")).toBeDefined();

    await user.clear(slugField());
    await user.type(slugField(), "bad slug");
    await user.click(screen.getByRole("button", { name: "Перевірити й додати" }));
    expect(await screen.findByText("Слаг компанії — літери, цифри, крапка, дефіс і підкреслення.")).toBeDefined();
    expect(screen.queryByText("Така компанія вже є в списку.")).toBeNull();
  });

  test("422 біля платформи й назви показується біля своїх полів", async () => {
    const user = userEvent.setup();
    await openForm(
      sourcesBackend(
        {},
        {
          add: () =>
            problem(422, "invalid_value", "Запит не пройшов перевірку", [
              { field: "platform", message: "Невідома платформа." },
              { field: "name", message: "Назва компанії — не довша за 200 символів." },
            ]),
        },
      ),
    );
    await user.type(slugField(), "acme");

    await user.click(screen.getByRole("button", { name: "Перевірити й додати" }));

    expect(await screen.findByText("Невідома платформа.")).toBeDefined();
    expect(screen.getByRole("combobox", { name: "ATS-платформа" }).getAttribute("aria-invalid")).toBe("true");
    expect(nameField().getAttribute("aria-invalid")).toBe("true");
    expect(document.activeElement).toBe(screen.getByRole("combobox", { name: "ATS-платформа" }));
  });

  test("поле, яке змінили, перестає бути помилковим", async () => {
    const user = userEvent.setup();
    await openForm();
    await user.type(slugField(), "missing-co");
    await user.click(screen.getByRole("button", { name: "Перевірити й додати" }));
    await screen.findByText("Компанії зі слагом «missing-co» на greenhouse не знайдено.");

    await user.type(slugField(), "x");

    expect(screen.queryByText("Компанії зі слагом «missing-co» на greenhouse не знайдено.")).toBeNull();
    expect(slugField().getAttribute("aria-invalid")).toBeNull();
  });

  test("поки йде перевірка, кнопка неактивна: два кліки — один запит", async () => {
    const user = userEvent.setup();
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const backend = sourcesBackend({}, { add: () => gate.then(() => json(201, apiCompany(100, { slug: "acme", name: "acme", last_run: null }))) });
    await openForm(backend);
    await user.type(slugField(), "acme");

    await user.click(screen.getByRole("button", { name: "Перевірити й додати" }));
    const pending = screen.getByRole("button", { name: "Перевірити й додати" }) as HTMLButtonElement;
    expect(pending.disabled).toBe(true);
    await user.click(pending);
    release();

    await screen.findByRole("heading", { level: 1, name: "Джерела вакансій" });
    expect(backend.bodies["POST /api/sources/companies"]).toHaveLength(1);
  });

  test("після відмови кнопка знову активна", async () => {
    const user = userEvent.setup();
    await openForm();
    await user.type(slugField(), "missing-co");

    await user.click(screen.getByRole("button", { name: "Перевірити й додати" }));

    await screen.findByText("Компанії зі слагом «missing-co» на greenhouse не знайдено.");
    expect((screen.getByRole("button", { name: "Перевірити й додати" }) as HTMLButtonElement).disabled).toBe(false);
  });

  test("422 без відомого поля: загальний текст у role=alert, форма лишається", async () => {
    const user = userEvent.setup();
    await openForm(sourcesBackend({}, { add: () => problem(422, "invalid_request", "Запит не пройшов перевірку", [{ field: "request", message: "Невірний запит" }]) }));
    await user.type(slugField(), "acme");

    await user.click(screen.getByRole("button", { name: "Перевірити й додати" }));

    expect((await screen.findByRole("alert")).textContent).toBe("Запит не пройшов перевірку");
    expect(slugField().value).toBe("acme");
  });

  test("збій сервера: загальне повідомлення, форма лишається заповненою", async () => {
    const user = userEvent.setup();
    await openForm(sourcesBackend({}, { add: () => problem(500, "internal_error", "Внутрішня помилка.") }));
    await user.type(slugField(), "acme");

    await user.click(screen.getByRole("button", { name: "Перевірити й додати" }));

    expect((await screen.findByRole("alert")).textContent).toBe("Не вдалося додати джерело. Спробуй ще раз.");
    expect(slugField().value).toBe("acme");
  });

  test("сесія завершилась: повідомлення про вхід", async () => {
    const user = userEvent.setup();
    await openForm(sourcesBackend({}, { add: () => problem(401, "not_authenticated", "Потрібен вхід") }));
    await user.type(slugField(), "acme");

    await user.click(screen.getByRole("button", { name: "Перевірити й додати" }));

    expect((await screen.findByRole("alert")).textContent).toBe("Сесія завершилась. Увійди знову, щоб додати джерело.");
  });
});

describe("додати стрічку", () => {
  test("успіх: список стрічок із новою розгорнутою у стані «Ще не оновлювалось»", async () => {
    const user = userEvent.setup();
    const backend = await openForm(undefined, "/sources/new?tab=feeds");
    await user.selectOptions(screen.getByRole("combobox", { name: "RSS-джерело" }), "Djinni");
    await user.type(queryField(), "primary_keyword=Python");

    await user.click(screen.getByRole("button", { name: "Додати стрічку" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Джерела вакансій" })).toBeDefined();
    expect(backend.bodies["POST /api/sources/feeds"]).toEqual([{ source: "djinni", query: "primary_keyword=Python" }]);
    expect(location()).toBe(`/sources?tab=feeds&open=${sourceId(201)}`);
    expect(await screen.findByRole("tab", { name: "RSS-стрічки · 2", selected: true })).toBeDefined();
    expect(await sourceNames()).toEqual(["DOU · category=Python&remote", "Djinni · primary_keyword=Python"]);
    expect(within(await detailsOf("Djinni · primary_keyword=Python")).getByText("Ще не оновлювалось")).toBeDefined();
  });

  test("422 біля параметрів: aria-invalid, aria-describedby, фокус, введене лишається", async () => {
    const user = userEvent.setup();
    await openForm(undefined, "/sources/new?tab=feeds");
    await user.type(queryField(), "remote");

    await user.click(screen.getByRole("button", { name: "Додати стрічку" }));

    const text = await screen.findByText("Для стрічки dou потрібен параметр category=…");
    expect(queryField().getAttribute("aria-invalid")).toBe("true");
    expect((queryField().getAttribute("aria-describedby") ?? "").split(" ")).toContain(text.id);
    expect(document.activeElement).toBe(queryField());
    expect(queryField().value).toBe("remote");
  });

  test("422 про дубль стрічки", async () => {
    const user = userEvent.setup();
    await openForm(undefined, "/sources/new?tab=feeds");
    await user.type(queryField(), "category=Python&remote");

    await user.click(screen.getByRole("button", { name: "Додати стрічку" }));

    expect(await screen.findByText("Така стрічка вже є в списку.")).toBeDefined();
  });

  test("422 біля джерела стрічки", async () => {
    const user = userEvent.setup();
    await openForm(sourcesBackend({}, { add: () => problem(422, "invalid_value", "Невідоме джерело стрічки.", [{ field: "source", message: "Невідоме джерело стрічки." }]) }), "/sources/new?tab=feeds");
    await user.type(queryField(), "category=Python");

    await user.click(screen.getByRole("button", { name: "Додати стрічку" }));

    expect(await screen.findByText("Невідоме джерело стрічки.")).toBeDefined();
    expect(screen.getByRole("combobox", { name: "RSS-джерело" }).getAttribute("aria-invalid")).toBe("true");
  });
});

describe("вихід із форми", () => {
  test("порожня форма закривається без питань: «← До джерел» і «Скасувати»", async () => {
    const user = userEvent.setup();
    await openForm();

    await user.click(screen.getByRole("button", { name: "← До джерел" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Джерела вакансій" })).toBeDefined();
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(location()).toBe("/sources");
  });

  test("«Скасувати» повертає на вкладку, з якої відкрили форму", async () => {
    const user = userEvent.setup();
    await openForm(undefined, "/sources/new?tab=feeds");

    await user.click(screen.getByRole("button", { name: "Скасувати" }));

    await screen.findByRole("heading", { level: 1, name: "Джерела вакансій" });
    expect(location()).toBe("/sources?tab=feeds");
  });

  test("заповнена форма: «Закрити форму?» — «Скасувати» лишає введене, «Закрити» виходить", async () => {
    const user = userEvent.setup();
    await openForm();
    await user.type(slugField(), "acme");

    await user.click(screen.getByRole("button", { name: "← До джерел" }));

    const dialog = await screen.findByRole("alertdialog", { name: "Закрити форму?" });
    expect(within(dialog).getByText("Введені дані не буде збережено.")).toBeDefined();
    await user.click(within(dialog).getByRole("button", { name: "Скасувати" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect(slugField().value).toBe("acme");
    expect(location()).toBe("/sources/new");

    await user.click(screen.getByRole("button", { name: "Скасувати" }));
    await user.click(within(await screen.findByRole("alertdialog", { name: "Закрити форму?" })).getByRole("button", { name: "Закрити" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Джерела вакансій" })).toBeDefined();
    expect(location()).toBe("/sources");
  });

  test("заповнена лише назва — теж питає; перехід через меню — теж", async () => {
    const user = userEvent.setup();
    await openForm();
    await user.type(nameField(), "Acme");

    await user.click(screen.getByRole("link", { name: "Вакансії" }));

    expect(await screen.findByRole("alertdialog", { name: "Закрити форму?" })).toBeDefined();
    expect(location()).toBe("/sources/new");
  });

  test("успішне додавання не питає «Закрити форму?»", async () => {
    const user = userEvent.setup();
    await openForm();
    await user.type(slugField(), "acme");

    await user.click(screen.getByRole("button", { name: "Перевірити й додати" }));

    await screen.findByRole("heading", { level: 1, name: "Джерела вакансій" });
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  test("закриття вкладки із заповненою формою просить підтвердження (beforeunload)", async () => {
    const user = userEvent.setup();
    await openForm();
    const clean = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(clean);
    expect(clean.defaultPrevented).toBe(false);
    await user.type(slugField(), "acme");

    const dirty = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(dirty);

    expect(dirty.defaultPrevented).toBe(true);
  });
});

describe("з реєстру", () => {
  test("«Додати джерело» зі вкладки RSS веде на форму стрічки", async () => {
    const user = userEvent.setup();
    const backend = sourcesBackend({ feeds: [apiFeed(21)] });
    await openSources(backend, "/sources?tab=feeds");

    await user.click(screen.getByRole("link", { name: "Додати джерело" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Додати джерело" })).toBeDefined();
    expect(screen.getByRole("tab", { name: "RSS-стрічка", selected: true })).toBeDefined();
  });
});
