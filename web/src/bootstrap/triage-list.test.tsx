/** Список вакансій з тріажем і аналізом: два підписані скори, фільтри вердикту й формату, запит тріажу для Claude. */
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { COPIED, findDelegate } from "./delegateHarness";
import { apiAnalysis, apiJob, apiTriage, jobsBackend, type ApiAnalysis, type ApiJob } from "./jobsBackend";
import { connectPrompts } from "./promptsBackend";
import { renderClient } from "./testClient";
import { applyFilters, chips, openFilters } from "./vacancyFilters";
import { setViewport } from "./viewport";

const JOBS: ApiJob[] = [
  apiJob(1, { title: "Senior Backend Engineer", company: "Northstar Labs", created_at: "2026-10-19T09:00:00Z", triage: apiTriage({ score: 86, verdict: "analyse" }) }),
  apiJob(2, { title: "Platform Engineer", company: "Orbit Studio", created_at: "2026-10-18T09:00:00Z", triage: apiTriage({ score: 81, verdict: "analyse" }) }),
  apiJob(3, { title: "Python Engineer", company: "Lumen Works", created_at: "2026-10-17T09:00:00Z", triage: apiTriage({ score: 64, verdict: "maybe" }) }),
  apiJob(4, { title: "Engineering Manager", company: "Vertex Cloud", created_at: "2026-10-16T09:00:00Z", triage: apiTriage({ score: 32, verdict: "skip" }) }),
  apiJob(5, { title: "Rust Developer", company: "Cedar Ledger", created_at: "2026-10-15T09:00:00Z" }),
  apiJob(6, { title: "Go Developer", company: "Delta Pay", created_at: "2026-10-14T09:00:00Z" }),
];
const ANALYSES: ApiAnalysis[] = [
  apiAnalysis(1, { score: 78, work_mode: "remote" }),
  apiAnalysis(6, { score: 90, work_mode: "onsite", flags: ["Формат onsite — не з профілю."] }),
];

/** Вакансії тут з аналізом чи іншою роботою над ними, тож живуть у табі «У процесі», а не у «Відкритих». */
const IN_PROGRESS = "/vacancies?tab=in-progress";

async function openList(path = IN_PROGRESS, jobs: ApiJob[] = JOBS, analyses: ApiAnalysis[] = ANALYSES) {
  const backend = jobsBackend(jobs, analyses);
  backend.interactions = jobs.map((job) => job.job_id);
  connectPrompts(backend);
  const view = renderClient(path, backend.fetchFn);
  await screen.findByRole("heading", { level: 1, name: "Вакансії" });
  await screen.findByRole("status", { name: "Результат" });
  return { backend, view, user: userEvent.setup() };
}

const rows = () => within(screen.getByRole("table", { name: "Вакансії" })).getAllByRole("row").slice(1);
const titles = () => rows().map((row) => within(row).getByRole("link").textContent);
const row = (title: string) => rows().find((candidate) => within(candidate).queryByRole("link", { name: title }) !== null) as HTMLElement;
const location = () => screen.getByTestId("location").textContent;
const lastList = (backend: { requests: string[] }) => backend.requests.filter((request) => request.startsWith("GET /api/jobs?")).at(-1) as string;

describe("два скори в списку", () => {
  test("порядок як на сервері: проаналізовані, потім тріаж, потім решта", async () => {
    await openList();
    expect(titles()).toEqual(["Senior Backend Engineer", "Go Developer", "Platform Engineer", "Python Engineer", "Engineering Manager", "Rust Developer"]);
  });

  test("заголовки колонок: Посада, Компанія, Тріаж, Аналіз, Додано, Дія", async () => {
    await openList();
    const headers = within(screen.getByRole("table", { name: "Вакансії" })).getAllByRole("columnheader");
    expect(headers.map((header) => header.textContent)).toEqual(["Посада", "Компанія", "Тріаж", "Аналіз", "Додано", "Дія"]);
  });

  test("скор тріажу й скор аналізу підписані й не плутаються", async () => {
    await openList();
    const both = row("Senior Backend Engineer");
    expect(within(both).getByText("Тріаж 86/100")).toBeDefined();
    expect(within(both).getByText("Аналіз 78%")).toBeDefined();
    expect(within(both).getByText("Аналізувати")).toBeDefined();
    const triageOnly = row("Platform Engineer");
    expect(within(triageOnly).getByText("Тріаж 81/100")).toBeDefined();
    expect(within(triageOnly).getByText("Не проаналізовано")).toBeDefined();
    expect(within(triageOnly).queryByText(/Аналіз \d/)).toBeNull();
  });

  test("без тріажу й аналізу — чесні порожні підписи", async () => {
    await openList();
    const plain = row("Rust Developer");
    expect(within(plain).getByText("Без тріажу")).toBeDefined();
    expect(within(plain).getByText("Не проаналізовано")).toBeDefined();
  });

  test("аналіз, що не пройшов фільтри, позначено «Не підходить»", async () => {
    await openList();
    const failed = row("Go Developer");
    expect(within(failed).getByText("Аналіз 90%")).toBeDefined();
    expect(within(failed).getByText("Не підходить")).toBeDefined();
    expect(within(row("Senior Backend Engineer")).queryByText("Не підходить")).toBeNull();
  });

  test("оцінка аналізу 0 — це оцінка", async () => {
    await openList(IN_PROGRESS, JOBS, [apiAnalysis(1, { score: 0 })]);
    expect(within(row("Senior Backend Engineer")).getByText("Аналіз 0%")).toBeDefined();
  });

  test("«Пропустити» не ховає вакансію: вона в списку з поясненням", async () => {
    await openList();
    const skipped = row("Engineering Manager");
    expect(within(skipped).getByText("Пропустити")).toBeDefined();
    expect(within(skipped).getByText("Тріаж 32/100")).toBeDefined();
    expect(screen.getByText("«Пропустити» — рекомендація тріажу. Вакансія залишається у списку.")).toBeDefined();
  });

  test("пояснення про «Пропустити» не з'являється, коли такого вердикту нема", async () => {
    await openList(IN_PROGRESS, [JOBS[0] as ApiJob], []);
    expect(screen.queryByText(/рекомендація тріажу/)).toBeNull();
  });

  test("на мобільному ті самі два скори карточками", async () => {
    setViewport("mobile");
    await openList();
    const card = within(screen.getByRole("list", { name: "Вакансії" })).getAllByRole("listitem")[0] as HTMLElement;
    expect(within(card).getByText("Тріаж 86/100")).toBeDefined();
    expect(within(card).getByText("Аналіз 78%")).toBeDefined();
    expect(within(card).getByRole("link", { name: "Senior Backend Engineer" })).toBeDefined();
  });
});

describe("пошук, вердикт і формат разом", () => {
  test("фільтри вердикту й формату є в панелі, за замовчуванням — «усі»", async () => {
    const { user } = await openList();
    const panel = await openFilters(user);
    const verdict = within(panel).getByRole("combobox", { name: "Вердикт тріажу" }) as HTMLSelectElement;
    const mode = within(panel).getByRole("combobox", { name: "Формат" }) as HTMLSelectElement;
    expect([...verdict.options].map((option) => option.textContent)).toEqual(["Усі вердикти", "Аналізувати", "Можливо", "Пропустити"]);
    expect([...mode.options].map((option) => option.textContent)).toEqual(["Усі формати", "Remote", "Hybrid", "Onsite"]);
    expect([verdict.value, mode.value]).toEqual(["", ""]);
  });

  test("вердикт «Пропустити» лишає лише такі вакансії й пише себе в адресу", async () => {
    const { user, backend } = await openList();
    await applyFilters(user, { "Вердикт тріажу": "skip" });
    await waitFor(() => expect(titles()).toEqual(["Engineering Manager"]));
    expect(location()).toBe("/vacancies?tab=in-progress&verdict=skip");
    expect(lastList(backend)).toContain("triage_verdict=skip");
    expect(chips()).toEqual(["Вердикт тріажу: Пропустити"]);
  });

  test("формат бере лише проаналізовані вакансії", async () => {
    const { user, backend } = await openList();
    await applyFilters(user, { Формат: "remote" });
    await waitFor(() => expect(titles()).toEqual(["Senior Backend Engineer"]));
    expect(location()).toBe("/vacancies?tab=in-progress&mode=remote");
    expect(lastList(backend)).toContain("work_mode=remote");
  });

  test("пошук + вердикт + формат працюють разом", async () => {
    const { user, backend } = await openList();
    await user.type(screen.getByRole("searchbox", { name: "Пошук" }), "backend{Enter}");
    await applyFilters(user, { "Вердикт тріажу": "analyse", Формат: "remote" });
    await waitFor(() => expect(location()).toBe("/vacancies?tab=in-progress&q=backend&verdict=analyse&mode=remote"));
    await waitFor(() => expect(titles()).toEqual(["Senior Backend Engineer"]));
    const request = new URL(lastList(backend).replace("GET ", ""), "http://x").searchParams;
    expect(Object.fromEntries(request)).toMatchObject({ query: "backend", triage_verdict: "analyse", work_mode: "remote" });
  });

  test("фільтри читаються з адреси", async () => {
    const { user } = await openList("/vacancies?tab=in-progress&verdict=maybe&mode=onsite");
    const panel = await openFilters(user);
    expect((within(panel).getByRole("combobox", { name: "Вердикт тріажу" }) as HTMLSelectElement).value).toBe("maybe");
    expect((within(panel).getByRole("combobox", { name: "Формат" }) as HTMLSelectElement).value).toBe("onsite");
  });

  test("невідомі значення в адресі ігноруються", async () => {
    const { backend, user } = await openList("/vacancies?tab=in-progress&verdict=great&mode=office");
    const panel = await openFilters(user);
    expect((within(panel).getByRole("combobox", { name: "Вердикт тріажу" }) as HTMLSelectElement).value).toBe("");
    expect((within(panel).getByRole("combobox", { name: "Формат" }) as HTMLSelectElement).value).toBe("");
    expect(lastList(backend)).not.toContain("triage_verdict");
    expect(lastList(backend)).not.toContain("work_mode");
  });

  test("«Скинути» в панелі скидає вердикт з форматом, пошук лишається", async () => {
    const { user } = await openList("/vacancies?tab=in-progress&q=e&verdict=skip&mode=remote");
    const panel = await openFilters(user);
    await user.click(within(panel).getByRole("button", { name: "Скинути" }));
    await waitFor(() => expect(location()).toBe("/vacancies?tab=in-progress&q=e"));
    await waitFor(() => expect(titles()).toHaveLength(6));
  });

  test("«Скинути пошук і фільтри» у порожній видачі скидає й пошук", async () => {
    const { user } = await openList("/vacancies?tab=in-progress&q=e&verdict=skip&mode=remote");
    await user.click(await screen.findByRole("button", { name: "Скинути пошук і фільтри" }));
    await waitFor(() => expect(location()).toBe("/vacancies?tab=in-progress"));
    await waitFor(() => expect(titles()).toHaveLength(6));
  });

  test("порожня видача: «Нічого не знайдено»", async () => {
    await openList("/vacancies?tab=in-progress&verdict=maybe&mode=remote");
    expect(await screen.findByText("Нічого не знайдено")).toBeDefined();
  });
});

describe("повернення до списку з деталей", () => {
  const PATH = "/vacancies?tab=in-progress&q=engineer&verdict=analyse&mode=remote";

  async function openDetails() {
    const opened = await openList(PATH);
    await opened.user.click(await screen.findByRole("link", { name: "Senior Backend Engineer" }));
    await screen.findByRole("heading", { level: 1, name: "Senior Backend Engineer" });
    return opened;
  }

  test("кнопка «Усі вакансії» повертає ті самі фільтри, фокус — на назві", async () => {
    const { user } = await openDetails();
    expect(location()).toBe(`/vacancies/1${PATH.slice("/vacancies".length)}`);
    await user.click(screen.getByRole("link", { name: "Усі вакансії" }));
    await waitFor(() => expect(location()).toBe(PATH));
    const title = await screen.findByRole("link", { name: "Senior Backend Engineer" });
    await waitFor(() => expect(document.activeElement).toBe(title));
    expect(chips()).toEqual(["Вердикт тріажу: Аналізувати", "Формат: Remote"]);
  });

  test("Escape повертає ті самі фільтри, фокус — на назві", async () => {
    const { user } = await openDetails();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(location()).toBe(PATH));
    const title = await screen.findByRole("link", { name: "Senior Backend Engineer" });
    await waitFor(() => expect(document.activeElement).toBe(title));
  });

  test("«Назад» і «Вперед» браузера теж зберігають фільтри", async () => {
    const { view } = await openDetails();
    await act(async () => view.router.navigate(-1));
    await waitFor(() => expect(location()).toBe(PATH));
    const title = await screen.findByRole("link", { name: "Senior Backend Engineer" });
    await waitFor(() => expect(document.activeElement).toBe(title));
    await act(async () => view.router.navigate(1));
    await screen.findByRole("heading", { level: 1, name: "Senior Backend Engineer" });
    expect(location()).toBe(`/vacancies/1${PATH.slice("/vacancies".length)}`);
  });
});

describe("запит тріажу: «Делегувати агенту»", () => {
  const TRIAGE = "Агент оцінить одну пачку нових вакансій (до 5) за тими самими правилами, що й автотріаж сервера, покаже підсумок і спитає, чи продовжувати.";

  test("під заголовком сторінки є блок, а старої кнопки «Запит для тріажу» нема", async () => {
    await openList();

    await findDelegate(TRIAGE);
    expect(screen.queryByRole("button", { name: "Запит для тріажу" })).toBeNull();
    expect(screen.queryByText(/Скопіює запит для Claude/)).toBeNull();
  });

  test("«Копіювати промпт» копіює текст запиту й підтверджує копіювання, не запускаючи тріаж", async () => {
    const { user, backend } = await openList();
    const writeText = vi.spyOn(navigator.clipboard, "writeText");

    const block = await findDelegate(TRIAGE);
    await user.click(block.getByRole("button", { name: "Копіювати промпт" }));

    expect(writeText).toHaveBeenCalledExactlyOnceWith("Triage the new jobs in joboffer");
    await waitFor(() => expect(block.getByRole("status").textContent).toBe(COPIED));
    expect(backend.bodies).toEqual([]);
  });

  test("не вдалося скопіювати — промпт розкрито для ручного копіювання", async () => {
    const { user } = await openList();
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValueOnce(new Error("denied"));

    const block = await findDelegate(TRIAGE);
    await user.click(block.getByRole("button", { name: "Копіювати промпт" }));

    await waitFor(() => expect(block.getByRole("status").textContent).toContain("Не вдалося скопіювати автоматично."));
    expect(block.getByRole("region", { name: "Промпт" }).textContent).toContain("Triage the new jobs in joboffer");
  });
});

describe("підказка «Що таке тріаж?»", () => {
  const HINT = { name: "Що таке тріаж?" };
  const HINT_TEXT = "Тріаж — швидка попередня оцінка вакансії: бал 0–100 і вердикт. Він нічого не ховає. Оцінює сервер за ключовими словами або агент за тими самими правилами. Повний аналіз глибший: порівнює вимоги з твоїми підтвердженими фактами й показує прогалини.";

  test("клік мишею відкриває підказку з точним текстом", async () => {
    const { user } = await openList();
    await user.click(screen.getByRole("button", HINT));
    expect(await screen.findByText(HINT_TEXT)).toBeDefined();
  });

  test("з клавіатури: фокус + Enter відкриває, Escape закриває", async () => {
    const { user } = await openList();
    screen.getByRole("button", HINT).focus();
    await user.keyboard("{Enter}");
    expect(await screen.findByText(HINT_TEXT)).toBeDefined();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByText(HINT_TEXT)).toBeNull());
  });

  test("з клавіатури: фокус + Space відкриває", async () => {
    const { user } = await openList();
    screen.getByRole("button", HINT).focus();
    await user.keyboard(" ");
    expect(await screen.findByText(HINT_TEXT)).toBeDefined();
  });

  test("дотик на touch-пристрої відкриває підказку без наведення", async () => {
    const { user } = await openList();
    await user.pointer([{ keys: "[TouchA>]", target: screen.getByRole("button", HINT) }, { keys: "[/TouchA]" }]);
    expect(await screen.findByText(HINT_TEXT)).toBeDefined();
  });

  test("на інших сторінках з «Делегувати агенту» підказки тріажу немає", async () => {
    const backend = jobsBackend(JOBS, ANALYSES);
    connectPrompts(backend);
    renderClient("/vacancies/new", backend.fetchFn);
    await findDelegate("Агент попросить посилання чи текст вакансії, збереже її й запропонує аналіз");
    expect(screen.queryByRole("button", HINT)).toBeNull();
  });
});
