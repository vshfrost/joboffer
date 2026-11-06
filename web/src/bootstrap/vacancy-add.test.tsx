import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { CLAUDE, connectAgents } from "./agentsBackend";
import { delegateBlocks } from "./delegateHarness";
import { apiJob, jobsBackend, type ApiJob } from "./jobsBackend";
import { connectPrompts } from "./promptsBackend";
import { renderClient } from "./testClient";
import { setViewport } from "./viewport";

const EXISTING = apiJob(1, { title: "Senior Backend Engineer", company: "Northline Pay", url: "https://northline.example/jobs/1", text: "Розробка платіжних сервісів" });
const WAITING = apiJob(2, {
  title: "Python Engineer — Payments",
  company: "Brisa Systems",
  source: "linkedin_alert",
  url: "https://www.linkedin.com/jobs/view/4012345678",
  text: null,
});
const POSTING = "Senior Rust engineer. Remote. Tokio, Postgres.";

const location = () => screen.getByTestId("location").textContent;
const text = () => screen.getByLabelText("Текст опису") as HTMLTextAreaElement;
const url = () => screen.getByLabelText("Посилання") as HTMLInputElement;
const title = () => screen.getByLabelText("Назва") as HTMLInputElement;
const company = () => screen.getByLabelText("Компанія") as HTMLInputElement;
const submit = () => screen.getByRole("button", { name: "Додати" });

async function openForm(jobs: ApiJob[] = [EXISTING, WAITING], path = "/vacancies/new") {
  const backend = jobsBackend(jobs);
  const view = renderClient(path, backend.fetchFn);
  await screen.findByRole("heading", { level: 1, name: "Додати вакансію" });
  return { backend, view, user: userEvent.setup() };
}

describe("кнопка «Додати вакансію» на списку", () => {
  test("веде на форму й несе поточні фільтри", async () => {
    const backend = jobsBackend([EXISTING]);
    renderClient("/vacancies?tab=all&q=north", backend.fetchFn);
    const user = userEvent.setup();
    await screen.findByRole("status", { name: "Результат" });
    const link = screen.getByRole("link", { name: "Додати вакансію" });
    expect(link.getAttribute("href")).toBe("/vacancies/new?tab=all&q=north");
    await user.click(link);
    expect(await screen.findByRole("heading", { level: 1, name: "Додати вакансію" })).toBeDefined();
    await waitFor(() => expect(location()).toBe("/vacancies/new?tab=all&q=north"));
  });

  test("є і на порожньому списку, і в табі «Сховані»", async () => {
    const backend = jobsBackend([]);
    renderClient("/vacancies?tab=dismissed", backend.fetchFn);
    await screen.findByRole("status", { name: "Результат" });
    expect(screen.getByRole("link", { name: "Додати вакансію" })).toBeDefined();
  });
});

describe("форма", () => {
  test("відкривається за прямою адресою: заголовок вкладки й чотири поля з видимими підписами", async () => {
    await openForm();
    expect(document.title).toBe("Додати вакансію · Вакансії · joboffer");
    for (const label of ["Текст опису", "Посилання", "Назва", "Компанія"]) {
      expect(screen.getByLabelText(label)).toBeDefined();
      expect(screen.getByText(label, { selector: "label" })).toBeDefined();
    }
    expect(text().value).toBe("");
  });

  test("текст — обов'язкове поле, решта — за бажанням", async () => {
    await openForm();
    expect(text().getAttribute("aria-required")).toBe("true");
    expect(url().getAttribute("aria-required")).toBeNull();
    expect(screen.getByText("Обов’язково. Встав повний текст вакансії.")).toBeDefined();
    expect(screen.getByText("Необов’язково. Посилання LinkedIn на вакансію з алерту допише текст у неї.")).toBeDefined();
  });

  test("не є сторінкою вакансії: «new» не шукається як номер", async () => {
    const { backend } = await openForm();
    expect(backend.requests).toEqual([]);
  });
});

describe("успішне додавання", () => {
  test("нова вакансія → її деталі з повідомленням; на сервер іде те, що ввели", async () => {
    const { user, backend } = await openForm();
    await user.type(text(), POSTING);
    await user.type(title(), "Rust Engineer");
    await user.type(company(), "Tokio Ltd");
    await user.click(submit());
    expect(await screen.findByRole("heading", { level: 1, name: "Rust Engineer" })).toBeDefined();
    expect(backend.bodies).toEqual([{ text: POSTING, url: "", title: "Rust Engineer", company: "Tokio Ltd" }]);
    await waitFor(() => expect(location()).toBe("/vacancies/3"));
    expect(screen.getByRole("status", { name: "Повідомлення" }).textContent).toBe("Вакансію додано");
    expect(await screen.findByText(POSTING)).toBeDefined();
  });

  test("з посиланням: у деталях воно вже нормалізоване сервером", async () => {
    const { user } = await openForm();
    await user.type(text(), POSTING);
    await user.type(url(), "https://rust.example/jobs/9");
    await user.click(submit());
    expect(await screen.findByRole("link", { name: "https://rust.example/jobs/9" })).toBeDefined();
  });

  test("Enter у однорядковому полі теж додає", async () => {
    const { user, backend } = await openForm();
    await user.type(text(), POSTING);
    await user.type(title(), "Rust Engineer{Enter}");
    await screen.findByRole("heading", { level: 1, name: "Rust Engineer" });
    expect(backend.bodies).toHaveLength(1);
  });

  test("подвійне натискання шле один запит", async () => {
    const { user, backend } = await openForm();
    await user.type(text(), POSTING);
    await user.dblClick(submit());
    await waitFor(() => expect(location()).toBe("/vacancies/3"));
    expect(backend.bodies).toHaveLength(1);
  });

  test("фільтри списку лишаються в адресі деталей, тож «Усі вакансії» їх повертає", async () => {
    const { user } = await openForm([EXISTING], "/vacancies/new?q=north");
    await user.type(text(), POSTING);
    await user.click(submit());
    await screen.findByRole("status", { name: "Повідомлення" });
    await waitFor(() => expect(location()).toBe("/vacancies/2?q=north"));
    await user.click(screen.getByRole("link", { name: "Усі вакансії" }));
    await waitFor(() => expect(location()).toBe("/vacancies?q=north"));
  });

  test("повідомлення живе лише на цьому відкритті деталей", async () => {
    const { user } = await openForm();
    await user.type(text(), POSTING);
    await user.click(submit());
    await screen.findByRole("status", { name: "Повідомлення" });
    await user.click(screen.getByRole("link", { name: "Усі вакансії" }));
    await screen.findByRole("status", { name: "Результат" });
    await user.click(screen.getByRole("link", { name: "Senior Backend Engineer" }));
    await screen.findByRole("heading", { level: 1, name: "Senior Backend Engineer" });
    expect(screen.queryByRole("status", { name: "Повідомлення" })).toBeNull();
  });
});

describe("дубль", () => {
  test("той самий текст в іншому регістрі й з іншими пробілами → наявна вакансія й «Така вакансія вже є»", async () => {
    const { user, backend } = await openForm();
    await user.type(text(), "  розробка   ПЛАТІЖНИХ сервісів ");
    await user.click(submit());
    expect(await screen.findByRole("heading", { level: 1, name: "Senior Backend Engineer" })).toBeDefined();
    expect(screen.getByRole("status", { name: "Повідомлення" }).textContent).toBe("Така вакансія вже є");
    await waitFor(() => expect(location()).toBe("/vacancies/1"));
    expect(backend.jobs).toHaveLength(2);
  });

  test("той самий URL з іншим текстом → наявна вакансія", async () => {
    const { user } = await openForm();
    await user.type(text(), "Зовсім інший текст");
    await user.type(url(), "https://northline.example/jobs/1");
    await user.click(submit());
    expect(await screen.findByRole("heading", { level: 1, name: "Senior Backend Engineer" })).toBeDefined();
    expect(screen.getByRole("status", { name: "Повідомлення" }).textContent).toBe("Така вакансія вже є");
  });
});

describe("посилання LinkedIn на вакансію «потрібен текст»", () => {
  test("текст дописується в ту саму вакансію, назва й компанія лишаються, повідомлення про це", async () => {
    const { user, backend } = await openForm();
    await user.type(text(), POSTING);
    await user.type(url(), "https://es.linkedin.com/comm/jobs/view/dev-at-brisa-4012345678/?trackingId=x");
    await user.type(title(), "Інша назва");
    await user.click(submit());
    expect(await screen.findByRole("heading", { level: 1, name: "Python Engineer — Payments" })).toBeDefined();
    await waitFor(() => expect(location()).toBe("/vacancies/2"));
    expect(screen.getByRole("status", { name: "Повідомлення" }).textContent).toBe("Текст додано у вакансію з алерту");
    expect(await screen.findByText(POSTING)).toBeDefined();
    expect(screen.queryByText("Потрібен текст")).toBeNull();
    expect(screen.getByText("Brisa Systems")).toBeDefined();
    expect(backend.jobs).toHaveLength(2);
  });

  test("підказка в деталях веде на форму з уже підставленим посиланням", async () => {
    const backend = jobsBackend([WAITING]);
    renderClient("/vacancies/2", backend.fetchFn);
    const user = userEvent.setup();
    await screen.findByRole("heading", { level: 1, name: "Python Engineer — Payments" });
    await user.click(screen.getByRole("link", { name: "Додати текст опису" }));
    await screen.findByRole("heading", { level: 1, name: "Додати вакансію" });
    expect(url().value).toBe("https://www.linkedin.com/jobs/view/4012345678");
    await user.type(text(), POSTING);
    await user.click(submit());
    expect(await screen.findByText("Текст додано у вакансію з алерту")).toBeDefined();
  });

  test("у вакансії з текстом такої підказки нема", async () => {
    const backend = jobsBackend([EXISTING]);
    renderClient("/vacancies/1", backend.fetchFn);
    await screen.findByRole("heading", { level: 1, name: "Senior Backend Engineer" });
    expect(screen.queryByRole("link", { name: "Додати текст опису" })).toBeNull();
  });
});

describe("помилки", () => {
  test("порожній текст і недійсне посилання — помилки біля полів, уведене лишається, фокус на першому полі з помилкою", async () => {
    const { user, backend } = await openForm();
    await user.type(url(), "example.com/job");
    await user.type(title(), "Моя назва");
    await user.click(submit());
    expect(await screen.findByText("Встав текст опису вакансії.")).toBeDefined();
    expect(screen.getByText("Посилання має починатися з http:// або https://.")).toBeDefined();
    expect(text().getAttribute("aria-invalid")).toBe("true");
    expect(url().getAttribute("aria-invalid")).toBe("true");
    expect(title().getAttribute("aria-invalid")).toBeNull();
    expect(text().getAttribute("aria-describedby")).not.toBeNull();
    const described = (text().getAttribute("aria-describedby") ?? "").split(" ").map((id) => document.getElementById(id)?.textContent ?? "");
    expect(described.join(" ")).toContain("Встав текст опису вакансії.");
    expect(url().value).toBe("example.com/job");
    expect(title().value).toBe("Моя назва");
    expect(document.activeElement).toBe(text());
    expect(location()).toBe("/vacancies/new");
    expect(backend.jobs).toHaveLength(2);
  });

  test("помилка лише в посиланні — фокус на ньому", async () => {
    const { user } = await openForm();
    await user.type(text(), POSTING);
    await user.type(url(), "ftp://x.example/1");
    await user.click(submit());
    await screen.findByText("Посилання має починатися з http:// або https://.");
    expect(document.activeElement).toBe(url());
    expect(text().value).toBe(POSTING);
  });

  test("після виправлення форма додає, а старі помилки зникають", async () => {
    const { user } = await openForm();
    await user.click(submit());
    await screen.findByText("Встав текст опису вакансії.");
    await user.type(text(), POSTING);
    await user.click(submit());
    await waitFor(() => expect(location()).toBe("/vacancies/3"));
    expect(screen.queryByText("Встав текст опису вакансії.")).toBeNull();
  });

  test("помилка сервера: тривога, нічого не стерто, повтор вдається", async () => {
    const { user, backend } = await openForm();
    backend.failures.add = 1;
    await user.type(text(), POSTING);
    await user.type(company(), "Tokio Ltd");
    await user.click(submit());
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Не вдалося додати вакансію. Введене не втрачено — спробуй ще раз.");
    expect(text().value).toBe(POSTING);
    expect(company().value).toBe("Tokio Ltd");
    expect(location()).toBe("/vacancies/new");
    await user.click(submit());
    await waitFor(() => expect(location()).toBe("/vacancies/3"));
    expect(backend.bodies).toHaveLength(2);
  });
});

describe("скасування", () => {
  test("«Скасувати» повертає список із попередніми фільтрами й нічого не шле", async () => {
    const { user, backend } = await openForm([EXISTING], "/vacancies/new?tab=dismissed&q=x");
    await user.type(text(), "щось ввів");
    await user.click(screen.getByRole("link", { name: "Скасувати" }));
    await waitFor(() => expect(location()).toBe("/vacancies?tab=dismissed&q=x"));
    expect(await screen.findByRole("tab", { name: "Сховані" })).toBeDefined();
    expect(backend.bodies).toEqual([]);
  });

  test("Скасувати без фільтрів веде на чистий список", async () => {
    const { user } = await openForm();
    await user.click(screen.getByRole("link", { name: "Скасувати" }));
    await waitFor(() => expect(location()).toBe("/vacancies"));
  });
});

describe("клавіатура й доступність", () => {
  test("порядок табуляції: текст, посилання, назва, компанія, «Додати», «Скасувати»", async () => {
    const { user } = await openForm();
    text().focus();
    const order: (HTMLElement | null)[] = [];
    for (let step = 0; step < 5; step += 1) {
      await user.tab();
      order.push(document.activeElement as HTMLElement | null);
    }
    expect(order).toEqual([url(), title(), company(), submit(), screen.getByRole("link", { name: "Скасувати" })]);
  });

  test("поки йде запит, кнопка вимкнена", async () => {
    const { user, backend } = await openForm();
    const gate = backend.hold();
    await user.type(text(), POSTING);
    await user.click(submit());
    expect(submit().hasAttribute("disabled")).toBe(true);
    await act(async () => gate.release());
    await waitFor(() => expect(location()).toBe("/vacancies/3"));
  });

  test("працює і на mobile: ті самі поля", async () => {
    setViewport("mobile");
    await openForm();
    expect(within(screen.getByRole("main")).getByLabelText("Текст опису")).toBeDefined();
  });
});

describe("делегування агенту", () => {
  const DESCRIPTION = "Агент попросить посилання чи текст вакансії, збереже її й запропонує аналіз";

  test("блок стоїть між заголовком і формою", async () => {
    const backend = jobsBackend([EXISTING]);
    connectPrompts(backend);
    connectAgents(backend, [CLAUDE]);
    renderClient("/vacancies/new", backend.fetchFn);
    await screen.findByRole("heading", { level: 1, name: "Додати вакансію" });

    const block = delegateBlocks()[0] as HTMLElement;
    expect(within(block).getByText(DESCRIPTION)).toBeDefined();
    expect(delegateBlocks()).toHaveLength(1);
    const heading = screen.getByRole("heading", { level: 1, name: "Додати вакансію" });
    const form = text().closest("form") as HTMLFormElement;
    expect(heading.compareDocumentPosition(block) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(block.compareDocumentPosition(form) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(form.contains(block)).toBe(false);
  });

  test("сервер не віддав промпт: «Не вдалося отримати текст запиту», нічого не скопійовано", async () => {
    const backend = jobsBackend([EXISTING]);
    connectPrompts(backend, "fail");
    connectAgents(backend, []);
    renderClient("/vacancies/new", backend.fetchFn);
    await screen.findByRole("heading", { level: 1, name: "Додати вакансію" });
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, "writeText");

    const block = within(await screen.findByRole("region", { name: "Делегувати агенту" }));
    await user.click(await block.findByRole("button", { name: "Копіювати промпт" }));

    expect(await block.findByText("Не вдалося отримати текст запиту. Спробуй ще раз.")).toBeDefined();
    expect(writeText).not.toHaveBeenCalled();
  });
});
