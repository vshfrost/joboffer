/** Блок «Подача» в деталях вакансії: стани, лише дозволені дії, закриття з підтвердженням, «Не цікаво». */
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { apiApplication, apiDocument, apiJob, jobsBackend, type ApiApplication } from "./jobsBackend";
import { COPIED, findDelegate, queryDelegate } from "./delegateHarness";
import { connectPrompts } from "./promptsBackend";
import { renderClient } from "./testClient";

const JOB = apiJob(1, { title: "Senior Backend Engineer", company: "Northstar Labs", text: "Розробка API на Python." });

async function openDetails(application: ApiApplication | null, options: { documents?: boolean; job?: typeof JOB } = {}) {
  const backend = jobsBackend([options.job ?? JOB], [], options.documents === true ? [apiDocument(1, "cv", 3)] : [], application === null ? [] : [application]);
  connectPrompts(backend);
  const view = renderClient("/vacancies/1", backend.fetchFn);
  await screen.findByRole("heading", { level: 1, name: options.job?.title ?? "Senior Backend Engineer" });
  return { backend, view, user: userEvent.setup() };
}

const DELEGATE_APPLY = "Відкриє вакансію у твоєму браузері, знайде форму подачі й заповнить її. Надсилаєш заявку ти сам.";

const block = async () => within(await screen.findByRole("region", { name: "Подача" }));
const buttons = (scope: { queryAllByRole(role: "button"): HTMLElement[] }) => scope.queryAllByRole("button").map((button) => button.textContent);

const MOVE_BUTTONS = {
  applied: ["Є відповідь", "Перейти до співбесіди", "Отримано оффер", "Відмова", "Відкликати подачу"],
  replied: ["Перейти до співбесіди", "Отримано оффер", "Відмова", "Відкликати подачу"],
  interview: ["Отримано оффер", "Відмова", "Відкликати подачу"],
  offer: ["Відкликати подачу"],
  rejected: [],
  withdrawn: [],
} as const;
const LABELS = { applied: "Подано", replied: "Є відповідь", interview: "Співбесіда", offer: "Оффер", rejected: "Відмова", withdrawn: "Відкликано" } as const;

describe("не подано", () => {
  test("блок пропонує зафіксувати подачу", async () => {
    await openDetails(null);
    const panel = await block();
    expect(await panel.findByText("Подачу ще не зафіксовано")).toBeDefined();
    expect(panel.getByRole("button", { name: "Я подався" })).toBeDefined();
    expect(panel.queryByRole("button", { name: "Є відповідь" })).toBeNull();
  });

  test("поки подача вантажиться — скелетон, а «Не цікаво» ще недоступне", async () => {
    const backend = jobsBackend([JOB]);
    const hold = backend.holdApplication();
    renderClient("/vacancies/1", backend.fetchFn);
    await screen.findByRole("heading", { level: 1, name: "Senior Backend Engineer" });
    expect(screen.getByRole("status", { name: "Завантажуємо подачу" })).toBeDefined();
    expect((screen.getByRole("button", { name: "Не цікаво" }) as HTMLButtonElement).disabled).toBe(true);
    hold.release();
    expect(await screen.findByText("Подачу ще не зафіксовано")).toBeDefined();
    expect((screen.getByRole("button", { name: "Не цікаво" }) as HTMLButtonElement).disabled).toBe(false);
  });

  test("помилка завантаження — повідомлення з повтором; повтор показує блок", async () => {
    const backend = jobsBackend([JOB]);
    backend.failures.application = 1;
    renderClient("/vacancies/1", backend.fetchFn);
    const user = userEvent.setup();
    expect(await screen.findByText("Не вдалося завантажити подачу.")).toBeDefined();
    expect((screen.getByRole("button", { name: "Не цікаво" }) as HTMLButtonElement).disabled).toBe(true);
    await user.click(screen.getByRole("button", { name: "Спробувати подачу ще раз" }));
    expect(await screen.findByText("Подачу ще не зафіксовано")).toBeDefined();
  });
});

describe.each(Object.keys(MOVE_BUTTONS) as (keyof typeof MOVE_BUTTONS)[])("статус %s", (status) => {
  test("бейдж-текст, дата й канал, а дії — лише дозволені переходи", async () => {
    await openDetails(apiApplication(1, { status, channel: "linkedin", applied_on: "2026-10-18", ats: "ashby" }));
    const panel = await block();
    expect(await panel.findByText(LABELS[status])).toBeDefined();
    expect(panel.getByText("LinkedIn")).toBeDefined();
    expect(panel.getByText(/Подано 2026-10-18/)).toBeDefined();
    const actions = buttons(panel).filter((name) => name !== "Усі дані подачі" && name !== "Змінити дані");
    expect(actions).toEqual(MOVE_BUTTONS[status]);
  });
});

describe("закрита подача", () => {
  test.each(["rejected", "withdrawn"] as const)("%s: пояснення замість дій і «Змінити дані» лишається", async (status) => {
    await openDetails(apiApplication(1, { status }));
    const panel = await block();
    expect(await panel.findByText(/Подачу закрито/)).toBeDefined();
    expect(panel.getByText(/Відмови сховано зі списку вакансій, відкликані подачі — на вкладці «У процесі»/)).toBeDefined();
    expect(panel.queryByText(/фільтр «Закриті»/)).toBeNull();
    expect(panel.queryByRole("button", { name: "Відмова" })).toBeNull();
    expect(panel.queryByRole("button", { name: "Відкликати подачу" })).toBeNull();
  });
});

describe("усі дані подачі", () => {
  test("розкриваються за кнопкою: ATS, домени й адреси; порожнє — «Не вказано»", async () => {
    const { user } = await openDetails(apiApplication(1, { ats: "lever", company_domains: ["northstar.example", "jobs.northstar.example"], company_emails: ["careers@northstar.example"] }));
    const panel = await block();
    const toggle = await panel.findByRole("button", { name: "Усі дані подачі" });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(panel.queryByText("careers@northstar.example")).toBeNull();
    await user.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(panel.getByText("Lever")).toBeDefined();
    expect(panel.getByText("northstar.example, jobs.northstar.example")).toBeDefined();
    expect(panel.getByText("careers@northstar.example")).toBeDefined();
  });

  test("без ATS, доменів і адрес — «Не вказано»", async () => {
    const { user } = await openDetails(apiApplication(1));
    const panel = await block();
    await user.click(await panel.findByRole("button", { name: "Усі дані подачі" }));
    expect(panel.getAllByText("Не вказано")).toHaveLength(3);
  });

  test("довгі домени й адреси переносяться, не ламаючи блок", async () => {
    const long = `${"very-long-company-name".repeat(6)}.example`;
    const { user } = await openDetails(apiApplication(1, { company_domains: [long], company_emails: [`recruiter@${long}`] }));
    const panel = await block();
    await user.click(await panel.findByRole("button", { name: "Усі дані подачі" }));
    expect(panel.getByText(long).className).toContain("[overflow-wrap:anywhere]");
    expect(panel.getByText(`recruiter@${long}`).className).toContain("[overflow-wrap:anywhere]");
  });
});

describe("перехід статусу", () => {
  test("успіх показує новий статус лише після відповіді сервера", async () => {
    const { user, backend } = await openDetails(apiApplication(1));
    const panel = await block();
    const hold = backend.holdApplication();
    await user.click(await panel.findByRole("button", { name: "Перейти до співбесіди" }));
    // Відповіді ще нема: статус старий, кнопки заблоковано від повторного натискання.
    expect(panel.getByText("Подано", { selector: "span" })).toBeDefined();
    expect((panel.getByRole("button", { name: "Є відповідь" }) as HTMLButtonElement).disabled).toBe(true);
    expect(backend.bodies.at(-1)).toEqual({ status: "interview" });
    hold.release();
    await waitFor(() => expect(panel.getByText("Співбесіда", { selector: "span" })).toBeDefined());
    expect(buttons(panel).filter((name) => name !== "Усі дані подачі" && name !== "Змінити дані")).toEqual(MOVE_BUTTONS.interview);
    expect(screen.getByRole("status", { name: "Результат подачі" }).textContent).toContain("Статус змінено: «Співбесіда».");
  });

  test("подвійний клік — один запит", async () => {
    const { user, backend } = await openDetails(apiApplication(1));
    const panel = await block();
    const hold = backend.holdApplication();
    const button = await panel.findByRole("button", { name: "Є відповідь" });
    await user.dblClick(button);
    hold.release();
    await waitFor(() => expect(panel.getByText("Є відповідь", { selector: "span" })).toBeDefined());
    expect(backend.requests.filter((line) => line.startsWith("POST /api/jobs/1/application/status"))).toHaveLength(1);
  });

  test("два натискання в одній подачі подій — один запит", async () => {
    const { backend } = await openDetails(apiApplication(1));
    const panel = await block();
    const button = await panel.findByRole("button", { name: "Є відповідь" });
    act(() => {
      button.click();
      button.click();
    });
    await waitFor(() => expect(panel.getByText("Є відповідь", { selector: "span" })).toBeDefined());
    expect(backend.requests.filter((line) => line.startsWith("POST /api/jobs/1/application/status"))).toHaveLength(1);
  });

  test("збій сервера не міняє статус і пояснює це; повтор працює", async () => {
    const { user, backend } = await openDetails(apiApplication(1));
    backend.failures.move = 1;
    const panel = await block();
    await user.click(await panel.findByRole("button", { name: "Є відповідь" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Не вдалося змінити статус. Статус не змінено.");
    expect(panel.getByText("Подано", { selector: "span" })).toBeDefined();
    await user.click(panel.getByRole("button", { name: "Є відповідь" }));
    await waitFor(() => expect(panel.getByText("Є відповідь", { selector: "span" })).toBeDefined());
    expect(screen.queryByRole("alert")).toBeNull();
  });

  test("подачу вже прибрано (404) — просить оновити сторінку, статус старий", async () => {
    const { user, backend } = await openDetails(apiApplication(1));
    const panel = await block();
    backend.applications = [];
    await user.click(await panel.findByRole("button", { name: "Є відповідь" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Подачі нема — онови сторінку.");
    expect(panel.getByText("Подано", { selector: "span" })).toBeDefined();
  });

  test("сервер відхилив перехід (422) — його текст показано, статус старий", async () => {
    const { user, backend } = await openDetails(apiApplication(1, { status: "interview" }));
    const panel = await block();
    // Інший клієнт уже закрив подачу: клієнт ще показує стару кнопку.
    backend.applications = [apiApplication(1, { status: "rejected" })];
    await user.click(await panel.findByRole("button", { name: "Отримано оффер" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Подачу вже закрито (rejected): статус більше не змінюється.");
    expect(panel.getByText("Співбесіда", { selector: "span" })).toBeDefined();
  });
});

describe("закриття з підтвердженням", () => {
  test.each([
    ["Відмова", "Зафіксувати відмову?", "rejected", "Відмова"],
    ["Відкликати подачу", "Відкликати подачу?", "withdrawn", "Відкликано"],
  ])("«%s»: діалог, підтвердження міняє статус", async (button, title, status, label) => {
    const { user, backend } = await openDetails(apiApplication(1));
    const panel = await block();
    await user.click(await panel.findByRole("button", { name: button }));
    const dialog = screen.getByRole("alertdialog");
    expect(within(dialog).getByText(title)).toBeDefined();
    expect(within(dialog).getByText(/Вакансія й документи залишаться/)).toBeDefined();
    expect(backend.requests.some((line) => line.startsWith("POST /api/jobs/1/application/status"))).toBe(false);
    await user.click(within(dialog).getByRole("button", { name: "Підтвердити" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect(backend.bodies.at(-1)).toEqual({ status });
    expect(await panel.findByText(label, { selector: "span" })).toBeDefined();
    expect(await panel.findByText(/Подачу закрито/)).toBeDefined();
    // Кнопка, що відкривала діалог, зникла: фокус іде на заголовок блоку.
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("heading", { level: 2, name: "Подача" })));
  });

  test("скасування не міняє нічого й повертає фокус на кнопку", async () => {
    const { user, backend } = await openDetails(apiApplication(1));
    const panel = await block();
    const trigger = await panel.findByRole("button", { name: "Відмова" });
    await user.click(trigger);
    await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Скасувати" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect(backend.requests.some((line) => line.startsWith("POST /api/jobs/1/application/status"))).toBe(false);
    expect(panel.getByText("Подано", { selector: "span" })).toBeDefined();
    expect(document.activeElement).toBe(trigger);
  });

  test("Escape закриває діалог без змін", async () => {
    const { user, backend } = await openDetails(apiApplication(1));
    const panel = await block();
    await user.click(await panel.findByRole("button", { name: "Відкликати подачу" }));
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect(screen.getByRole("heading", { level: 1, name: "Senior Backend Engineer" })).toBeDefined();
    expect(backend.requests.some((line) => line.startsWith("POST /api/jobs/1/application/status"))).toBe(false);
  });

  test("збій у діалозі лишає його відкритим і нічого не закриває", async () => {
    const { user, backend } = await openDetails(apiApplication(1));
    backend.failures.move = 1;
    const panel = await block();
    await user.click(await panel.findByRole("button", { name: "Відмова" }));
    const dialog = screen.getByRole("alertdialog");
    await user.click(within(dialog).getByRole("button", { name: "Підтвердити" }));
    expect((await within(dialog).findByRole("alert")).textContent).toContain("Не вдалося змінити статус. Статус не змінено.");
    await user.click(within(dialog).getByRole("button", { name: "Підтвердити" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect(await panel.findByText("Відмова", { selector: "span" })).toBeDefined();
  });
});

describe("«Не цікаво» у деталях", () => {
  test("для поданої вакансії недоступне з видимим поясненням", async () => {
    await openDetails(apiApplication(1));
    await block();
    await screen.findByText("Подано", { selector: "span" });
    const hide = screen.getByRole("button", { name: "Не цікаво" }) as HTMLButtonElement;
    expect(hide.disabled).toBe(true);
    expect(screen.getByText("Є подача — вакансію не ховають. Керуй нею через статус подачі.")).toBeDefined();
  });

  test("для закритої подачі теж недоступне", async () => {
    await openDetails(apiApplication(1, { status: "withdrawn" }));
    await screen.findByText("Відкликано", { selector: "span" });
    expect((screen.getByRole("button", { name: "Не цікаво" }) as HTMLButtonElement).disabled).toBe(true);
  });

  test("для неподаної активне й відкриває діалог", async () => {
    const { user } = await openDetails(null);
    await screen.findByText("Подачу ще не зафіксовано");
    await waitFor(() => expect((screen.getByRole("button", { name: "Не цікаво" }) as HTMLButtonElement).disabled).toBe(false));
    expect(screen.queryByText(/Є подача — вакансію не ховають/)).toBeNull();
    await user.click(screen.getByRole("button", { name: "Не цікаво" }));
    expect(within(screen.getByRole("alertdialog")).getByText("Сховати вакансію?")).toBeDefined();
  });

  test("подача з'явилась в іншому місці: сервер відмовив (409) — діалог пояснює, вакансія лишається", async () => {
    const { user, backend } = await openDetails(null);
    await screen.findByText("Подачу ще не зафіксовано");
    backend.applications = [apiApplication(1)];
    await user.click(screen.getByRole("button", { name: "Не цікаво" }));
    await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Сховати" }));
    expect((await screen.findByRole("alert")).textContent).toContain("На вакансію є подача — поданих вакансій не ховають.");
    expect(backend.jobs[0]?.dismissed_at).toBeNull();
  });
});

describe("документи вакансії поруч із подачею", () => {
  test("PDF версії відкривається в новій вкладці, а слова «відправлено» нема", async () => {
    await openDetails(apiApplication(1), { documents: true });
    const link = await screen.findByRole("link", { name: "CV, версія 3: відкрити PDF у новій вкладці" });
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
    expect(link.getAttribute("href")).toContain("/api/documents/1/pdf");
    expect(document.body.textContent).not.toMatch(/відправлено/i);
  });
});

describe("делегування подачі агенту", () => {
  test("подачі нема — у «Подачі» є блок «Делегувати агенту» із запитом на подачу цієї вакансії, а «Я подався» лишається", async () => {
    const { user } = await openDetails(null);
    const writeText = vi.spyOn(navigator.clipboard, "writeText");
    const panel = await block();
    const delegate = await findDelegate(DELEGATE_APPLY, await screen.findByRole("region", { name: "Подача" }));

    await user.click(delegate.getByRole("button", { name: "Копіювати промпт" }));

    expect(writeText).toHaveBeenCalledWith("Apply to job #1 in joboffer");
    await waitFor(() => expect(delegate.getByRole("status").textContent).toBe(COPIED));
    expect(panel.getByRole("button", { name: "Я подався" })).toBeDefined();
  });

  test("подача є — блоку нема", async () => {
    await openDetails(apiApplication(1));
    const panel = await block();
    expect(await panel.findByText("Подано", { selector: "span" })).toBeDefined();
    expect(queryDelegate(DELEGATE_APPLY)).toBeNull();
  });

  test("форма «Я подався» відкрита — блоку нема", async () => {
    const { user } = await openDetails(null);
    const panel = await block();
    await findDelegate(DELEGATE_APPLY, await screen.findByRole("region", { name: "Подача" }));
    await user.click(panel.getByRole("button", { name: "Я подався" }));
    expect(queryDelegate(DELEGATE_APPLY)).toBeNull();
  });
});
