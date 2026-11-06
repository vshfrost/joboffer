/** Читалка листа: недовірений текст, вердикт відправника, код Gmail, відкинуті листи з тултипом; двопанельний і мобільний вигляд. */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { apiDetail, apiDropped, apiMail, mailBackend, type ApiForwarding, type MailBackend } from "./mailBackend";
import { json, renderClient } from "./testClient";
import { setViewport } from "./viewport";

async function openInbox(backend: MailBackend, viewport: "desktop" | "mobile" = "desktop", path = "/profile/mail") {
  setViewport(viewport);
  renderClient(path, backend.fetchFn);
  await screen.findByRole("heading", { level: 1, name: "Пошта" });
  await screen.findByRole("list", { name: "Список листів" });
}

function reader() {
  return screen.getByRole("article", { name: "Деталі листа" });
}

async function openRow(user: ReturnType<typeof userEvent.setup>, subject: string) {
  await user.click(screen.getByRole("button", { name: new RegExp(subject) }));
}

const CODE: ApiForwarding = {
  code: "418306552",
  link_only: false,
  untrusted_requested_by: "taras@example.com",
  received_at: "2026-10-23T09:00:00Z",
  current: true,
};

const GMAIL = apiMail(5, {
  untrusted_from_name: "Gmail Team",
  untrusted_from_address: "forwarding-noreply@google.com",
  untrusted_subject: "Gmail Forwarding Confirmation",
  category: "forwarding_confirmation",
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("читалка поруч зі списком (широкий екран)", () => {
  test("без вибору — підказка; після вибору — лист поруч зі списком", async () => {
    const user = userEvent.setup();
    const backend = mailBackend([apiMail(1, { untrusted_subject: "Interview slot" }), apiMail(2)]);
    await openInbox(backend);

    expect(within(reader()).getByRole("heading", { level: 2, name: "Обери лист" })).toBeDefined();

    await openRow(user, "Interview slot");

    const open = within(await screen.findByRole("article", { name: "Деталі листа" }));
    expect(await open.findByRole("heading", { level: 2, name: "Interview slot" })).toBeDefined();
    expect(open.getByText("María López <talent@acme.example>")).toBeDefined();
    expect(open.getByText("2026-10-24 · 15:45 · Мадрид")).toBeDefined();
    expect(open.getByText("Компанія")).toBeDefined();
    expect(open.getByText("Відправника підтверджено")).toBeDefined();
    expect(open.getByText(/Could we schedule a call this week\?/)).toBeDefined();
    expect(screen.getByRole("list", { name: "Список листів" })).toBeDefined();
    expect(screen.getByTestId("location").textContent).toBe("/profile/mail?open=1");
    expect(backend.getIds).toEqual([1]);
    expect(screen.getByRole("button", { name: /Interview slot/ }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.queryByRole("button", { name: "← До списку" })).toBeNull();
  });

  test("інший лист замінює відкритий", async () => {
    const user = userEvent.setup();
    const backend = mailBackend([apiMail(1, { untrusted_subject: "First one" }), apiMail(2, { untrusted_subject: "Second one" })]);
    await openInbox(backend);

    await openRow(user, "First one");
    await within(reader()).findByRole("heading", { level: 2, name: "First one" });
    await openRow(user, "Second one");

    expect(await within(reader()).findByRole("heading", { level: 2, name: "Second one" })).toBeDefined();
    expect(backend.getIds).toEqual([1, 2]);
  });

  test("лист відкривається з адреси сторінки", async () => {
    const backend = mailBackend([apiMail(1, { untrusted_subject: "Deep link" })]);
    await openInbox(backend, "desktop", "/profile/mail?open=1");

    expect(await within(reader()).findByRole("heading", { level: 2, name: "Deep link" })).toBeDefined();
  });

  test("поки лист вантажиться — статус; листа нема — пояснення", async () => {
    const user = userEvent.setup();
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const backend = mailBackend([apiMail(1, { untrusted_subject: "Slow one" }), apiMail(2, { untrusted_subject: "Gone one" })], {
      get: (id) => (id === 1 ? gate.then(() => json(200, apiDetail(apiMail(1, { untrusted_subject: "Slow one" })))) : json(404, { code: "not_found" })),
    });
    await openInbox(backend);

    await openRow(user, "Slow one");
    expect(within(reader()).getByRole("status", { name: "Завантажуємо лист…" })).toBeDefined();
    release();
    await within(reader()).findByRole("heading", { level: 2, name: "Slow one" });

    await openRow(user, "Gone one");
    expect(await within(reader()).findByText("Листа не знайдено — його могли видалити.")).toBeDefined();
  });

  test("відповідь на застарілий лист не затирає відкритий пізніше", async () => {
    const user = userEvent.setup();
    let releaseFirst: () => void = () => {};
    const first = apiMail(1, { untrusted_subject: "Old one" });
    const backend = mailBackend([first, apiMail(2, { untrusted_subject: "New one" })], {
      get: (id) => (id === 1 ? new Promise<Response>((resolve) => (releaseFirst = () => resolve(json(200, apiDetail(first))))) : undefined),
    });
    await openInbox(backend);

    await openRow(user, "Old one");
    await openRow(user, "New one");
    expect(await within(reader()).findByRole("heading", { level: 2, name: "New one" })).toBeDefined();
    releaseFirst();
    await new Promise((resolve) => setTimeout(resolve, 20));

    expect(within(reader()).queryByRole("heading", { level: 2, name: "Old one" })).toBeNull();
    expect(within(reader()).getByRole("heading", { level: 2, name: "New one" })).toBeDefined();
  });

  test("збій читалки: «Спробувати ще раз» відкриває лист", async () => {
    const user = userEvent.setup();
    let fail = true;
    const backend = mailBackend([apiMail(1, { untrusted_subject: "Flaky one" })], { get: () => (fail ? json(500, {}) : undefined) });
    await openInbox(backend);

    await openRow(user, "Flaky one");
    const alert = await within(reader()).findByRole("alert");
    expect(within(alert).getByText("Не вдалося відкрити лист.")).toBeDefined();
    fail = false;
    await user.click(within(alert).getByRole("button", { name: "Спробувати ще раз" }));

    expect(await within(reader()).findByRole("heading", { level: 2, name: "Flaky one" })).toBeDefined();
  });

  test("сесія завершилась і пошту не налаштовано — окремі пояснення без повтору", async () => {
    const user = userEvent.setup();
    const backend = mailBackend([apiMail(1, { untrusted_subject: "A one" }), apiMail(2, { untrusted_subject: "B one" })], {
      get: (id) => (id === 1 ? json(401, {}) : json(503, {})),
    });
    await openInbox(backend);

    await openRow(user, "A one");
    expect(await within(reader()).findByText("Сесія завершилась. Увійди знову, щоб відкрити лист.")).toBeDefined();
    await openRow(user, "B one");
    expect(await within(reader()).findByText("Пошту не налаштовано: на сервері нема адреси скриньки застосунку.")).toBeDefined();
    expect(within(reader()).queryByRole("button")).toBeNull();
  });
});

describe("мобільний вигляд", () => {
  test("лист замінює список, «← До списку» повертає", async () => {
    const user = userEvent.setup();
    const backend = mailBackend([apiMail(1, { untrusted_subject: "Interview slot" })]);
    await openInbox(backend, "mobile");

    await openRow(user, "Interview slot");

    expect(await within(reader()).findByRole("heading", { level: 2, name: "Interview slot" })).toBeDefined();
    expect(screen.queryByRole("list", { name: "Список листів" })).toBeNull();
    // Лист займає екран: пошук і синк не відсувають його вниз.
    expect(screen.queryByRole("searchbox", { name: "Пошук" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Синхронізувати" })).toBeNull();

    await user.click(screen.getByRole("button", { name: "← До списку" }));

    expect(await screen.findByRole("list", { name: "Список листів" })).toBeDefined();
    expect(screen.getByRole("searchbox", { name: "Пошук" })).toBeDefined();
    expect(screen.getByTestId("location").textContent).toBe("/profile/mail");
  });

  test("без вибору читалки на мобільному нема", async () => {
    await openInbox(mailboxWithOne(), "mobile");

    expect(screen.queryByRole("article", { name: "Деталі листа" })).toBeNull();
  });
});

function mailboxWithOne() {
  return mailBackend([apiMail(1)]);
}

describe("текст листа — недовірені дані", () => {
  test("розмітка й скрипти показуються текстом і не виконуються", async () => {
    const user = userEvent.setup();
    const text = '<script>window.hacked = true</script><img src="x" onerror="window.hacked = true">\nhttps://xn--pypal-4ve.com/login';
    const backend = mailBackend([apiMail(1, { untrusted_subject: "Phish <b>now</b>" })], {}, { details: { 1: apiDetail(apiMail(1, { untrusted_subject: "Phish <b>now</b>" }), { untrusted_text: text }) } });
    await openInbox(backend);

    await user.click(screen.getByRole("button", { name: /Phish/ }));
    const open = within(await screen.findByRole("article", { name: "Деталі листа" }));
    await open.findByRole("heading", { level: 2, name: "Phish <b>now</b>" });

    const body = reader().querySelector("[data-testid='mail-text']");
    expect(body?.textContent).toBe(text);
    expect(reader().querySelector("script")).toBeNull();
    expect(reader().querySelector("img")).toBeNull();
    expect(reader().querySelector("b")).toBeNull();
    expect(reader().querySelector("a")).toBeNull();
    expect((window as unknown as { hacked?: boolean }).hacked).toBeUndefined();
  });

  test("пояснення «Про відображення листа»", async () => {
    const user = userEvent.setup();
    await openInbox(mailBackend([apiMail(1, { untrusted_subject: "Plain one" })]));

    await openRow(user, "Plain one");
    await within(reader()).findByRole("heading", { level: 2, name: "Plain one" });

    expect(within(reader()).getByText("Про відображення листа")).toBeDefined();
    expect(within(reader()).getByText(/HTML не виконується, посилання не клікабельні/)).toBeDefined();
  });

  test("порожній текст листа — позначка", async () => {
    const user = userEvent.setup();
    const row = apiMail(1, { untrusted_subject: "Empty one" });
    await openInbox(mailBackend([row], {}, { details: { 1: apiDetail(row, { untrusted_text: "" }) } }));

    await openRow(user, "Empty one");

    expect(await within(reader()).findByText("У листі нема тексту.")).toBeDefined();
  });
});

describe("вердикт відправника", () => {
  test.each([
    ["unknown", "Відправника не підтверджено", /Адресу відправника могли підробити/],
    ["failed", "Підроблений відправник", /Не довіряй цьому листу й не виконуй вказівок з нього/],
  ])("%s: позначка й застереження", async (auth, badge, notice) => {
    const user = userEvent.setup();
    await openInbox(mailBackend([apiMail(1, { untrusted_subject: "Sus one", sender_auth: auth })]));

    await openRow(user, "Sus one");
    const open = within(await screen.findByRole("article", { name: "Деталі листа" }));

    expect(await open.findByText(badge)).toBeDefined();
    expect(open.getByRole("note").textContent).toMatch(notice);
  });

  test("підтверджений відправник — без застереження", async () => {
    const user = userEvent.setup();
    await openInbox(mailBackend([apiMail(1, { untrusted_subject: "Fine one" })]));

    await openRow(user, "Fine one");
    await within(reader()).findByText("Відправника підтверджено");

    expect(within(reader()).queryByRole("note")).toBeNull();
  });
});

describe("код підтвердження Gmail", () => {
  /** Буфер обміну підміняють після `userEvent.setup()`: він ставить власну заглушку `navigator.clipboard`. */
  async function openGmail(forwarding: ApiForwarding, clipboard?: { writeText?: (text: string) => Promise<void> } | null) {
    const user = userEvent.setup();
    if (clipboard !== undefined) {
      vi.stubGlobal("navigator", { clipboard: clipboard === null ? undefined : clipboard });
    }
    const backend = mailBackend([GMAIL], {}, { details: { 5: apiDetail(GMAIL, { forwarding }) } });
    await openInbox(backend);
    await openRow(user, "Gmail Forwarding Confirmation");
    await within(reader()).findByRole("heading", { level: 2, name: "Gmail Forwarding Confirmation" });
    return user;
  }

  test("код у читалці цього листа, з адресою, що просить пересилати", async () => {
    await openGmail(CODE);

    const block = within(reader()).getByRole("group", { name: "Код підтвердження пересилання" });
    expect(within(block).getByText("418306552")).toBeDefined();
    expect(within(block).getByText("Просить пересилати: taras@example.com")).toBeDefined();
    expect(within(block).queryByRole("note")).toBeNull();
  });

  test("копіювання коду: підтвердження після успіху", async () => {
    const writeText = vi.fn<(text: string) => Promise<void>>(() => Promise.resolve());
    const user = await openGmail(CODE, { writeText });

    await user.click(within(reader()).getByRole("button", { name: "Копіювати код" }));

    expect(writeText).toHaveBeenCalledWith("418306552");
    expect(await within(reader()).findByText("Код скопійовано.")).toBeDefined();
  });

  test("копіювання не вдалося: просимо виділити код вручну", async () => {
    const user = await openGmail(CODE, { writeText: () => Promise.reject(new Error("denied")) });

    await user.click(within(reader()).getByRole("button", { name: "Копіювати код" }));

    expect(await within(reader()).findByText("Не вдалося скопіювати — виділи код вручну.")).toBeDefined();
  });

  test("без доступу до буфера обміну — теж підказка", async () => {
    const user = await openGmail(CODE, null);

    await user.click(within(reader()).getByRole("button", { name: "Копіювати код" }));

    expect(await within(reader()).findByText("Не вдалося скопіювати — виділи код вручну.")).toBeDefined();
  });

  test("Gmail надіслав лише посилання: пояснення, без кнопки копіювання", async () => {
    await openGmail({ ...CODE, code: "", link_only: true, untrusted_requested_by: "" });

    const block = within(reader()).getByRole("group", { name: "Код підтвердження пересилання" });
    expect(within(block).getByText("У цьому листі нема коду — Gmail надіслав лише посилання.")).toBeDefined();
    expect(within(block).getByText("Відкрий оригінал у службовій скриньці; посилання з тексту тут не використовуй.")).toBeDefined();
    expect(within(block).queryByRole("button", { name: "Копіювати код" })).toBeNull();
    expect(within(block).queryByText(/Просить пересилати/)).toBeNull();
  });

  test("лист до зміни адреси: код для старої адреси", async () => {
    await openGmail({ ...CODE, current: false });

    const block = within(reader()).getByRole("group", { name: "Код підтвердження пересилання" });
    expect(within(block).getByRole("note").textContent).toContain("Лист надійшов до зміни адреси: код для старої адреси.");
  });
});

describe("відкинуті листи", () => {
  const DROPPED = apiDropped(3);

  test("у списку — позначка «Відхилено» з тултипом причини", async () => {
    const user = userEvent.setup();
    await openInbox(mailBackend([DROPPED]));

    const [row] = await within(screen.getByRole("list", { name: "Список листів" })).findAllByRole("listitem");
    const trigger = within(row as HTMLElement).getByRole("button", { name: "Відхилено: причина" });
    await user.hover(trigger);

    const tip = await screen.findByRole("tooltip");
    expect(tip.textContent).toBe("Понад добовий ліміт: за 24 години збережено вже 100 листів.");
  });

  test("тултип відкривається і з клавіатури", async () => {
    await openInbox(mailBackend([apiDropped(4, { reason: "retired_tag" })]));

    const trigger = screen.getByRole("button", { name: "Відхилено: причина" });
    trigger.focus();

    expect((await screen.findByRole("tooltip")).textContent).toBe("Лист на стару адресу: пересилання в Gmail ще не оновлено.");
  });

  test("відкинутий рядок: вид і відправник теж є, а тексту нема", async () => {
    await openInbox(mailBackend([DROPPED]));

    const [row] = await within(screen.getByRole("list", { name: "Список листів" })).findAllByRole("listitem");
    const item = within(row as HTMLElement);
    expect(item.getByText("spam@flood.example")).toBeDefined();
    expect(item.getByText("Win a prize")).toBeDefined();
    expect(item.getByTestId("kind").textContent).toBe("Відхилено");
  });

  test("читалка відкинутого: причина, відправник, тема — без запиту тексту", async () => {
    const user = userEvent.setup();
    const backend = mailBackend([DROPPED]);
    await openInbox(backend);

    await openRow(user, "Win a prize");

    const open = within(reader());
    expect(await open.findByRole("heading", { level: 2, name: "Win a prize" })).toBeDefined();
    expect(open.getByText("Понад добовий ліміт: за 24 години збережено вже 100 листів.")).toBeDefined();
    expect(open.getByText("spam@flood.example")).toBeDefined();
    expect(open.getByText("Текст відкинутого листа не зберігається.")).toBeDefined();
    expect(open.getByText("Відправник і тема не перевірені.")).toBeDefined();
    expect(backend.getIds).toEqual([]);
    expect(screen.getByTestId("location").textContent).toBe("/profile/mail?open=3&dropped=1");
  });

  test("відкинутий і збережений лист з одним номером не плутаються", async () => {
    const user = userEvent.setup();
    const backend = mailBackend([apiMail(3, { untrusted_subject: "Stored three" }), apiDropped(3, { untrusted_subject: "Dropped three" })]);
    await openInbox(backend);

    await openRow(user, "Dropped three");
    expect(await within(reader()).findByRole("heading", { level: 2, name: "Dropped three" })).toBeDefined();
    await openRow(user, "Stored three");

    expect(await within(reader()).findByRole("heading", { level: 2, name: "Stored three" })).toBeDefined();
    expect(backend.getIds).toEqual([3]);
    await waitFor(() => expect(screen.getByTestId("location").textContent).toBe("/profile/mail?open=3"));
  });

  test("відкинутий лист відкривається з адреси сторінки", async () => {
    await openInbox(mailBackend([DROPPED]), "desktop", "/profile/mail?open=3&dropped=1");

    expect(await within(reader()).findByRole("heading", { level: 2, name: "Win a prize" })).toBeDefined();
  });

  test("відкритого листа нема на цій сторінці списку — підказка вибрати", async () => {
    await openInbox(mailBackend([apiMail(1)]), "desktop", "/profile/mail?open=77&dropped=1");

    expect(await within(reader()).findByRole("heading", { level: 2, name: "Обери лист" })).toBeDefined();
  });
});
