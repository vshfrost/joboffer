/** Таби вакансій і панель «Фільтри»: лічильники з сервера, бейджі «!», порядок блоків, умови фільтрів чипами. */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { findDelegate } from "./delegateHarness";
import { apiApplication, apiJob, jobsBackend, type ApiCounts, type ApiJob } from "./jobsBackend";
import { connectPrompts } from "./promptsBackend";
import { renderClient } from "./testClient";
import { applyFilters, chips, filtersButton, openFilters } from "./vacancyFilters";

const JOBS: ApiJob[] = [apiJob(1, { title: "Open Role", source: "manual" }), apiJob(2, { title: "Feed Role", source: "ats:ashby" })];
const NO_COUNTS: ApiCounts = { in_progress: 0, applied_unreviewed: 0, needs_text: false };

async function openList(path = "/vacancies", counts: ApiCounts = NO_COUNTS, jobs: ApiJob[] = JOBS) {
  const backend = jobsBackend(jobs);
  backend.counts = counts;
  connectPrompts(backend);
  renderClient(path, backend.fetchFn);
  await screen.findByRole("heading", { level: 1, name: "Вакансії" });
  await screen.findByRole("status", { name: "Результат" });
  return { backend, user: userEvent.setup() };
}

const location = () => screen.getByTestId("location").textContent;
const tab = (name: RegExp | string) => screen.getByRole("tab", { name });

describe("лічильник «У процесі»", () => {
  test("салатовий лічильник показує число з сервера на токенах counter", async () => {
    await openList("/vacancies", { ...NO_COUNTS, in_progress: 18 });
    const badge = within(tab(/^У процесі/)).getByRole("img", { name: "18 вакансій у процесі" });
    expect(badge.textContent).toBe("18");
    expect(badge.className).toContain("bg-counter");
    expect(badge.className).toContain("text-counter-foreground");
  });

  test("число стоїть у родовому відмінку: 1 вакансія, 2 вакансії, 5 вакансій", async () => {
    await openList("/vacancies", { ...NO_COUNTS, in_progress: 1 });
    expect(within(tab(/^У процесі/)).getByRole("img", { name: "1 вакансія у процесі" })).toBeDefined();
  });

  test("число береться з сервера, а не з довжини списку: список порожній, лічильник 7", async () => {
    await openList("/vacancies", { ...NO_COUNTS, in_progress: 7 }, []);
    expect(screen.getByText("Відкритих вакансій немає")).toBeDefined();
    expect(within(tab(/^У процесі/)).getByRole("img", { name: "7 вакансій у процесі" }).textContent).toBe("7");
  });

  test("лічильник видно й на інших табах", async () => {
    const { user } = await openList("/vacancies", { ...NO_COUNTS, in_progress: 3 });
    for (const name of ["Подано", "Потрібен текст", "Сховані", "У процесі"]) {
      await user.click(tab(new RegExp(`^${name}`)));
      await screen.findByRole("status", { name: "Результат" });
      expect(within(tab(/^У процесі/)).getByRole("img", { name: "3 вакансії у процесі" })).toBeDefined();
    }
  });

  test("при нулі лічильника нема", async () => {
    await openList();
    expect(within(tab("У процесі")).queryByRole("img")).toBeNull();
    expect(tab("У процесі").textContent).toBe("У процесі");
  });

  test("лічильник лишається, поки вантажиться список іншого таба", async () => {
    const { user, backend } = await openList("/vacancies", { ...NO_COUNTS, in_progress: 4 });
    const gate = backend.hold();
    await user.click(tab("Сховані"));
    await screen.findByRole("status", { name: "Завантажуємо вакансії" });
    expect(within(tab(/^У процесі/)).getByRole("img", { name: "4 вакансії у процесі" })).toBeDefined();
    gate.release();
  });
});

describe("лічильник «Подано» і бейджі «!»", () => {
  test("«Подано» показує число нерозібраних листів на токенах attention, а не «!»", async () => {
    await openList("/vacancies", { ...NO_COUNTS, applied_unreviewed: 2 });
    const badge = within(tab(/^Подано/)).getByRole("img", { name: "2 вакансії з нерозібраними листами" });
    expect(badge.textContent).toBe("2");
    expect(badge.className).toContain("bg-status-warning");
    expect(badge.className).toContain("text-status-warning-foreground");
    expect(within(tab(/^Потрібен текст/)).queryByRole("img")).toBeNull();
  });

  test("число стоїть у родовому відмінку: 1 вакансія, 5 вакансій", async () => {
    await openList("/vacancies", { ...NO_COUNTS, applied_unreviewed: 1 });
    expect(within(tab(/^Подано/)).getByRole("img", { name: "1 вакансія з нерозібраними листами" })).toBeDefined();
  });

  test("при нулі на «Подано» нічого нема", async () => {
    await openList();
    expect(within(tab("Подано")).queryByRole("img")).toBeNull();
    expect(tab("Подано").textContent).toBe("Подано");
  });

  test("«!» на «Потрібен текст», коли є вакансія без тексту", async () => {
    await openList("/vacancies", { ...NO_COUNTS, needs_text: true });
    const badge = within(tab(/^Потрібен текст/)).getByRole("img", { name: "Потребує уваги: є вакансії без тексту" });
    expect(badge.textContent).toBe("!");
    expect(within(tab(/^Подано/)).queryByRole("img")).toBeNull();
  });

  test("лічильник «Подано» і «!» видно на будь-якому табі", async () => {
    await openList("/vacancies?tab=dismissed", { in_progress: 0, applied_unreviewed: 2, needs_text: true });
    expect(within(tab(/^Подано/)).getByRole("img", { name: "2 вакансії з нерозібраними листами" })).toBeDefined();
    expect(within(tab(/^Потрібен текст/)).getByRole("img", { name: "Потребує уваги: є вакансії без тексту" })).toBeDefined();
  });

  test("без лічильників і прапорців бейджів немає ні на одному табі", async () => {
    await openList();
    expect(screen.getAllByRole("tab").map((candidate) => candidate.textContent)).toEqual(["Відкриті вакансії", "У процесі", "Подано", "Потрібен текст", "Сховані"]);
    expect(within(screen.getByRole("tablist")).queryAllByRole("img")).toEqual([]);
  });
});

describe("порядок блоків сторінки", () => {
  test("заголовок → «Делегувати агенту» → пошук → таби → «Фільтри» → підсумок", async () => {
    await openList();
    const heading = screen.getByRole("heading", { level: 1, name: "Вакансії" });
    const delegate = screen.getByRole("region", { name: "Делегувати агенту" });
    const search = screen.getByRole("searchbox", { name: "Пошук" });
    const tablist = screen.getByRole("tablist", { name: "Групи вакансій" });
    const filters = filtersButton();
    const summary = screen.getByRole("status", { name: "Результат" });
    const ordered = [heading, delegate, search, tablist, filters, summary];
    for (const [index, element] of ordered.slice(0, -1).entries()) {
      const next = ordered[index + 1] as HTMLElement;
      expect(element.compareDocumentPosition(next) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    }
  });

  test("«Делегувати агенту» лишається з поточним описом і кнопками", async () => {
    await openList();
    const block = await findDelegate("Агент оцінить одну пачку нових вакансій (до 5) за тими самими правилами, що й автотріаж сервера, покаже підсумок і спитає, чи продовжувати.");
    expect(block.getByRole("button", { name: "Копіювати промпт" })).toBeDefined();
  });

  test("пошук стоїть над табами, а не в панелі фільтрів", async () => {
    const { user } = await openList();
    const panel = await openFilters(user);
    expect(within(panel).queryByRole("searchbox")).toBeNull();
    expect(within(panel).queryByRole("button", { name: "Знайти" })).toBeNull();
  });
});

describe("панель «Фільтри»", () => {
  test("за замовчуванням згорнута: кнопка без числа, полів нема", async () => {
    await openList();
    expect(filtersButton().getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("region", { name: "Фільтри вакансій" })).toBeNull();
    expect(screen.queryByRole("combobox")).toBeNull();
    expect(within(filtersButton()).queryByText(/^\d+$/)).toBeNull();
  });

  test("кнопка відкриває й закриває панель", async () => {
    const { user } = await openList();
    await user.click(filtersButton());
    expect(filtersButton().getAttribute("aria-expanded")).toBe("true");
    const panel = screen.getByRole("region", { name: "Фільтри вакансій" });
    for (const label of ["Свіжість", "Джерело", "Вердикт тріажу", "Формат"]) {
      expect(within(panel).getByRole("combobox", { name: label })).toBeDefined();
    }
    expect(within(panel).getAllByRole("combobox")).toHaveLength(4);
    expect(within(panel).getByRole("button", { name: "Застосувати фільтри" })).toBeDefined();
    expect(within(panel).getByRole("button", { name: "Скинути" })).toBeDefined();
    await user.click(filtersButton());
    expect(screen.queryByRole("region", { name: "Фільтри вакансій" })).toBeNull();
  });

  test("вибір у панелі нічого не застосовує, поки не натиснуто «Застосувати фільтри»", async () => {
    const { user, backend } = await openList();
    const before = backend.requests.length;
    const panel = await openFilters(user);
    await user.selectOptions(within(panel).getByRole("combobox", { name: "Джерело" }), "manual");
    expect(location()).toBe("/vacancies");
    expect(backend.requests.length).toBe(before);
    expect(chips()).toEqual([]);
  });

  test("«Застосувати фільтри»: панель згортається, на кнопці число умов, умови стоять чипами", async () => {
    const { user, backend } = await openList();
    await applyFilters(user, { Свіжість: "7", Джерело: "manual" });
    await waitFor(() => expect(location()).toBe("/vacancies?days=7&source=manual"));
    expect(screen.queryByRole("region", { name: "Фільтри вакансій" })).toBeNull();
    expect(filtersButton().getAttribute("aria-expanded")).toBe("false");
    expect(within(filtersButton()).getByText("2")).toBeDefined();
    expect(chips()).toEqual(["Свіжість: За тиждень", "Джерело: manual"]);
    await waitFor(() => expect(backend.requests.at(-1)).toContain("source=manual"));
  });

  test("чип прибирає лише свою умову", async () => {
    const { user } = await openList("/vacancies?days=7&source=manual");
    await user.click(screen.getByRole("button", { name: "Прибрати фільтр Джерело: manual" }));
    await waitFor(() => expect(location()).toBe("/vacancies?days=7"));
    expect(chips()).toEqual(["Свіжість: За тиждень"]);
    expect(within(filtersButton()).getByText("1")).toBeDefined();
  });

  test("остання прибрана умова: чипів і числа нема", async () => {
    const { user } = await openList("/vacancies?source=manual");
    await user.click(screen.getByRole("button", { name: "Прибрати фільтр Джерело: manual" }));
    await waitFor(() => expect(location()).toBe("/vacancies"));
    expect(chips()).toEqual([]);
    expect(within(filtersButton()).queryByText(/^\d+$/)).toBeNull();
  });

  test("«Скинути» прибирає всі умови, але лишає пошук і таб", async () => {
    const { user } = await openList("/vacancies?tab=in-progress&q=rust&days=7&verdict=maybe&mode=remote");
    expect(within(filtersButton()).getByText("3")).toBeDefined();
    const panel = await openFilters(user);
    await user.click(within(panel).getByRole("button", { name: "Скинути" }));
    await waitFor(() => expect(location()).toBe("/vacancies?tab=in-progress&q=rust"));
    expect(chips()).toEqual([]);
    expect(within(filtersButton()).queryByText(/^\d+$/)).toBeNull();
    expect((screen.getByRole("searchbox", { name: "Пошук" }) as HTMLInputElement).value).toBe("rust");
  });

  test("пошук не рахується умовою фільтра", async () => {
    await openList("/vacancies?q=rust");
    expect(within(filtersButton()).queryByText(/^\d+$/)).toBeNull();
    expect(chips()).toEqual([]);
  });

  test("умови з адреси одразу видно чипами й числом, панель закрита", async () => {
    await openList("/vacancies?days=1&source=manual&verdict=skip&mode=hybrid");
    expect(filtersButton().getAttribute("aria-expanded")).toBe("false");
    expect(within(filtersButton()).getByText("4")).toBeDefined();
    expect(chips()).toEqual(["Свіжість: За добу", "Джерело: manual", "Вердикт тріажу: Пропустити", "Формат: Hybrid"]);
  });
});

describe("статус подачі й «Закриті»", () => {
  const statusOptions = async (user: ReturnType<typeof userEvent.setup>) => {
    const panel = await openFilters(user);
    return within(within(panel).getByRole("combobox", { name: "Статус подачі" })).getAllByRole("option").map((option) => option.textContent);
  };

  test("вибір статусу є лише на «Подано» й містить лише активні статуси", async () => {
    const { user } = await openList("/vacancies?tab=applied");
    expect(await statusOptions(user)).toEqual(["Усі статуси", "Подано", "Є відповідь", "Співбесіда", "Оффер"]);
  });

  test.each(["/vacancies", "/vacancies?tab=in-progress", "/vacancies?tab=needs-text", "/vacancies?tab=dismissed"])("на %s вибору статусу нема", async (path) => {
    const { user } = await openList(path);
    const panel = await openFilters(user);
    expect(within(panel).queryByRole("combobox", { name: "Статус подачі" })).toBeNull();
  });

  test("перемикача «Закриті» нема ні на одному табі", async () => {
    const { user } = await openList("/vacancies?tab=applied");
    for (const name of ["Відкриті вакансії", "У процесі", "Подано", "Потрібен текст", "Сховані"]) {
      await user.click(tab(new RegExp(`^${name}`)));
      await screen.findByRole("status", { name: "Результат" });
      expect(screen.queryByRole("checkbox", { name: "Закриті" })).toBeNull();
      expect(screen.queryByText("Закриті")).toBeNull();
    }
  });

  test("обраний статус потрапляє в запит і в чип; вихід з «Подано» його скидає", async () => {
    const { user, backend } = await openList("/vacancies?tab=applied");
    await applyFilters(user, { "Статус подачі": "interview" });
    await waitFor(() => expect(location()).toBe("/vacancies?tab=applied&status=interview"));
    expect(chips()).toEqual(["Статус подачі: Співбесіда"]);
    await waitFor(() => expect(backend.requests.at(-1)).toBe("GET /api/jobs?stage=applied&status=interview&limit=200"));
    await user.click(tab(/^У процесі/));
    await waitFor(() => expect(location()).toBe("/vacancies?tab=in-progress"));
    expect(chips()).toEqual([]);
    await waitFor(() => expect(backend.requests.at(-1)).toBe("GET /api/jobs?stage=in_progress&limit=200"));
  });

  test("статус в адресі поза табом «Подано» ігнорується", async () => {
    const { backend } = await openList("/vacancies?status=offer");
    expect(chips()).toEqual([]);
    expect(backend.requests.at(-1)).toBe("GET /api/jobs?stage=open&limit=200");
  });

  test("закритий статус в адресі на «Подано» ігнорується", async () => {
    const { backend } = await openList("/vacancies?tab=applied&status=rejected");
    expect(chips()).toEqual([]);
    expect(backend.requests.at(-1)).toBe("GET /api/jobs?stage=applied&limit=200");
  });
});

describe("рядок не несе позначки непрочитаних відповідей", () => {
  test("«Не цікаво» лишається в рядку, окремої мітки листа нема", async () => {
    await openList("/vacancies", { ...NO_COUNTS, applied_unreviewed: 2 });
    expect(screen.getByRole("button", { name: "Не цікаво: Open Role" })).toBeDefined();
    const row = screen.getByRole("link", { name: "Open Role" }).closest("tr") as HTMLElement;
    expect(within(row).queryByRole("img")).toBeNull();
    expect(row.textContent).not.toMatch(/лист|відповід/i);
  });
});

describe("колір бейджа «Є відповідь»", () => {
  test("у рядку таблиці бейдж «Є відповідь» має колір уваги", async () => {
    const backend = jobsBackend([apiJob(1, { title: "Replied Role" })], [], [], [apiApplication(1, { status: "replied" })]);
    connectPrompts(backend);
    renderClient("/vacancies?tab=applied", backend.fetchFn);
    await screen.findByRole("status", { name: "Результат" });
    const row = (await screen.findByRole("link", { name: "Replied Role" })).closest("tr") as HTMLElement;
    expect(within(row).getByText("Є відповідь").className).toContain("bg-status-warning");
  });
});
