import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { apiApplication, apiJob, daysAgo, jobsBackend, type ApiJob } from "./jobsBackend";
import { renderClient } from "./testClient";
import { applyFilters, openFilters } from "./vacancyFilters";
import { setViewport } from "./viewport";

const JOBS: ApiJob[] = [
  apiJob(1, { title: "Senior Backend Engineer", company: "Northline Pay", created_at: "2026-10-19T09:00:00Z", source: "manual" }),
  apiJob(2, { title: "Python Engineer — Payments", company: "Brisa Systems", created_at: "2026-10-18T09:00:00Z", source: "linkedin_alert", text: null }),
  apiJob(3, { title: "Rust Developer", company: "Cedar Ledger", created_at: "2026-10-17T22:30:00Z", source: "manual", text: "We write Rust daily" }),
  apiJob(4, {
    title: "Hidden Role",
    company: "Forma Cloud",
    created_at: "2026-10-16T09:00:00Z",
    dismissed_at: "2026-10-20T09:00:00Z",
    dismiss_reason: "не цікаво",
  }),
];

async function openList(jobs: ApiJob[] = JOBS, path = "/vacancies") {
  const backend = jobsBackend(jobs);
  const view = renderClient(path, backend.fetchFn);
  await screen.findByRole("heading", { level: 1, name: "Вакансії" });
  await screen.findByRole("status", { name: "Результат" });
  return { backend, view, user: userEvent.setup() };
}

const rows = () => within(screen.getByRole("table", { name: "Вакансії" })).getAllByRole("row");
const cards = () => within(screen.getByRole("list", { name: "Вакансії" })).getAllByRole("listitem");
const location = () => screen.getByTestId("location").textContent;

describe("сторінка вакансій", () => {
  test("має заголовок, підзаголовок і заголовок вкладки", async () => {
    await openList();
    expect(screen.getByRole("heading", { level: 1, name: "Вакансії" })).toBeDefined();
    expect(screen.getByText("Наступний крок у твоїй кар’єрі.")).toBeDefined();
    expect(document.title).toBe("Вакансії · joboffer");
  });

  test("таби «Відкриті вакансії», «У процесі», «Подано», «Потрібен текст», «Сховані» стоять блоком, перший вибраний", async () => {
    await openList([apiJob(1)]);
    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((tab) => tab.textContent)).toEqual(["Відкриті вакансії", "У процесі", "Подано", "Потрібен текст", "Сховані"]);
    expect(tabs.map((tab) => tab.getAttribute("aria-selected"))).toEqual(["true", "false", "false", "false", "false"]);
    expect(screen.getByRole("tablist", { name: "Групи вакансій" })).toBeDefined();
  });

  test("таб за замовчуванням — «Відкриті вакансії», запит просить етап open", async () => {
    const { backend } = await openList([apiJob(1)]);
    expect(screen.getByRole("tab", { name: "Відкриті вакансії" }).getAttribute("aria-selected")).toBe("true");
    expect(backend.requests.at(-1)).toBe("GET /api/jobs?stage=open&limit=200");
  });

  test.each(["all", "closed", "zzz", ""])("старе чи невідоме значення tab=%j веде на «Відкриті вакансії»", async (value) => {
    await openList([apiJob(1)], `/vacancies?tab=${value}`);
    expect(screen.getByRole("tab", { name: "Відкриті вакансії" }).getAttribute("aria-selected")).toBe("true");
  });

  test("поки список вантажиться — скелетон зі статусом, а не порожній стан", async () => {
    const backend = jobsBackend(JOBS);
    const gate = backend.hold();
    renderClient("/vacancies", backend.fetchFn);
    const status = await screen.findByRole("status", { name: "Завантажуємо вакансії" });
    expect(status.getAttribute("aria-busy")).toBe("true");
    expect(screen.queryByText("Відкритих вакансій немає")).toBeNull();
    await act(async () => gate.release());
    expect(await screen.findByRole("table", { name: "Вакансії" })).toBeDefined();
    expect(screen.queryByRole("status", { name: "Завантажуємо вакансії" })).toBeNull();
  });

  test("у «Відкритих» є вакансії з текстом; без тексту й схована — ні", async () => {
    await openList();
    expect(screen.getByRole("link", { name: "Senior Backend Engineer" })).toBeDefined();
    expect(screen.getByRole("link", { name: "Rust Developer" })).toBeDefined();
    expect(screen.queryByRole("link", { name: "Python Engineer — Payments" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Hidden Role" })).toBeNull();
  });

  test("порядок: новіші першими", async () => {
    await openList();
    const titles = rows()
      .slice(1)
      .map((row) => within(row).getByRole("link").textContent);
    expect(titles).toEqual(["Senior Backend Engineer", "Rust Developer"]);
  });

  test("кількість знайдених видно під табами й оголошується в статусі", async () => {
    await openList();
    const summary = screen.getByRole("status", { name: "Результат" });
    expect(summary.textContent).toBe("Показано 2 вакансії");
    expect(summary.className).not.toContain("sr-only");
  });

  test("відмова не показується в жодному табі, навіть за пошуком", async () => {
    const jobs = [apiJob(1, { title: "Rejected Role" }), apiJob(2, { title: "Plain Role" }), apiJob(3, { title: "Rejected Hidden", dismissed_at: "2026-10-20T09:00:00Z", dismiss_reason: "x" })];
    const backend = jobsBackend(jobs, [], [], [apiApplication(1, { status: "rejected" }), apiApplication(3, { status: "rejected" })]);
    renderClient("/vacancies?q=rejected", backend.fetchFn);
    expect(await screen.findByText("Нічого не знайдено")).toBeDefined();
    await userEvent.setup().click(screen.getByRole("tab", { name: "Сховані" }));
    await waitFor(() => expect(backend.requests.at(-1)).toContain("dismissed=true"));
    expect(await screen.findByText("Нічого не знайдено")).toBeDefined();
    expect(screen.queryByRole("link", { name: "Rejected Hidden" })).toBeNull();
  });
});

describe("таблиця на desktop", () => {
  test("колонки: посада, компанія, тріаж, аналіз, додано", async () => {
    setViewport("desktop");
    await openList();
    const headers = within(screen.getByRole("table", { name: "Вакансії" })).getAllByRole("columnheader");
    expect(headers.map((header) => header.textContent)).toEqual(["Посада", "Компанія", "Тріаж", "Аналіз", "Додано", "Дія"]);
  });

  test("рядок показує назву-посилання, компанію, джерело й день додавання за Мадридом", async () => {
    setViewport("desktop");
    await openList();
    const row = rows()[1] as HTMLElement;
    expect(within(row).getByRole("link", { name: "Senior Backend Engineer" }).getAttribute("href")).toBe("/vacancies/1");
    const cells = within(row).getAllByRole("cell");
    expect(cells.map((cell) => cell.textContent?.replace(/\s+/g, " ").trim())).toEqual([
      "Senior Backend Engineer",
      "Northline Pay manual",
      "Без тріажу",
      "Не проаналізовано",
      "2026-10-19",
      "Не цікаво",
    ]);
  });

  test("день додавання рахується за Мадридом, а не за UTC", async () => {
    setViewport("desktop");
    await openList();
    const row = rows().find((candidate) => within(candidate).queryByRole("link", { name: "Rust Developer" }) !== null) as HTMLElement;
    expect(within(row).getByText("2026-10-18")).toBeDefined();
  });

  test("вакансія «потрібен текст» має позначку стану даних у рядку, вакансія з текстом — ні", async () => {
    setViewport("desktop");
    await openList(JOBS, "/vacancies?tab=needs-text");
    const row = rows().find((candidate) => within(candidate).queryByRole("link", { name: "Python Engineer — Payments" }) !== null) as HTMLElement;
    expect(within(row).getByText("Потрібен текст")).toBeDefined();
    expect(screen.queryByRole("link", { name: "Senior Backend Engineer" })).toBeNull();
  });

  test("«нове» стоїть у рядку лише в нової вакансії з джерела", async () => {
    setViewport("desktop");
    await openList([apiJob(1, { title: "Fresh Role", source: "ats:greenhouse", is_new: true }), apiJob(2, { title: "Seen Role", source: "rss:remoteok" })]);
    const rowOf = (name: string) => rows().find((candidate) => within(candidate).queryByRole("link", { name }) !== null) as HTMLElement;
    expect(within(rowOf("Fresh Role")).getByText("нове")).toBeDefined();
    expect(within(rowOf("Seen Role")).queryByText("нове")).toBeNull();
  });

  test("без назви й компанії — «Без назви» й «Не вказано»", async () => {
    setViewport("desktop");
    await openList([apiJob(5, { title: null, company: null })]);
    const row = rows()[1] as HTMLElement;
    expect(within(row).getByRole("link", { name: "Без назви" })).toBeDefined();
    expect(within(row).getByText("Не вказано")).toBeDefined();
  });
});

describe("картки на mobile", () => {
  test("ті самі дані, що й у таблиці, але списком карток без таблиці", async () => {
    setViewport("mobile");
    await openList();
    expect(screen.queryByRole("table")).toBeNull();
    const items = cards();
    expect(items).toHaveLength(2);
    const first = items[0] as HTMLElement;
    expect(within(first).getByRole("link", { name: "Senior Backend Engineer" }).getAttribute("href")).toBe("/vacancies/1");
    expect(first.textContent).toContain("Northline Pay");
    expect(first.textContent).toContain("manual");
    expect(first.textContent).toContain("2026-10-19");
    expect(within(first).getByRole("button", { name: "Не цікаво: Senior Backend Engineer" })).toBeDefined();
  });

  test("картка вакансії без тексту має позначку «Потрібен текст»", async () => {
    setViewport("mobile");
    await openList(JOBS, "/vacancies?tab=needs-text");
    const waiting = cards().find((card) => within(card).queryByRole("link", { name: "Python Engineer — Payments" }) !== null) as HTMLElement;
    expect(within(waiting).getByText("Потрібен текст")).toBeDefined();
  });

  test("«нове» стоїть на картці лише в нової вакансії з джерела", async () => {
    setViewport("mobile");
    await openList([apiJob(1, { title: "Fresh Role", source: "ats:greenhouse", is_new: true }), apiJob(2, { title: "Seen Role", source: "rss:remoteok" })]);
    const cardOf = (name: string) => cards().find((card) => within(card).queryByRole("link", { name }) !== null) as HTMLElement;
    expect(within(cardOf("Fresh Role")).getByText("нове")).toBeDefined();
    expect(within(cardOf("Seen Role")).queryByText("нове")).toBeNull();
  });

  test.each(["desktop", "mobile"] as const)("на %s кожна вакансія показує назву, компанію, джерело й день", async (viewport) => {
    setViewport(viewport);
    await openList();
    const container = viewport === "desktop" ? screen.getByRole("table", { name: "Вакансії" }) : screen.getByRole("list", { name: "Вакансії" });
    for (const expected of ["Senior Backend Engineer", "Northline Pay", "manual", "2026-10-19", "Rust Developer", "Cedar Ledger"]) {
      expect(container.textContent).toContain(expected);
    }
  });
});

describe("довгі значення", () => {
  const LONG_TITLE = "Principal Distributed Systems Reliability Engineer, Payments Platform, Cross-Border Settlement and Reconciliation";
  const LONG_COMPANY = "Supercalifragilisticexpialidocious-International-Holdings-and-Partners-Of-Valencia-Limited";

  test.each(["desktop", "mobile"] as const)("на %s назва й компанія показані повністю й можуть переноситись", async (viewport) => {
    setViewport(viewport);
    await openList([apiJob(9, { title: LONG_TITLE, company: LONG_COMPANY })]);
    const link = screen.getByRole("link", { name: LONG_TITLE });
    expect(link.textContent).toBe(LONG_TITLE);
    expect(link.className).toContain("[overflow-wrap:anywhere]");
    const company = screen.getByText(LONG_COMPANY);
    expect(company.className).toContain("[overflow-wrap:anywhere]");
    expect(company.className).not.toContain("truncate");
    expect(link.className).not.toContain("truncate");
  });
});

describe("порожні стани", () => {
  test("у «Відкритих» нічого немає", async () => {
    await openList([]);
    expect(screen.getByText("Відкритих вакансій немає")).toBeDefined();
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryByRole("button", { name: "Скинути пошук і фільтри" })).toBeNull();
  });

  test("у табі «У процесі» нема таких вакансій", async () => {
    await openList([apiJob(1)], "/vacancies?tab=in-progress");
    expect(await screen.findByText("Вакансій у процесі немає")).toBeDefined();
  });

  test("у табі «Подано» нема подач", async () => {
    await openList([apiJob(1)], "/vacancies?tab=applied");
    expect(await screen.findByText("Поданих вакансій немає")).toBeDefined();
  });

  test("у табі «Потрібен текст» нема таких вакансій", async () => {
    await openList([apiJob(1)], "/vacancies?tab=needs-text");
    expect(await screen.findByText("Вакансій без тексту немає")).toBeDefined();
  });

  test("у табі «Сховані» нема схованих", async () => {
    await openList([apiJob(1)], "/vacancies?tab=dismissed");
    expect(await screen.findByText("Схованих вакансій немає")).toBeDefined();
  });

  test("фільтр нічого не знайшов — окремий стан зі скиданням фільтрів", async () => {
    const { user } = await openList(JOBS, "/vacancies?q=nothing-like-this");
    expect(await screen.findByText("Нічого не знайдено")).toBeDefined();
    expect(screen.queryByText("Відкритих вакансій немає")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Скинути пошук і фільтри" }));
    expect(await screen.findByRole("table", { name: "Вакансії" })).toBeDefined();
    await waitFor(() => expect(location()).toBe("/vacancies"));
  });
});

describe("помилка списку", () => {
  test("показує тривогу з повтором, а повтор вантажить список", async () => {
    const backend = jobsBackend(JOBS);
    backend.failures.list = 1;
    renderClient("/vacancies", backend.fetchFn);
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Не вдалося завантажити вакансії.");
    expect(screen.queryByText("Відкритих вакансій немає")).toBeNull();
    await userEvent.setup().click(within(alert).getByRole("button", { name: "Спробувати ще раз" }));
    expect(await screen.findByRole("table", { name: "Вакансії" })).toBeDefined();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("ліміт списку", () => {
  test("якщо сервер віддав стільки, скільки просили, — підказка звузити пошук", async () => {
    const many = Array.from({ length: 200 }, (_, index) => apiJob(index + 1));
    await openList(many);
    expect(screen.getByText("Показано перші 200 вакансій. Звузь пошук, щоб побачити решту.")).toBeDefined();
  });

  test("менше за ліміт — без підказки", async () => {
    await openList();
    expect(screen.queryByText(/Показано перші/)).toBeNull();
  });
});

describe("таби й фільтри живуть в адресі", () => {
  test("початкові значення беруться з адреси й потрапляють у запит", async () => {
    const { backend, user } = await openList(JOBS, "/vacancies?tab=needs-text&q=python&days=7&source=linkedin_alert");
    expect(screen.getByRole("tab", { name: "Потрібен текст" }).getAttribute("aria-selected")).toBe("true");
    expect((screen.getByRole("searchbox", { name: "Пошук" }) as HTMLInputElement).value).toBe("python");
    const panel = await openFilters(user);
    expect((within(panel).getByRole("combobox", { name: "Свіжість" }) as HTMLSelectElement).value).toBe("7");
    expect((within(panel).getByRole("combobox", { name: "Джерело" }) as HTMLSelectElement).value).toBe("linkedin_alert");
    const last = new URL(`http://x${backend.requests.at(-1)?.replace("GET ", "")}`);
    expect(Object.fromEntries(last.searchParams)).toEqual({
      query: "python",
      days: "7",
      source: "linkedin_alert",
      needs_text: "true",
      limit: "200",
    });
  });

  test("таб «Відкриті вакансії» не лишає параметра tab", async () => {
    const { user } = await openList(JOBS, "/vacancies?tab=dismissed");
    await user.click(screen.getByRole("tab", { name: "Відкриті вакансії" }));
    await waitFor(() => expect(location()).toBe("/vacancies"));
  });

  test("клік по табу змінює адресу й вантажить його вакансії", async () => {
    const { user, backend } = await openList();
    await user.click(screen.getByRole("tab", { name: "Сховані" }));
    await waitFor(() => expect(location()).toBe("/vacancies?tab=dismissed"));
    expect(await screen.findByRole("link", { name: "Hidden Role" })).toBeDefined();
    expect(screen.queryByRole("link", { name: "Senior Backend Engineer" })).toBeNull();
    expect(backend.requests.at(-1)).toContain("dismissed=true");
  });

  test("стрілки клавіатури перемикають таби по колу, Home й End — на краї", async () => {
    const { user } = await openList();
    await user.click(screen.getByRole("tab", { name: "Відкриті вакансії" }));
    await user.keyboard("{ArrowRight}");
    await waitFor(() => expect(screen.getByRole("tab", { name: "У процесі" }).getAttribute("aria-selected")).toBe("true"));
    await waitFor(() => expect(location()).toBe("/vacancies?tab=in-progress"));
    await user.keyboard("{ArrowRight}");
    await waitFor(() => expect(screen.getByRole("tab", { name: "Подано" }).getAttribute("aria-selected")).toBe("true"));
    await waitFor(() => expect(location()).toBe("/vacancies?tab=applied"));
    await user.keyboard("{ArrowRight}");
    await waitFor(() => expect(screen.getByRole("tab", { name: "Потрібен текст" }).getAttribute("aria-selected")).toBe("true"));
    await waitFor(() => expect(location()).toBe("/vacancies?tab=needs-text"));
    await user.keyboard("{End}");
    await waitFor(() => expect(screen.getByRole("tab", { name: "Сховані" }).getAttribute("aria-selected")).toBe("true"));
    await user.keyboard("{ArrowRight}");
    await waitFor(() => expect(screen.getByRole("tab", { name: "Відкриті вакансії" }).getAttribute("aria-selected")).toBe("true"));
    await waitFor(() => expect(location()).toBe("/vacancies"));
  });

  test("пошук застосовується за Enter і не губить таб", async () => {
    const { user, backend } = await openList(JOBS, "/vacancies?tab=dismissed");
    await user.type(screen.getByRole("searchbox", { name: "Пошук" }), "forma{Enter}");
    await waitFor(() => expect(location()).toBe("/vacancies?tab=dismissed&q=forma"));
    await waitFor(() => expect(backend.requests.at(-1)).toContain("query=forma"));
    expect(await screen.findByRole("link", { name: "Hidden Role" })).toBeDefined();
  });

  test("кнопка «Знайти» робить те саме, що Enter; пробіли по краях зрізаються", async () => {
    const { user } = await openList();
    await user.type(screen.getByRole("searchbox", { name: "Пошук" }), "  rust  ");
    await user.click(screen.getByRole("button", { name: "Знайти" }));
    await waitFor(() => expect(location()).toBe("/vacancies?q=rust"));
    expect(await screen.findByRole("link", { name: "Rust Developer" })).toBeDefined();
    expect(screen.queryByRole("link", { name: "Senior Backend Engineer" })).toBeNull();
  });

  test("пошук шукає й у тексті вакансії", async () => {
    const { user } = await openList();
    await user.type(screen.getByRole("searchbox", { name: "Пошук" }), "daily{Enter}");
    expect(await screen.findByRole("link", { name: "Rust Developer" })).toBeDefined();
  });

  test("свіжість: вибір у панелі потрапляє в адресу лише після «Застосувати фільтри»", async () => {
    const fresh = [apiJob(1, { title: "Свіжа", created_at: daysAgo(1) }), apiJob(2, { title: "Стара", created_at: daysAgo(20) })];
    const { user } = await openList(fresh);
    const panel = await openFilters(user);
    await user.selectOptions(within(panel).getByRole("combobox", { name: "Свіжість" }), "7");
    expect(location()).toBe("/vacancies");
    await user.click(within(panel).getByRole("button", { name: "Застосувати фільтри" }));
    await waitFor(() => expect(location()).toBe("/vacancies?days=7"));
    expect(await screen.findByRole("link", { name: "Свіжа" })).toBeDefined();
    expect(screen.queryByRole("link", { name: "Стара" })).toBeNull();
  });

  test("варіанти свіжості: будь-коли, за добу, за тиждень, за місяць", async () => {
    const { user } = await openList();
    const panel = await openFilters(user);
    const options = within(within(panel).getByRole("combobox", { name: "Свіжість" })).getAllByRole("option");
    expect(options.map((option) => option.textContent)).toEqual(["Будь-коли", "За добу", "За тиждень", "За місяць"]);
  });

  test("джерело: варіанти — з відповіді сервера, вибір звужує список", async () => {
    const { user } = await openList(JOBS, "/vacancies?tab=needs-text");
    const panel = await openFilters(user);
    const select = within(panel).getByRole("combobox", { name: "Джерело" });
    expect(within(select).getAllByRole("option").map((option) => option.textContent)).toEqual(["Усі джерела", "linkedin_alert", "manual"]);
    await applyFilters(user, { Джерело: "manual" });
    await waitFor(() => expect(location()).toBe("/vacancies?tab=needs-text&source=manual"));
    expect(await screen.findByText("Нічого не знайдено")).toBeDefined();
    expect(screen.queryByRole("link", { name: "Python Engineer — Payments" })).toBeNull();
  });

  test("фільтри переживають перемикання таба (крім статусу подачі)", async () => {
    const { user } = await openList(JOBS, "/vacancies?q=forma");
    await user.click(screen.getByRole("tab", { name: "Сховані" }));
    await waitFor(() => expect(location()).toBe("/vacancies?tab=dismissed&q=forma"));
  });

  test("зайві й хибні параметри адреси, зокрема старий closed, ігноруються", async () => {
    const { backend } = await openList(JOBS, "/vacancies?tab=zzz&days=abc&x=1&closed=1");
    expect(screen.getByRole("tab", { name: "Відкриті вакансії" }).getAttribute("aria-selected")).toBe("true");
    expect(backend.requests.at(-1)).toBe("GET /api/jobs?stage=open&limit=200");
    expect(screen.queryByRole("checkbox", { name: "Закриті" })).toBeNull();
  });

  test("невідоме джерело в адресі лишається вибраним, щоб його видно й можна скинути", async () => {
    const { user } = await openList(JOBS, "/vacancies?source=ghost");
    const panel = await openFilters(user);
    const select = within(panel).getByRole("combobox", { name: "Джерело" }) as HTMLSelectElement;
    expect(select.value).toBe("ghost");
  });
});
