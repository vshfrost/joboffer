import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { apiJob, jobsBackend, type ApiJob } from "./jobsBackend";
import { renderClient } from "./testClient";
import { setViewport } from "./viewport";

const FULL = apiJob(1, {
  title: "Senior Backend Engineer",
  company: "Northline Pay",
  location: "Spain · Remote",
  source: "manual",
  url: "https://northline.example/jobs/1",
  created_at: "2026-10-19T09:00:00Z",
  text: "Розробка платіжних сервісів.\n\nPython і PostgreSQL.",
});
const OTHER = apiJob(2, { title: "Rust Developer", company: "Cedar Ledger", created_at: "2026-10-18T09:00:00Z" });
const WAITING = apiJob(3, { title: "Python Engineer — Payments", company: "Brisa Systems", source: "linkedin_alert", text: null, url: "https://www.linkedin.com/jobs/view/4012345678" });

const location = () => screen.getByTestId("location").textContent;

async function openDetails(jobs: ApiJob[], path: string, name = "Senior Backend Engineer") {
  const backend = jobsBackend(jobs);
  const view = renderClient(path, backend.fetchFn);
  await screen.findByRole("heading", { level: 1, name });
  return { backend, view, user: userEvent.setup() };
}

describe("деталі вакансії", () => {
  test("показують повну назву, компанію, локацію, джерело, день і посилання", async () => {
    await openDetails([FULL], "/vacancies/1");
    expect(screen.getByRole("heading", { level: 1, name: "Senior Backend Engineer" })).toBeDefined();
    expect(screen.getByText("Northline Pay")).toBeDefined();
    expect(screen.getByText("Spain · Remote")).toBeDefined();
    expect(screen.getByText("manual")).toBeDefined();
    expect(screen.getByText("2026-10-19")).toBeDefined();
    const link = screen.getByRole("link", { name: "https://northline.example/jobs/1" });
    expect(link.getAttribute("href")).toBe("https://northline.example/jobs/1");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
  });

  test("заголовок вкладки — назва вакансії", async () => {
    await openDetails([FULL], "/vacancies/1");
    expect(document.title).toBe("Senior Backend Engineer · Вакансії · joboffer");
  });

  test("вакансія без локації й посилання не малює порожніх рядків", async () => {
    await openDetails([OTHER], "/vacancies/2", "Rust Developer");
    expect(screen.queryByRole("link", { name: /^https?:/ })).toBeNull();
    expect(screen.queryByText("Локація")).toBeNull();
  });

  test("опис — звичайний текст зі збереженням абзаців", async () => {
    await openDetails([FULL], "/vacancies/1");
    const text = await screen.findByText(/Розробка платіжних сервісів/);
    expect(text.textContent).toBe("Розробка платіжних сервісів.\n\nPython і PostgreSQL.");
    expect(text.className).toContain("whitespace-pre-wrap");
    expect(text.className).toContain("[overflow-wrap:anywhere]");
  });

  test("HTML в описі третьої сторони не виконується й не стає розміткою", async () => {
    const hostile = apiJob(5, { title: "Trap", text: '<img src=x onerror="window.pwned=1"><script>window.pwned=2</script><b>жирний</b>' });
    await openDetails([hostile], "/vacancies/5", "Trap");
    expect(document.querySelector("main img")).toBeNull();
    expect(document.querySelector("main script")).toBeNull();
    expect(document.querySelector("main b")).toBeNull();
    expect(await screen.findByText(/<img src=x onerror=/)).toBeDefined();
    expect((window as unknown as { pwned?: number }).pwned).toBeUndefined();
  });

  test("HTML в назві й компанії теж лишається текстом", async () => {
    const hostile = apiJob(5, { title: "<i>Boss</i>", company: "<u>Evil</u>" });
    await openDetails([hostile], "/vacancies/5", "<i>Boss</i>");
    expect(document.querySelector("main i")).toBeNull();
    expect(document.querySelector("main u")).toBeNull();
    expect(screen.getByText("<u>Evil</u>")).toBeDefined();
  });

  test("оцінка — «Не оцінено» з постійним застереженням, не 0 %", async () => {
    await openDetails([FULL], "/vacancies/1");
    const section = screen.getByRole("region", { name: "Відповідність профілю" });
    expect(await within(section).findByText("Не оцінено")).toBeDefined();
    expect(within(section).getByText("Оцінка за рубрикою 0–100. Це не ймовірність отримати оффер.")).toBeDefined();
    expect(section.textContent).not.toContain("0%");
  });

  test("документи CV і CL — порожній стан", async () => {
    await openDetails([FULL], "/vacancies/1");
    const section = screen.getByRole("region", { name: "Документи" });
    expect(await within(section).findByText("CV ще немає")).toBeDefined();
    expect(within(section).getByText("Cover letter ще немає")).toBeDefined();
  });

  test("«потрібен текст» — позначка стану даних і підказка вставити опис, без блоку опису", async () => {
    await openDetails([WAITING], "/vacancies/3", "Python Engineer — Payments");
    expect(screen.getByText("Потрібен текст")).toBeDefined();
    expect(screen.getByText(/Опису ще нема/)).toBeDefined();
    expect(screen.queryByRole("heading", { name: "Про роль" })).toBeNull();
    expect(screen.queryByText("Оцінено")).toBeNull();
  });

  test("вакансія з текстом не має позначки «Потрібен текст»", async () => {
    await openDetails([FULL], "/vacancies/1");
    expect(screen.queryByText("Потрібен текст")).toBeNull();
    expect(await screen.findByRole("heading", { level: 2, name: "Про роль" })).toBeDefined();
  });

  test("схована вакансія показує, що сховано, і причину", async () => {
    const hidden = apiJob(7, { title: "Hidden Role", dismissed_at: "2026-10-20T09:00:00Z", dismiss_reason: "не цікаво" });
    await openDetails([hidden], "/vacancies/7", "Hidden Role");
    expect(screen.getByText("Сховано: не цікаво")).toBeDefined();
    expect(screen.getByRole("button", { name: "Повернути" })).toBeDefined();
    expect(screen.queryByRole("button", { name: "Не цікаво" })).toBeNull();
  });
});

describe("відкриття й повернення", () => {
  test("клік на посаду відкриває деталі замість списку, навігація лишається", async () => {
    const { user } = await openDetails([FULL, OTHER], "/vacancies", "Вакансії");
    await user.click(await screen.findByRole("link", { name: "Senior Backend Engineer" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Senior Backend Engineer" })).toBeDefined();
    expect(location()).toBe("/vacancies/1");
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.getByRole("navigation", { name: "Головна навігація" })).toBeDefined();
  });

  test("«Усі вакансії» повертає список зі збереженими фільтрами, а фокус — на назву вакансії", async () => {
    const { user } = await openDetails([FULL, OTHER], "/vacancies?q=e&source=manual", "Вакансії");
    await user.click(await screen.findByRole("link", { name: "Rust Developer" }));
    await waitFor(() => expect(location()).toBe("/vacancies/2?q=e&source=manual"));
    await screen.findByRole("heading", { level: 1, name: "Rust Developer" });
    await user.click(screen.getByRole("link", { name: "Усі вакансії" }));
    await waitFor(() => expect(location()).toBe("/vacancies?q=e&source=manual"));
    const title = await screen.findByRole("link", { name: "Rust Developer" });
    await waitFor(() => expect(document.activeElement).toBe(title));
    expect((screen.getByRole("searchbox", { name: "Пошук" }) as HTMLInputElement).value).toBe("e");
  });

  test("Escape повертає список зі збереженими фільтрами й фокусом на назві", async () => {
    const { user } = await openDetails([FULL, OTHER], "/vacancies?tab=all&days=30", "Вакансії");
    await user.click(await screen.findByRole("link", { name: "Senior Backend Engineer" }));
    await screen.findByRole("heading", { level: 1, name: "Senior Backend Engineer" });
    await user.keyboard("{Escape}");
    await waitFor(() => expect(location()).toBe("/vacancies?tab=all&days=30"));
    const title = await screen.findByRole("link", { name: "Senior Backend Engineer" });
    await waitFor(() => expect(document.activeElement).toBe(title));
  });

  test("кнопка «Назад» браузера теж повертає ті самі фільтри й фокус", async () => {
    const { user, view } = await openDetails([FULL, OTHER], "/vacancies?q=Developer", "Вакансії");
    await user.click(await screen.findByRole("link", { name: "Rust Developer" }));
    await screen.findByRole("heading", { level: 1, name: "Rust Developer" });
    await act(async () => view.router.navigate(-1));
    await waitFor(() => expect(location()).toBe("/vacancies?q=Developer"));
    const title = await screen.findByRole("link", { name: "Rust Developer" });
    await waitFor(() => expect(document.activeElement).toBe(title));
  });

  test("пряме відкриття не має що фокусувати: «Усі вакансії» веде на чистий список", async () => {
    const { user } = await openDetails([FULL], "/vacancies/1");
    await user.click(screen.getByRole("link", { name: "Усі вакансії" }));
    await waitFor(() => expect(location()).toBe("/vacancies"));
    expect(await screen.findByRole("link", { name: "Senior Backend Engineer" })).toBeDefined();
  });

  test("Escape з відкритим діалогом закриває діалог, а не залишає сторінку", async () => {
    const { user } = await openDetails([FULL], "/vacancies/1");
    await user.click(screen.getByRole("button", { name: "Не цікаво" }));
    await screen.findByRole("alertdialog");
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect(location()).toBe("/vacancies/1");
  });

  test("інші клавіші не повертають до списку", async () => {
    await openDetails([FULL], "/vacancies/1");
    fireEvent.keyDown(document.body, { key: "Enter" });
    expect(location()).toBe("/vacancies/1");
  });
});

describe("пряме відкриття й стани", () => {
  test("неіснуюча вакансія — «не знайдено»", async () => {
    const backend = jobsBackend([FULL]);
    renderClient("/vacancies/99", backend.fetchFn);
    expect(await screen.findByRole("heading", { level: 1, name: "Вакансію не знайдено" })).toBeDefined();
    expect(screen.getByRole("link", { name: "Усі вакансії" }).getAttribute("href")).toBe("/vacancies");
  });

  test.each(["abc", "0", "-1", "1.5", "01"])("адреса /vacancies/%s — «не знайдено» без запиту до сервера", async (raw) => {
    const backend = jobsBackend([FULL]);
    renderClient(`/vacancies/${raw}`, backend.fetchFn);
    expect(await screen.findByRole("heading", { level: 1, name: "Вакансію не знайдено" })).toBeDefined();
    expect(backend.requests).toEqual([]);
  });

  test("поки вакансія вантажиться — скелетон зі статусом", async () => {
    const backend = jobsBackend([FULL]);
    const gate = backend.hold();
    renderClient("/vacancies/1", backend.fetchFn);
    expect(await screen.findByRole("status", { name: "Завантажуємо вакансію" })).toBeDefined();
    await act(async () => gate.release());
  });

  test("помилка сервера — тривога з повтором", async () => {
    const backend = jobsBackend([FULL]);
    backend.failures.get = 1;
    renderClient("/vacancies/1", backend.fetchFn);
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Не вдалося завантажити вакансію.");
    await userEvent.setup().click(within(alert).getByRole("button", { name: "Спробувати ще раз" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Senior Backend Engineer" })).toBeDefined();
  });

  test("адреса з іншим номером підтягує іншу вакансію", async () => {
    const { view } = await openDetails([FULL, OTHER], "/vacancies/1");
    await act(async () => view.router.navigate("/vacancies/2"));
    expect(await screen.findByRole("heading", { level: 1, name: "Rust Developer" })).toBeDefined();
  });

  test("на mobile деталі показують ті самі дані", async () => {
    setViewport("mobile");
    await openDetails([FULL], "/vacancies/1");
    expect(screen.getByText("Northline Pay")).toBeDefined();
    expect(screen.getByRole("region", { name: "Відповідність профілю" })).toBeDefined();
    expect(screen.getByRole("region", { name: "Документи" })).toBeDefined();
  });
});
