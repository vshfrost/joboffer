/** Форма «Я подався» і «Змінити дані»: валідація за API, чернетка, подвійний submit, вихід із незбереженою формою. */
import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { apiApplication, apiJob, jobsBackend, type ApiApplication } from "./jobsBackend";
import { renderClient } from "./testClient";

const JOB = apiJob(1, { title: "Senior Backend Engineer", company: "Northstar Labs" });
const OTHER = apiJob(2, { title: "Rust Developer", company: "Cedar Ledger" });
const TODAY = new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Madrid" }).format(new Date());

async function openDetails(application: ApiApplication | null = null) {
  const backend = jobsBackend([JOB, OTHER], [], [], application === null ? [] : [application]);
  renderClient("/vacancies/1", backend.fetchFn);
  await screen.findByRole("heading", { level: 1, name: "Senior Backend Engineer" });
  return { backend, user: userEvent.setup() };
}

async function openForm() {
  const opened = await openDetails();
  await opened.user.click(await screen.findByRole("button", { name: "Я подався" }));
  return opened;
}

const form = () => within(screen.getByRole("form", { name: "Я подався" }));
const channel = () => form().getByRole("combobox", { name: "Канал" }) as HTMLSelectElement;
const date = () => form().getByLabelText("Дата подачі") as HTMLInputElement;
const ats = () => form().getByRole("combobox", { name: /ATS/ }) as HTMLSelectElement;
const submit = () => form().getByRole("button", { name: /^(Зберегти подачу|Зберігаємо…)$/ }) as HTMLButtonElement;
const saves = (backend: Awaited<ReturnType<typeof openDetails>>["backend"]) => backend.requests.filter((line) => line.startsWith("PUT /api/jobs/1/application"));

describe("відкриття форми", () => {
  test("канал без значення за замовчуванням, дата — сьогодні за Мадридом, ATS необов'язковий, фокус на каналі", async () => {
    await openForm();
    expect(channel().value).toBe("");
    expect(within(channel()).getAllByRole("option").map((option) => option.textContent)).toEqual(["Обери канал", "Email", "ATS або сайт компанії", "LinkedIn", "Рекомендація"]);
    expect(date().value).toBe(TODAY);
    expect(ats().value).toBe("");
    expect(within(ats()).getAllByRole("option").map((option) => option.textContent)).toEqual(["Не вказано", "Greenhouse", "Lever", "Ashby", "Workable", "SmartRecruiters", "Інша система"]);
    expect(document.activeElement).toBe(channel());
  });

  test("підпис пояснює, що форма лише фіксує вже виконану подачу", async () => {
    await openForm();
    expect(screen.getByText("Зафіксуйте вже виконану подачу. Ця форма не надсилає заявку роботодавцю.")).toBeDefined();
  });

  test("домени й адреси сховано за розкриттям; воно відкривається кнопкою", async () => {
    const { user } = await openForm();
    const toggle = form().getByRole("button", { name: "Домени й адреси email · необов’язково" });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(form().queryByRole("textbox", { name: "Домени" })).toBeNull();
    await user.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(form().getByRole("textbox", { name: "Домени" })).toBeDefined();
    expect(form().getByRole("textbox", { name: "Адреси email" })).toBeDefined();
  });

  test("«Скасувати» повертає до пропозиції без запиту", async () => {
    const { user, backend } = await openForm();
    await user.click(form().getByRole("button", { name: "Скасувати" }));
    expect(screen.getByRole("button", { name: "Я подався" })).toBeDefined();
    expect(screen.queryByRole("form", { name: "Я подався" })).toBeNull();
    expect(saves(backend)).toEqual([]);
  });
});

describe("збереження", () => {
  test("відправляє значення форми й показує подачу лише після відповіді сервера", async () => {
    const { user, backend } = await openForm();
    await user.selectOptions(channel(), "ats");
    fireEvent.change(date(), { target: { value: "2026-10-18" } });
    await user.selectOptions(ats(), "lever");
    await user.click(form().getByRole("button", { name: "Домени й адреси email · необов’язково" }));
    await user.type(form().getByRole("textbox", { name: "Домени" }), "northstar.example{Enter}jobs.northstar.example");
    await user.type(form().getByRole("textbox", { name: "Адреси email" }), "careers@northstar.example");
    const hold = backend.holdApplication();
    await user.click(submit());
    // Відповіді нема: форма ще на місці, подачі в блоці нема.
    expect(screen.getByRole("form", { name: "Я подався" })).toBeDefined();
    expect(submit().disabled).toBe(true);
    expect(submit().textContent).toBe("Зберігаємо…");
    expect(backend.bodies.at(-1)).toEqual({
      channel: "ats",
      applied_on: "2026-10-18",
      ats: "lever",
      company_domains: ["northstar.example", "jobs.northstar.example"],
      company_emails: ["careers@northstar.example"],
    });
    hold.release();
    const panel = within(await screen.findByRole("region", { name: "Подача" }));
    expect(await panel.findByText("Подано", { selector: "span" })).toBeDefined();
    expect(panel.getByText(/Подано 2026-10-18 · Lever/)).toBeDefined();
    expect(screen.queryByRole("form", { name: "Я подався" })).toBeNull();
    expect(screen.getByRole("status", { name: "Результат подачі" }).textContent).toContain("Подачу збережено. Заявку роботодавцю не надсилали.");
  });

  test("порожні необов'язкові поля йдуть порожніми, а фокус після збереження — на заголовку блоку", async () => {
    const { user, backend } = await openForm();
    await user.selectOptions(channel(), "email");
    await user.click(submit());
    await screen.findByText("Подано", { selector: "span" });
    expect(backend.bodies.at(-1)).toEqual({ channel: "email", applied_on: TODAY, ats: "", company_domains: [], company_emails: [] });
    expect(document.activeElement).toBe(screen.getByRole("heading", { level: 2, name: "Подача" }));
  });

  test("подвійне натискання — один запит", async () => {
    const { user, backend } = await openForm();
    await user.selectOptions(channel(), "email");
    const hold = backend.holdApplication();
    await user.dblClick(submit());
    hold.release();
    await screen.findByText("Подано", { selector: "span" });
    expect(saves(backend)).toHaveLength(1);
  });

  test("два submit в одній подачі подій — один запит", async () => {
    const { user, backend } = await openForm();
    await user.selectOptions(channel(), "email");
    const element = screen.getByRole("form", { name: "Я подався" }) as HTMLFormElement;
    act(() => {
      element.requestSubmit();
      element.requestSubmit();
    });
    await screen.findByText("Подано", { selector: "span" });
    expect(saves(backend)).toHaveLength(1);
  });

  test("Enter у полі дати теж відправляє форму один раз", async () => {
    const { user, backend } = await openForm();
    await user.selectOptions(channel(), "linkedin");
    date().focus();
    await user.keyboard("{Enter}");
    await screen.findByText("Подано", { selector: "span" });
    expect(saves(backend)).toHaveLength(1);
  });
});

describe("помилки сервера", () => {
  test("422 показує тексти біля своїх полів і не стирає введене", async () => {
    const { user, backend } = await openForm();
    await user.selectOptions(channel(), "email");
    fireEvent.change(date(), { target: { value: "2999-01-01" } });
    await user.click(form().getByRole("button", { name: "Домени й адреси email · необов’язково" }));
    await user.type(form().getByRole("textbox", { name: "Домени" }), "not a domain");
    await user.type(form().getByRole("textbox", { name: "Адреси email" }), "jane");
    await user.click(submit());
    expect(await form().findByText("Дата подачі не може бути в майбутньому.")).toBeDefined();
    expect(form().getByText("Некоректний домен компанії: not a domain.")).toBeDefined();
    expect(form().getByText("Некоректна адреса компанії: jane.")).toBeDefined();
    expect(date().getAttribute("aria-invalid")).toBe("true");
    expect(date().getAttribute("aria-describedby")).not.toBeNull();
    // Введене лишилось, кнопка знову активна.
    expect(date().value).toBe("2999-01-01");
    expect((form().getByRole("textbox", { name: "Домени" }) as HTMLTextAreaElement).value).toBe("not a domain");
    expect(submit().disabled).toBe(false);
    expect(screen.queryByText("Подано", { selector: "span" })).toBeNull();
    // Виправлення й повторне збереження.
    fireEvent.change(date(), { target: { value: "2026-10-18" } });
    await user.clear(form().getByRole("textbox", { name: "Домени" }));
    await user.type(form().getByRole("textbox", { name: "Домени" }), "acme.example");
    await user.clear(form().getByRole("textbox", { name: "Адреси email" }));
    await user.type(form().getByRole("textbox", { name: "Адреси email" }), "jane@acme.example");
    await user.click(submit());
    await screen.findByText("Подано", { selector: "span" });
    expect(saves(backend)).toHaveLength(2);
  });

  test("помилка в полі, що сховане під розкриттям, розкриває його", async () => {
    const { user } = await openForm();
    await user.selectOptions(channel(), "email");
    await user.click(form().getByRole("button", { name: "Домени й адреси email · необов’язково" }));
    await user.type(form().getByRole("textbox", { name: "Адреси email" }), "jane");
    await user.click(form().getByRole("button", { name: "Домени й адреси email · необов’язково" }));
    expect(form().queryByRole("textbox", { name: "Адреси email" })).toBeNull();
    await user.click(submit());
    expect(await form().findByText("Некоректна адреса компанії: jane.")).toBeDefined();
    expect((form().getByRole("textbox", { name: "Адреси email" }) as HTMLTextAreaElement).value).toBe("jane");
  });

  test("канал не обрано — сервер повертає 422 біля каналу", async () => {
    const { user } = await openForm();
    await user.click(submit());
    expect(await form().findByText("Канал — один з: email, ats, linkedin, referral.")).toBeDefined();
    expect(channel().getAttribute("aria-invalid")).toBe("true");
  });

  test("збій сервера: загальне повідомлення, форма й введене на місці, повтор спрацьовує", async () => {
    const { user, backend } = await openForm();
    backend.failures.saveApplication = 1;
    await user.selectOptions(channel(), "referral");
    await user.click(submit());
    expect((await form().findByRole("alert")).textContent).toContain("Не вдалося зберегти подачу. Введене збережено — спробуй ще раз.");
    expect(channel().value).toBe("referral");
    expect(submit().disabled).toBe(false);
    await user.click(submit());
    await screen.findByText("Подано", { selector: "span" });
    expect(saves(backend)).toHaveLength(2);
  });

  test("422 з полем, якого нема у формі, — загальне повідомлення; введене лишається", async () => {
    const backend = jobsBackend([JOB]);
    const fetchFn: typeof fetch = (input, init) =>
      init?.method === "PUT"
        ? Promise.resolve(
            new Response(JSON.stringify({ code: "invalid_request", message: "Запит не пройшов перевірку", field_errors: [{ field: "request", message: "Запит не пройшов перевірку" }] }), {
              status: 422,
              headers: { "Content-Type": "application/json" },
            }),
          )
        : backend.fetchFn(input, init);
    renderClient("/vacancies/1", fetchFn);
    const user = userEvent.setup();
    await screen.findByRole("heading", { level: 1, name: "Senior Backend Engineer" });
    await user.click(await screen.findByRole("button", { name: "Я подався" }));
    await user.selectOptions(channel(), "email");
    await user.click(submit());
    expect((await form().findByRole("alert")).textContent).toBe("Запит не пройшов перевірку");
    expect(channel().value).toBe("email");
  });

  test("вакансію видалено: повідомлення, що вона недоступна", async () => {
    const { user, backend } = await openForm();
    backend.jobs = [];
    await user.selectOptions(channel(), "email");
    await user.click(submit());
    expect((await form().findByRole("alert")).textContent).toContain("Вакансію не знайдено.");
  });
});

describe("зміна даних", () => {
  const SAVED = apiApplication(1, { status: "interview", channel: "email", applied_on: "2026-10-18", ats: "lever", company_domains: ["acme.example"], company_emails: ["hr@acme.example"] });

  async function openEdit() {
    const opened = await openDetails(SAVED);
    const panel = within(await screen.findByRole("region", { name: "Подача" }));
    await opened.user.click(await panel.findByRole("button", { name: "Усі дані подачі" }));
    await opened.user.click(panel.getByRole("button", { name: "Змінити дані" }));
    return { ...opened, panel };
  }

  test("форма заповнена збереженим, розкриття доменів уже відкрите", async () => {
    await openEdit();
    expect(screen.getByRole("form", { name: "Змінити дані подачі" })).toBeDefined();
    const edit = within(screen.getByRole("form", { name: "Змінити дані подачі" }));
    expect((edit.getByRole("combobox", { name: "Канал" }) as HTMLSelectElement).value).toBe("email");
    expect((edit.getByLabelText("Дата подачі") as HTMLInputElement).value).toBe("2026-10-18");
    expect((edit.getByRole("combobox", { name: /ATS/ }) as HTMLSelectElement).value).toBe("lever");
    expect((edit.getByRole("textbox", { name: "Домени" }) as HTMLTextAreaElement).value).toBe("acme.example");
    expect((edit.getByRole("textbox", { name: "Адреси email" }) as HTMLTextAreaElement).value).toBe("hr@acme.example");
  });

  test("збереження міняє дані, статус лишається", async () => {
    const { user, backend } = await openEdit();
    const edit = within(screen.getByRole("form", { name: "Змінити дані подачі" }));
    await user.selectOptions(edit.getByRole("combobox", { name: "Канал" }), "referral");
    await user.click(edit.getByRole("button", { name: "Зберегти подачу" }));
    const panel = within(await screen.findByRole("region", { name: "Подача" }));
    await waitFor(() => expect(screen.queryByRole("form", { name: "Змінити дані подачі" })).toBeNull());
    expect(panel.getByText("Співбесіда", { selector: "span" })).toBeDefined();
    expect(panel.getByText("Рекомендація")).toBeDefined();
    expect(backend.bodies.at(-1)).toMatchObject({ channel: "referral", ats: "lever", company_domains: ["acme.example"] });
  });

  test("«Скасувати» повертає збережене без запиту", async () => {
    const { user, backend } = await openEdit();
    const edit = within(screen.getByRole("form", { name: "Змінити дані подачі" }));
    await user.selectOptions(edit.getByRole("combobox", { name: "Канал" }), "referral");
    await user.click(edit.getByRole("button", { name: "Скасувати" }));
    expect(screen.queryByRole("form", { name: "Змінити дані подачі" })).toBeNull();
    expect(saves(backend)).toEqual([]);
    expect(screen.getByText("Співбесіда", { selector: "span" })).toBeDefined();
  });
});

describe("вихід із незбереженою формою", () => {
  test("перехід за посиланням питає підтвердження; «Залишитись» лишає форму з введеним", async () => {
    const { user } = await openForm();
    await user.selectOptions(channel(), "ats");
    await user.click(screen.getByRole("link", { name: "Усі вакансії" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByText("Є незбережені зміни")).toBeDefined();
    await user.click(within(dialog).getByRole("button", { name: "Залишитись" }));
    expect(screen.getByTestId("location").textContent).toBe("/vacancies/1");
    expect(channel().value).toBe("ats");
  });

  test("«Піти без збереження» переходить і не зберігає подачу", async () => {
    const { user, backend } = await openForm();
    await user.selectOptions(channel(), "ats");
    await user.click(screen.getByRole("link", { name: "Усі вакансії" }));
    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Піти без збереження" }));
    await waitFor(() => expect(screen.getByTestId("location").textContent).toBe("/vacancies"));
    expect(saves(backend)).toEqual([]);
  });

  test("Escape на сторінці з відкритою формою не виходить зі сторінки без підтвердження", async () => {
    const { user } = await openForm();
    await user.selectOptions(channel(), "ats");
    await user.keyboard("{Escape}");
    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByText("Є незбережені зміни")).toBeDefined();
  });

  test("порожня незмінена форма не блокує вихід", async () => {
    const { user } = await openForm();
    await user.click(screen.getByRole("link", { name: "Усі вакансії" }));
    await waitFor(() => expect(screen.getByTestId("location").textContent).toBe("/vacancies"));
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  test("закриття вкладки із зміненою формою попереджає (beforeunload)", async () => {
    const { user } = await openForm();
    const clean = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(clean);
    expect(clean.defaultPrevented).toBe(false);
    await user.selectOptions(channel(), "ats");
    const dirty = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(dirty);
    expect(dirty.defaultPrevented).toBe(true);
  });

  test("після збереження вихід вільний", async () => {
    const { user } = await openForm();
    await user.selectOptions(channel(), "ats");
    await user.click(submit());
    await screen.findByText("Подано", { selector: "span" });
    await user.click(screen.getByRole("link", { name: "Усі вакансії" }));
    await waitFor(() => expect(screen.getByTestId("location").textContent).toBe("/vacancies"));
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });
});
