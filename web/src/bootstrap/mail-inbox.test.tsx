/** «Вхідні» пошти: список, пошук, вид, сторінки, порожні стани й помилки. */
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { apiDropped, apiMail, mailBackend, type MailBackend, type MailOverrides } from "./mailBackend";
import { json, renderClient } from "./testClient";
import { setViewport } from "./viewport";

async function openInbox(backend: MailBackend, path = "/profile/mail") {
  setViewport("desktop");
  renderClient(path, backend.fetchFn);
  await screen.findByRole("heading", { level: 1, name: "Пошта" });
}


async function rows() {
  return within(await screen.findByRole("list", { name: "Список листів" })).getAllByRole("listitem");
}

function many(count: number) {
  return Array.from({ length: count }, (_, index) => apiMail(index + 1, { received_at: `2026-10-24T${String(20 - (index % 10)).padStart(2, "0")}:00:00Z` }));
}

describe("список", () => {
  test("заголовок сторінки, вкладки й заголовок вкладки браузера", async () => {
    await openInbox(mailBackend([apiMail(1)]));

    expect(screen.getByText("Профіль / Пошта")).toBeDefined();
    expect(screen.getByRole("link", { name: "← Огляд профілю" }).getAttribute("href")).toBe("/profile");
    const tabs = screen.getByRole("tablist", { name: "Розділи пошти" });
    expect(within(tabs).getByRole("tab", { name: "Вхідні", selected: true })).toBeDefined();
    expect(within(tabs).getByRole("tab", { name: "Налаштування", selected: false })).toBeDefined();
    expect(document.title).toBe("Пошта · joboffer");
  });

  test("поки лист вантажиться — статус із скелетоном, потім рядки", async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const backend = mailBackend([apiMail(1)], { list: () => gate.then(() => json(200, { items: [apiMail(1)], page: { number: 1, size: 20, total: 1, first: 1, last: 1, has_newer: false, has_older: false } })) });
    await openInbox(backend);

    expect(screen.getByRole("status", { name: "Завантажуємо листи…" })).toBeDefined();
    release();
    expect(await rows()).toHaveLength(1);
    expect(screen.queryByRole("status", { name: "Завантажуємо листи…" })).toBeNull();
  });

  test("рядок: відправник, день і час за Мадридом, тема, вид", async () => {
    await openInbox(mailBackend([apiMail(1, { untrusted_subject: "Interview slot", received_at: "2026-07-01T10:05:00Z" })]));

    const [row] = await rows();
    const item = within(row as HTMLElement);
    expect(item.getByText("María López")).toBeDefined();
    expect(item.getByText("2026-07-01")).toBeDefined();
    expect(item.getByText("12:05")).toBeDefined();
    expect(item.getByText("Interview slot")).toBeDefined();
    expect(item.getByText("Компанія")).toBeDefined();
  });

  test("без імені відправника показується адреса", async () => {
    await openInbox(mailBackend([apiMail(1, { untrusted_from_name: "" })]));

    const [row] = await rows();
    expect(within(row as HTMLElement).getByText("talent@acme.example")).toBeDefined();
  });

  test("підсумок над списком і види листів у рядках", async () => {
    const backend = mailBackend([
      apiMail(1),
      apiMail(2, { category: "linkedin_alert", untrusted_subject: "Alert" }),
      apiMail(3, { category: "forwarding_confirmation", untrusted_subject: "Gmail" }),
    ]);
    await openInbox(backend);

    expect(await screen.findByText("Усі переслані листи · 3")).toBeDefined();
    const labels = (await rows()).map((row) => within(row).getByTestId("kind").textContent);
    expect(labels).toEqual(["Компанія", "LinkedIn: вакансії", "Підтвердження Gmail"]);
  });
});

describe("пошук, вид і розмір сторінки", () => {
  test("пошук за Enter: запит у списку й в адресі; «Скинути фільтри» повертає все", async () => {
    const user = userEvent.setup();
    const backend = mailBackend([apiMail(1, { untrusted_subject: "Acme call" }), apiMail(2, { untrusted_subject: "Other", untrusted_from_address: "x@other.example" })]);
    await openInbox(backend);
    await rows();

    await user.type(screen.getByRole("searchbox", { name: "Пошук" }), "acme{Enter}");

    expect(await screen.findByText("Усі переслані листи · 1")).toBeDefined();
    expect(backend.listUrls.at(-1)).toBe("/api/mail?q=acme");
    expect(screen.getByTestId("location").textContent).toBe("/profile/mail?q=acme");

    await user.click(screen.getByRole("button", { name: "Скинути фільтри" }));

    expect(await screen.findByText("Усі переслані листи · 2")).toBeDefined();
    expect(backend.listUrls.at(-1)).toBe("/api/mail");
    expect((screen.getByRole("searchbox", { name: "Пошук" }) as HTMLInputElement).value).toBe("");
    expect(screen.queryByRole("button", { name: "Скинути фільтри" })).toBeNull();
  });

  test("кнопка «Знайти» шукає так само", async () => {
    const user = userEvent.setup();
    const backend = mailBackend([apiMail(1)]);
    await openInbox(backend);
    await rows();

    await user.type(screen.getByRole("searchbox", { name: "Пошук" }), "  María  ");
    await user.click(screen.getByRole("button", { name: "Знайти" }));

    await screen.findByText("Усі переслані листи · 1");
    expect(backend.listUrls.at(-1)).toBe("/api/mail?q=Mar%C3%ADa");
  });

  test("вид листа: «Відхилені» залишає лише відхилені", async () => {
    const user = userEvent.setup();
    const backend = mailBackend([apiMail(1), apiDropped(2)]);
    await openInbox(backend);
    await rows();

    await user.selectOptions(screen.getByRole("combobox", { name: "Вид листа" }), "dropped");

    expect(await screen.findByText("Усі переслані листи · 1")).toBeDefined();
    expect(backend.listUrls.at(-1)).toBe("/api/mail?kind=dropped");
    expect(screen.getByTestId("location").textContent).toBe("/profile/mail?kind=dropped");
    expect((await rows()).map((row) => within(row).getByText(/Win a prize|Re:/).textContent)).toEqual(["Win a prize"]);
  });

  test("усі види фільтра названо по-людськи", async () => {
    await openInbox(mailBackend([apiMail(1)]));

    const options = within(screen.getByRole("combobox", { name: "Вид листа" })).getAllByRole("option");
    expect(options.map((option) => option.textContent)).toEqual([
      "Усі види",
      "Компанія",
      "LinkedIn: вакансії",
      "LinkedIn: повідомлення",
      "Підтвердження Gmail",
      "Інше",
      "Відхилені",
    ]);
  });

  test("розмір сторінки: 50 — у запиті, сторінка скидається на першу", async () => {
    const user = userEvent.setup();
    const backend = mailBackend(many(45));
    await openInbox(backend, "/profile/mail?page=2");
    await screen.findByText("21–40 з 45");

    await user.selectOptions(screen.getByRole("combobox", { name: "На сторінці" }), "50");

    expect(await screen.findByText("1–45 з 45")).toBeDefined();
    expect(backend.listUrls.at(-1)).toBe("/api/mail?per_page=50");
  });

  test("запит береться з адреси сторінки", async () => {
    const backend = mailBackend([apiMail(1, { untrusted_subject: "Acme call" })]);
    await openInbox(backend, "/profile/mail?q=acme&kind=company&per_page=100");

    await rows();
    expect(backend.listUrls).toEqual(["/api/mail?q=acme&kind=company&per_page=100"]);
    expect((screen.getByRole("searchbox", { name: "Пошук" }) as HTMLInputElement).value).toBe("acme");
    expect((screen.getByRole("combobox", { name: "Вид листа" }) as HTMLSelectElement).value).toBe("company");
    expect((screen.getByRole("combobox", { name: "На сторінці" }) as HTMLSelectElement).value).toBe("100");
  });
});

describe("сторінки", () => {
  test("діапазон і кнопки: на першій «Новіші» вимкнено", async () => {
    await openInbox(mailBackend(many(45)));

    expect(await screen.findByText("1–20 з 45")).toBeDefined();
    expect(screen.getByRole("button", { name: "Новіші листи" }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByRole("button", { name: "Старіші листи" }).hasAttribute("disabled")).toBe(false);
  });

  test("«Старіші» веде далі, на останній вимкнено «Старіші»", async () => {
    const user = userEvent.setup();
    const backend = mailBackend(many(45));
    await openInbox(backend);
    await screen.findByText("1–20 з 45");

    await user.click(screen.getByRole("button", { name: "Старіші листи" }));
    expect(await screen.findByText("21–40 з 45")).toBeDefined();
    expect(backend.listUrls.at(-1)).toBe("/api/mail?page=2");
    expect(screen.getByTestId("location").textContent).toBe("/profile/mail?page=2");

    await user.click(screen.getByRole("button", { name: "Старіші листи" }));
    expect(await screen.findByText("41–45 з 45")).toBeDefined();
    expect(screen.getByRole("button", { name: "Старіші листи" }).hasAttribute("disabled")).toBe(true);

    await user.click(screen.getByRole("button", { name: "Новіші листи" }));
    expect(await screen.findByText("21–40 з 45")).toBeDefined();
  });

  test("сторінка за межею списку: підказка й повернення на першу", async () => {
    const user = userEvent.setup();
    const backend = mailBackend(many(5));
    await openInbox(backend, "/profile/mail?page=9");

    expect(await screen.findByText("На цій сторінці листів нема")).toBeDefined();
    expect(screen.getByText("0 листів на цій сторінці з 5")).toBeDefined();

    await user.click(screen.getByRole("button", { name: "На першу сторінку" }));

    expect(await rows()).toHaveLength(5);
    expect(backend.listUrls.at(-1)).toBe("/api/mail");
  });

  test("один екран листів — без пагінації", async () => {
    await openInbox(mailBackend([apiMail(1)]));
    await rows();

    expect(screen.getByText("1–1 з 1")).toBeDefined();
    expect(screen.getByRole("button", { name: "Новіші листи" }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByRole("button", { name: "Старіші листи" }).hasAttribute("disabled")).toBe(true);
  });
});

describe("порожні стани й помилки", () => {
  test("листів ще нема: підказка й перехід до налаштувань", async () => {
    const user = userEvent.setup();
    await openInbox(mailBackend([]));

    expect(await screen.findByRole("heading", { level: 2, name: "Листів поки немає" })).toBeDefined();
    expect(screen.getByText("Налаштуй пересилання, потім синхронізуй скриньку.")).toBeDefined();
    expect(screen.queryByRole("list", { name: "Список листів" })).toBeNull();

    await user.click(screen.getByRole("button", { name: "Налаштувати пересилання" }));

    expect(screen.getByTestId("location").textContent).toBe("/profile/mail?tab=settings");
    expect(await screen.findByRole("tab", { name: "Налаштування", selected: true })).toBeDefined();
  });

  test("фільтр нічого не знайшов: «Немає збігів» і скидання", async () => {
    const user = userEvent.setup();
    const backend = mailBackend([apiMail(1)]);
    await openInbox(backend, "/profile/mail?q=nothing");

    expect(await screen.findByRole("heading", { level: 2, name: "Немає збігів" })).toBeDefined();
    expect(screen.getByText("Спробуй інший запит або скинь фільтри.")).toBeDefined();

    await user.click(within(screen.getByTestId("empty")).getByRole("button", { name: "Скинути фільтри" }));

    expect(await rows()).toHaveLength(1);
  });

  test("збій списку: повідомлення й «Спробувати ще раз»", async () => {
    const user = userEvent.setup();
    let fail = true;
    const overrides: MailOverrides = { list: () => (fail ? json(500, {}) : undefined) };
    const backend = mailBackend([apiMail(1)], overrides);
    await openInbox(backend);

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("Не вдалося завантажити листи.")).toBeDefined();
    fail = false;
    await user.click(within(alert).getByRole("button", { name: "Спробувати ще раз" }));

    expect(await rows()).toHaveLength(1);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  test("пошту не налаштовано: пояснення без повтору", async () => {
    await openInbox(mailBackend([], { list: () => json(503, { code: "mail_not_configured" }) }));

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("Пошту не налаштовано: на сервері нема адреси скриньки застосунку.")).toBeDefined();
    expect(within(alert).queryByRole("button")).toBeNull();
  });

  test("сесія завершилась: просимо увійти знову", async () => {
    await openInbox(mailBackend([], { list: () => json(401, {}) }));

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("Сесія завершилась. Увійди знову, щоб побачити листи.")).toBeDefined();
    expect(within(alert).queryByRole("button")).toBeNull();
  });

  test("відповідь на застарілий запит не затирає свіжішу", async () => {
    const user = userEvent.setup();
    let releaseStale: () => void = () => {};
    const stale = new Promise<Response>((resolve) => {
      releaseStale = () =>
        resolve(json(200, { items: [apiMail(9, { untrusted_subject: "Stale" })], page: { number: 1, size: 20, total: 1, first: 1, last: 1, has_newer: false, has_older: false } }));
    });
    const backend = mailBackend([apiMail(1, { untrusted_subject: "Fresh" })], {
      list: (url) => (url.searchParams.get("q") === null ? stale : undefined),
    });
    await openInbox(backend);

    await user.type(screen.getByRole("searchbox", { name: "Пошук" }), "fresh{Enter}");
    expect(await screen.findByText("Fresh")).toBeDefined();
    releaseStale();
    await new Promise((resolve) => setTimeout(resolve, 20));

    expect(screen.queryByText("Stale")).toBeNull();
    expect(screen.getByText("Fresh")).toBeDefined();
  });

  test("порожня тема й відсутній відправник мають позначки", async () => {
    await openInbox(mailBackend([apiMail(1, { untrusted_subject: "", untrusted_from_name: "", untrusted_from_address: "" })]));

    const [row] = await rows();
    expect(within(row as HTMLElement).getByText("(без відправника)")).toBeDefined();
    expect(within(row as HTMLElement).getByText("(без теми)")).toBeDefined();
  });
});
