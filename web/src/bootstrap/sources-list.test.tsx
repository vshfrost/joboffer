/** «Джерела»: вкладки з кількістю, рядки реєстру, пошук і фільтр стану, порожні стани, завантаження й помилки. Усе живе в адресі сторінки. */
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { rowOf, openSources, sourceList, sourceNames } from "./sourcesHarness";
import { apiCompany, apiFeed, apiRun, sourcesBackend, problem } from "./sourcesBackend";
import { json, renderClient } from "./testClient";
import { setViewport } from "./viewport";

const COMPANIES = [
  apiCompany(1, { name: "Northstar", slug: "northstar-eng", platform: "greenhouse" }),
  apiCompany(2, { name: "LumaPay", slug: "lumapay", platform: "ashby", last_run: apiRun({ ran_at: "2026-12-01T10:05:00Z", imported: 0 }) }),
  apiCompany(3, { name: "Orbit Labs", slug: "orbit", platform: "lever", last_run: apiRun({ error: "timeout" }) }),
  apiCompany(4, { name: "Cloudline", slug: "cloudline", platform: "ashby", enabled: false }),
  apiCompany(5, { name: "Nova Works", slug: "nova", platform: "lever", last_run: null }),
];
const FEEDS = [
  apiFeed(21, { source: "dou", query: "category=Python&remote" }),
  apiFeed(22, { source: "djinni", query: "primary_keyword=Python&exp_level=5y", last_run: null }),
];

const location = () => screen.getByTestId("location").textContent;

describe("сторінка", () => {
  test("заголовок, опис, назва вкладки браузера й посилання «Додати джерело»", async () => {
    await openSources(sourcesBackend({ companies: COMPANIES }));

    expect(screen.getByText("Компанії та стрічки, з яких joboffer знаходить вакансії.")).toBeDefined();
    expect(document.title).toBe("Джерела · joboffer");
    expect(screen.getByRole("link", { name: "Додати джерело" }).getAttribute("href")).toBe("/sources/new");
  });

  test("«Джерела» у навігації веде на справжню сторінку, а не на «Розділ ще в розробці»", async () => {
    setViewport("desktop");
    const backend = sourcesBackend({ companies: COMPANIES });
    renderClient("/vacancies", backend.fetchFn);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("link", { name: "Джерела" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Джерела вакансій" })).toBeDefined();
    expect(await screen.findByRole("tablist", { name: "Види джерел" })).toBeDefined();
    expect(screen.queryByText("Розділ ще в розробці")).toBeNull();
    expect(location()).toBe("/sources");
  });

  test("поки джерела вантажаться — статус зі скелетоном, потім реєстр", async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const backend = sourcesBackend(
      { companies: COMPANIES },
      { overview: () => gate.then(() => json(200, { companies: COMPANIES, feeds: [], refresh: backend.refresh, filtered_out_count: 0 })) },
    );
    await openSources(backend, "/sources", "desktop", false);

    expect(screen.getByRole("status", { name: "Завантажуємо джерела" })).toBeDefined();
    release();
    expect(await sourceNames()).toHaveLength(5);
    expect(screen.queryByRole("status", { name: "Завантажуємо джерела" })).toBeNull();
  });

  test("пояснення «Як працює відбір вакансій» згорнуте під реєстром", async () => {
    await openSources(sourcesBackend({ companies: COMPANIES }));

    const disclosure = screen.getByText("Як працює відбір вакансій").closest("details");
    expect(disclosure?.open).toBe(false);
    expect(within(disclosure as HTMLElement).getByText(/Керування кар’єрною ціллю, локаціями та правилами відбору — у розділі «Профіль»\./)).toBeDefined();
  });
});

describe("вкладки", () => {
  test("«Компанії · N» і «RSS-стрічки · N» з кількістю; за замовчуванням вибрано компанії", async () => {
    await openSources(sourcesBackend({ companies: COMPANIES, feeds: FEEDS }));

    const tabs = screen.getByRole("tablist", { name: "Види джерел" });
    expect(within(tabs).getByRole("tab", { name: "Компанії · 5", selected: true })).toBeDefined();
    expect(within(tabs).getByRole("tab", { name: "RSS-стрічки · 2", selected: false })).toBeDefined();
    expect(await sourceNames()).toEqual(["Northstar", "LumaPay", "Orbit Labs", "Cloudline", "Nova Works"]);
  });

  test("«RSS-стрічки» показує стрічки й пише вкладку в адресу; повернення до компаній адресу очищає", async () => {
    const user = userEvent.setup();
    await openSources(sourcesBackend({ companies: COMPANIES, feeds: FEEDS }));

    await user.click(screen.getByRole("tab", { name: "RSS-стрічки · 2" }));

    expect(await sourceNames()).toEqual(["DOU · category=Python&remote", "Djinni · primary_keyword=Python&exp_level=5y"]);
    expect(location()).toBe("/sources?tab=feeds");
    await user.click(screen.getByRole("tab", { name: "Компанії · 5" }));
    expect(await sourceNames()).toHaveLength(5);
    expect(location()).toBe("/sources");
  });

  test("вкладка з адреси відкривається одразу, підпис — «2 стрічки»", async () => {
    await openSources(sourcesBackend({ companies: COMPANIES, feeds: FEEDS }), "/sources?tab=feeds");

    expect(await screen.findByRole("tab", { name: "RSS-стрічки · 2", selected: true })).toBeDefined();
    expect(screen.getByText("2 стрічки · подробиці — за натисканням назви")).toBeDefined();
  });

  test("зміна вкладки очищає пошук і розгорнуте джерело, а фільтр стану лишає", async () => {
    const user = userEvent.setup();
    await openSources(sourcesBackend({ companies: COMPANIES, feeds: FEEDS }), "/sources?q=north&status=enabled&open=00000000-0000-4000-8000-000000000001");

    await user.click(await screen.findByRole("tab", { name: "RSS-стрічки · 2" }));

    expect(location()).toBe("/sources?tab=feeds&status=enabled");
  });

  test("підпис під реєстром: «5 компаній · подробиці — за натисканням назви»", async () => {
    await openSources(sourcesBackend({ companies: COMPANIES }));

    expect(await screen.findByText("5 компаній · подробиці — за натисканням назви")).toBeDefined();
  });
});

describe("рядки реєстру", () => {
  test("колонки: Джерело, Стан, Оновлення · Мадрид, Імпортовано", async () => {
    await openSources(sourcesBackend({ companies: COMPANIES }));

    const table = await sourceList();
    expect(within(table).getAllByRole("columnheader").map((header) => header.textContent)).toEqual([
      "Джерело",
      "Стан",
      "Оновлення · Мадрид",
      "Імпортовано",
    ]);
  });

  test("рядок: назва, платформа, стан, день і час за Мадридом, імпортовано", async () => {
    await openSources(sourcesBackend({ companies: COMPANIES }));

    const row = within(await rowOf("Northstar"));
    expect(row.getByText("Greenhouse")).toBeDefined();
    expect(row.getByText("Працює")).toBeDefined();
    expect(row.getByText("2026-07-01")).toBeDefined();
    expect(row.getByText("12:05")).toBeDefined();
    expect(row.getByText("3")).toBeDefined();
  });

  test("час за зимовим Мадридом: 10:05 UTC → 11:05; імпортовано 0 показується нулем", async () => {
    await openSources(sourcesBackend({ companies: COMPANIES }));

    const row = within(await rowOf("LumaPay"));
    expect(row.getByText("2026-12-01")).toBeDefined();
    expect(row.getByText("11:05")).toBeDefined();
    expect(row.getByText("0")).toBeDefined();
  });

  test("без прогону: «Ще не оновлювалось», «Ще не було» і «—»", async () => {
    await openSources(sourcesBackend({ companies: COMPANIES }));

    const row = within(await rowOf("Nova Works"));
    expect(row.getByText("Ще не оновлювалось")).toBeDefined();
    expect(row.getByText("Ще не було")).toBeDefined();
    expect(row.getByText("—")).toBeDefined();
  });

  test("прогін із помилкою: бейдж «Помилка», час спроби є, імпортовано «—»", async () => {
    await openSources(sourcesBackend({ companies: COMPANIES }));

    const row = within(await rowOf("Orbit Labs"));
    expect(row.getByText("Помилка")).toBeDefined();
    expect(row.getByText("2026-07-01")).toBeDefined();
    expect(row.getByText("—")).toBeDefined();
  });

  test("вимкнене джерело: бейдж «Вимкнено»", async () => {
    await openSources(sourcesBackend({ companies: COMPANIES }));

    expect(within(await rowOf("Cloudline")).getByText("Вимкнено")).toBeDefined();
  });

  test("стрічка: назва складається з джерела й параметрів, під нею — джерело", async () => {
    await openSources(sourcesBackend({ feeds: FEEDS }), "/sources?tab=feeds");

    const row = within(await rowOf("DOU · category=Python&remote"));
    expect(row.getByText("DOU", { selector: "span" })).toBeDefined();
    expect(row.getByText("Працює")).toBeDefined();
  });
});

describe("пошук і фільтр стану", () => {
  test("пошук за Enter: за назвою, слагом, платформою; запит пишеться в адресу", async () => {
    const user = userEvent.setup();
    await openSources(sourcesBackend({ companies: COMPANIES }));

    await user.type(screen.getByRole("searchbox", { name: "Пошук" }), "north{Enter}");
    expect(await sourceNames()).toEqual(["Northstar"]);
    expect(location()).toBe("/sources?q=north");

    await user.clear(screen.getByRole("searchbox", { name: "Пошук" }));
    await user.type(screen.getByRole("searchbox", { name: "Пошук" }), "LEVER{Enter}");
    expect(await sourceNames()).toEqual(["Orbit Labs", "Nova Works"]);

    await user.clear(screen.getByRole("searchbox", { name: "Пошук" }));
    await user.type(screen.getByRole("searchbox", { name: "Пошук" }), "lumapay{Enter}");
    expect(await sourceNames()).toEqual(["LumaPay"]);
  });

  test("кнопка «Знайти» шукає так само; пошук за параметрами стрічки", async () => {
    const user = userEvent.setup();
    await openSources(sourcesBackend({ feeds: FEEDS }), "/sources?tab=feeds");

    await user.type(screen.getByRole("searchbox", { name: "Пошук" }), "exp_level");
    await user.click(screen.getByRole("button", { name: "Знайти" }));

    expect(await sourceNames()).toEqual(["Djinni · primary_keyword=Python&exp_level=5y"]);
  });

  test("поле пошуку підказує, за чим шукати", async () => {
    await openSources(sourcesBackend({ companies: COMPANIES }));

    expect(screen.getByRole("searchbox", { name: "Пошук" }).getAttribute("placeholder")).toBe("Назва, платформа або параметри");
  });

  test("фільтр стану: «Усі», «Увімкнені», «З помилками», «Вимкнені»", async () => {
    await openSources(sourcesBackend({ companies: COMPANIES }));

    const select = screen.getByRole("combobox", { name: "Стан" });
    expect(within(select).getAllByRole("option").map((option) => option.textContent)).toEqual(["Усі", "Увімкнені", "З помилками", "Вимкнені"]);
  });

  test.each([
    ["enabled", ["Northstar", "LumaPay", "Orbit Labs", "Nova Works"]],
    ["error", ["Orbit Labs"]],
    ["disabled", ["Cloudline"]],
  ])("фільтр «%s» залишає потрібні джерела й пише стан в адресу", async (status, expected) => {
    const user = userEvent.setup();
    await openSources(sourcesBackend({ companies: COMPANIES }));

    await user.selectOptions(screen.getByRole("combobox", { name: "Стан" }), status);

    expect(await sourceNames()).toEqual(expected);
    expect(location()).toBe(`/sources?status=${status}`);
  });

  test("пошук і стан з адреси відновлюються після перезавантаження", async () => {
    await openSources(sourcesBackend({ companies: COMPANIES }), "/sources?q=o&status=enabled");

    expect((screen.getByRole("searchbox", { name: "Пошук" }) as HTMLInputElement).value).toBe("o");
    expect((screen.getByRole("combobox", { name: "Стан" }) as HTMLSelectElement).value).toBe("enabled");
    expect(await sourceNames()).toEqual(["Northstar", "Orbit Labs", "Nova Works"]);
  });

  test("нерозпізнані параметри адреси ігноруються", async () => {
    await openSources(sourcesBackend({ companies: COMPANIES }), "/sources?tab=nope&status=paused&open=nope");

    expect(await sourceNames()).toHaveLength(5);
    expect((screen.getByRole("combobox", { name: "Стан" }) as HTMLSelectElement).value).toBe("");
  });
});

describe("порожні стани", () => {
  test("нічого не знайдено: «Немає збігів» і «Скинути фільтри» повертає все", async () => {
    const user = userEvent.setup();
    await openSources(sourcesBackend({ companies: COMPANIES }));

    await user.type(screen.getByRole("searchbox", { name: "Пошук" }), "zzz{Enter}");

    expect(await screen.findByRole("heading", { name: "Немає збігів" })).toBeDefined();
    expect(screen.getByText("Зміни пошук або фільтр стану.")).toBeDefined();
    await user.click(screen.getByRole("button", { name: "Скинути фільтри" }));
    expect(await sourceNames()).toHaveLength(5);
    expect(location()).toBe("/sources");
    expect((screen.getByRole("searchbox", { name: "Пошук" }) as HTMLInputElement).value).toBe("");
    expect((screen.getByRole("combobox", { name: "Стан" }) as HTMLSelectElement).value).toBe("");
  });

  test("фільтр стану без збігів теж дає «Немає збігів»", async () => {
    const user = userEvent.setup();
    await openSources(sourcesBackend({ companies: [apiCompany(1)] }));

    await user.selectOptions(screen.getByRole("combobox", { name: "Стан" }), "disabled");

    expect(await screen.findByRole("heading", { name: "Немає збігів" })).toBeDefined();
  });

  test("у вкладці нічого нема: «Джерел поки немає» з посиланням «Додати джерело»", async () => {
    await openSources(sourcesBackend({ feeds: FEEDS }));

    expect(await screen.findByRole("heading", { name: "Джерел поки немає" })).toBeDefined();
    expect(screen.getByText("Додай компанію чи RSS-стрічку для імпорту вакансій.")).toBeDefined();
    expect(screen.queryByRole("button", { name: "Скинути фільтри" })).toBeNull();
    const links = screen.getAllByRole("link", { name: "Додати джерело" });
    expect(links.map((link) => link.getAttribute("href"))).toEqual(["/sources/new", "/sources/new"]);
  });

  test("порожня вкладка стрічок веде на форму зі стрічкою", async () => {
    await openSources(sourcesBackend({ companies: COMPANIES }), "/sources?tab=feeds");

    await screen.findByRole("heading", { name: "Джерел поки немає" });
    const links = screen.getAllByRole("link", { name: "Додати джерело" });
    expect(links.map((link) => link.getAttribute("href"))).toEqual(["/sources/new?tab=feeds", "/sources/new?tab=feeds"]);
  });
});

describe("помилки", () => {
  test("мережа недоступна: повідомлення й «Спробувати ще раз», який перезавантажує список", async () => {
    const user = userEvent.setup();
    let attempts = 0;
    const backend = sourcesBackend(
      { companies: COMPANIES },
      {
        overview: () => {
          attempts += 1;
          return attempts === 1 ? Promise.reject(new Error("offline")) : undefined;
        },
      },
    );
    await openSources(backend);

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("Не вдалося завантажити джерела")).toBeDefined();
    expect(within(alert).getByText("Перевір з’єднання й повтори спробу.")).toBeDefined();
    await user.click(within(alert).getByRole("button", { name: "Спробувати ще раз" }));

    expect(await sourceNames()).toHaveLength(5);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  test("сервер відповів 500: та сама помилка з повтором", async () => {
    await openSources(sourcesBackend({}, { overview: () => problem(500, "internal_error", "Внутрішня помилка.") }));

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByRole("button", { name: "Спробувати ще раз" })).toBeDefined();
  });

  test("відповідь не за контрактом — теж помилка завантаження", async () => {
    await openSources(sourcesBackend({}, { overview: () => json(200, { companies: "oops" }) }));

    expect(await screen.findByText("Не вдалося завантажити джерела")).toBeDefined();
  });

  test("сесія завершилась: текст без повтору", async () => {
    await openSources(sourcesBackend({}, { overview: () => problem(401, "not_authenticated", "Потрібен вхід") }));

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("Сесія завершилась. Увійди знову, щоб побачити джерела.")).toBeDefined();
    expect(within(alert).queryByRole("button", { name: "Спробувати ще раз" })).toBeNull();
  });
});
