/** «Налаштування» пошти й синк: адреса, інструкція Gmail, синк вручну з лічильником, зміна адреси. */
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { apiMail, apiSettings, mailBackend, type ApiSettings, type MailBackend, type MailOverrides } from "./mailBackend";
import { json, renderClient } from "./testClient";
import { setViewport } from "./viewport";

const LIMIT_TEXT = "Синк уже запитано 2 рази за 30 хв — наступний о 16:30 (Мадрид).";

/** `loaded` — дочекатися розділів налаштувань; для станів завантаження й помилок — `false`. */
async function openSettings(backend: MailBackend, path = "/profile/mail?tab=settings", loaded = path.includes("tab=settings")) {
  setViewport("desktop");
  renderClient(path, backend.fetchFn);
  await screen.findByRole("heading", { level: 1, name: "Пошта" });
  if (loaded) {
    await screen.findByRole("region", { name: "Синхронізація" });
  }
}

function backendWith(settings: Partial<ApiSettings> = {}, overrides: MailOverrides = {}) {
  return mailBackend([apiMail(1)], overrides, { settings: apiSettings(settings) });
}

function section(name: string) {
  return within(screen.getByRole("region", { name }));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("вкладка", () => {
  test("відкривається з адреси сторінки й перемикається вкладками", async () => {
    const user = userEvent.setup();
    await openSettings(backendWith());

    expect(await screen.findByRole("tab", { name: "Налаштування", selected: true })).toBeDefined();
    expect(screen.queryByRole("list", { name: "Список листів" })).toBeNull();

    await user.click(screen.getByRole("tab", { name: "Вхідні" }));

    expect(await screen.findByRole("list", { name: "Список листів" })).toBeDefined();
    expect(screen.getByTestId("location").textContent).toBe("/profile/mail");

    await user.click(screen.getByRole("tab", { name: "Налаштування" }));
    expect(screen.getByTestId("location").textContent).toBe("/profile/mail?tab=settings");
  });

  test("у налаштуваннях лише налаштування: ні листів, ні коду Gmail", async () => {
    await openSettings(backendWith());
    await screen.findByText("mailroom+abcdefghijkl@example.com");

    expect(screen.queryByRole("group", { name: "Код підтвердження пересилання" })).toBeNull();
    expect(screen.queryByRole("searchbox")).toBeNull();
  });

  test("стани завантаження: статус, збій із повтором, пошту не налаштовано, сесія", async () => {
    const user = userEvent.setup();
    let fail = true;
    await openSettings(backendWith({}, { settings: () => (fail ? json(500, {}) : undefined) }), undefined, false);

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("Не вдалося завантажити налаштування пошти.")).toBeDefined();
    fail = false;
    await user.click(within(alert).getByRole("button", { name: "Спробувати ще раз" }));
    expect(await screen.findByText("mailroom+abcdefghijkl@example.com")).toBeDefined();
  });

  test("поки налаштування вантажаться — статус", async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    await openSettings(backendWith({}, { settings: () => gate.then(() => json(200, apiSettings())) }), undefined, false);

    expect(screen.getByRole("status", { name: "Завантажуємо налаштування…" })).toBeDefined();
    release();
    expect(await screen.findByText("mailroom+abcdefghijkl@example.com")).toBeDefined();
  });

  test.each([
    [503, "Пошту не налаштовано: на сервері нема адреси скриньки застосунку."],
    [401, "Сесія завершилась. Увійди знову, щоб побачити налаштування пошти."],
  ])("відповідь %i — пояснення без повтору", async (status, message) => {
    await openSettings(backendWith({}, { settings: () => json(status, {}) }), undefined, false);

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText(message)).toBeDefined();
    expect(within(alert).queryByRole("button")).toBeNull();
  });
});

describe("адреса для пересилання", () => {
  test("адреса, копіювання, інструкція Gmail", async () => {
    const writeText = vi.fn<(text: string) => Promise<void>>(() => Promise.resolve());
    const user = userEvent.setup();
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    await openSettings(backendWith());

    const address = section("Адреса для пересилання");
    expect(await address.findByText("mailroom+abcdefghijkl@example.com")).toBeDefined();
    await user.click(address.getByRole("button", { name: "Копіювати адресу" }));

    expect(writeText).toHaveBeenCalledWith("mailroom+abcdefghijkl@example.com");
    expect(await address.findByText("Адресу скопійовано.")).toBeDefined();

    const steps = address.getByText("Як налаштувати Gmail").closest("details");
    expect(within(steps as HTMLElement).getAllByRole("listitem")).toHaveLength(4);
    expect(within(steps as HTMLElement).getByText(/Якщо Gmail надіслав лише посилання — відкрий оригінал у службовій скриньці/)).toBeDefined();
    expect(within(steps as HTMLElement).getByText(/Код підтвердження, якщо він є, з’явиться у «Вхідних»/)).toBeDefined();
  });

  test("копіювання не вдалося — підказка", async () => {
    const user = userEvent.setup();
    vi.stubGlobal("navigator", { clipboard: { writeText: () => Promise.reject(new Error("denied")) } });
    await openSettings(backendWith());

    await user.click((await section("Адреса для пересилання").findByRole("button", { name: "Копіювати адресу" })) as HTMLElement);

    expect(await section("Адреса для пересилання").findByText("Не вдалося скопіювати — виділи адресу вручну.")).toBeDefined();
  });

  test("адреса вже змінювалась — видно коли", async () => {
    await openSettings(backendWith({ rotated_at: "2026-10-20T08:00:00Z" }));

    expect(await section("Адреса для пересилання").findByText("Адресу змінено 2026-10-20 · 10:00 (Мадрид).")).toBeDefined();
  });

  test("адреса не змінювалась — рядка про зміну нема", async () => {
    await openSettings(backendWith());
    await section("Адреса для пересилання").findByText("mailroom+abcdefghijkl@example.com");

    expect(section("Адреса для пересилання").queryByText(/Адресу змінено/)).toBeNull();
  });
});

describe("синк", () => {
  test("останній синк, лічильник ручних запитів і кнопка", async () => {
    await openSettings(backendWith());

    const sync = section("Синхронізація");
    expect(await sync.findByText("Останній успішний синк: 2026-10-24 · 15:45 (Мадрид)")).toBeDefined();
    expect(sync.getByText("Ручних запитів доступно: 2 з 2 за 30 хв.")).toBeDefined();
    expect(sync.getByRole("button", { name: "Синхронізувати зараз" }).hasAttribute("disabled")).toBe(false);
    expect(sync.getByText("Запит підхоплює серверний таймер. Нові листи з’являться після завершення синку.")).toBeDefined();
  });

  test("синку ще не було й синк не вдався", async () => {
    await openSettings(backendWith({ synced_at: null }));
    expect(await section("Синхронізація").findByText("Синк ще не було.")).toBeDefined();
  });

  test("останній синк не вдався: застереження з текстом помилки", async () => {
    await openSettings(backendWith({ sync_failed: true, sync_error: "Gmail відповів 500 на profile." }));

    const sync = section("Синхронізація");
    expect(await sync.findByRole("alert")).toBeDefined();
    expect(sync.getByText("Останній синк не вдався: Gmail відповів 500 на profile.")).toBeDefined();
    expect(sync.getByText("Останній успішний синк: 2026-10-24 · 15:45 (Мадрид)")).toBeDefined();
  });

  test("запит синку: запит у черзі, лічильник зменшується, кнопка вимикається", async () => {
    const user = userEvent.setup();
    const backend = backendWith();
    await openSettings(backend);

    await user.click(await section("Синхронізація").findByRole("button", { name: "Синхронізувати зараз" }));

    const sync = section("Синхронізація");
    expect(await sync.findByRole("button", { name: "Запит у черзі" })).toBeDefined();
    expect(sync.getByRole("button", { name: "Запит у черзі" }).hasAttribute("disabled")).toBe(true);
    expect(sync.getByText("Ручних запитів доступно: 1 з 2 за 30 хв.")).toBeDefined();
    expect(backend.syncRequests).toBe(1);
  });

  test("ліміт вичерпано: кнопку вимкнено, видно коли звільниться", async () => {
    await openSettings(backendWith({ manual: { limit: 2, remaining: 0, next_at: "2026-10-24T14:30:00Z" } }));

    const sync = section("Синхронізація");
    expect(await sync.findByText("Ручних запитів доступно: 0 з 2 за 30 хв.")).toBeDefined();
    expect(sync.getByRole("button", { name: "Синхронізувати зараз" }).hasAttribute("disabled")).toBe(true);
    expect(sync.getByText("Наступний запит можна о 16:30 (Мадрид).")).toBeDefined();
  });

  test("сервер відмовив із лімітом: його текст у повідомленні", async () => {
    const user = userEvent.setup();
    await openSettings(backendWith({}, { sync: () => json(429, { code: "manual_sync_limit", message: LIMIT_TEXT }) }));

    await user.click(await section("Синхронізація").findByRole("button", { name: "Синхронізувати зараз" }));

    expect(await section("Синхронізація").findByText(LIMIT_TEXT)).toBeDefined();
    expect(section("Синхронізація").queryByRole("button", { name: "Запит у черзі" })).toBeNull();
  });

  test.each([
    [500, "Не вдалося запитати синк. Спробуй ще раз."],
    [401, "Сесія завершилась. Увійди знову, щоб запитати синк."],
    [503, "Пошту не налаштовано: на сервері нема адреси скриньки застосунку."],
  ])("збій синку (%i) — повідомлення", async (status, message) => {
    const user = userEvent.setup();
    await openSettings(backendWith({}, { sync: () => json(status, {}) }));

    await user.click(await section("Синхронізація").findByRole("button", { name: "Синхронізувати зараз" }));

    expect(await section("Синхронізація").findByText(message)).toBeDefined();
  });

  test("кнопка «Синхронізувати» над «Вхідними» запитує синк і показує лічильник", async () => {
    const user = userEvent.setup();
    const backend = backendWith();
    await openSettings(backend, "/profile/mail");
    await screen.findByRole("list", { name: "Список листів" });

    expect(await screen.findByText("Синк: 2026-10-24 · 15:45 · Мадрид · 2 з 2 ручних запитів")).toBeDefined();
    await user.click(screen.getByRole("button", { name: "Синхронізувати" }));

    expect(await screen.findByRole("button", { name: "Запит у черзі" })).toBeDefined();
    expect(await screen.findByText("Синк: 2026-10-24 · 15:45 · Мадрид · 1 з 2 ручних запитів · запит очікує серверного таймера")).toBeDefined();
    expect(backend.syncRequests).toBe(1);
  });

  test("над «Вхідними»: синку ще не було; сервер відмовив; ліміт вичерпано", async () => {
    const user = userEvent.setup();
    await openSettings(backendWith({ synced_at: null, manual: { limit: 2, remaining: 1, next_at: null } }, { sync: () => json(429, { message: LIMIT_TEXT }) }), "/profile/mail");

    expect(await screen.findByText("Синку ще не було · 1 з 2 ручних запитів")).toBeDefined();
    await user.click(screen.getByRole("button", { name: "Синхронізувати" }));

    expect(await screen.findByText(LIMIT_TEXT)).toBeDefined();
  });

  test("над «Вхідними»: лічильник нуль — кнопка вимкнена", async () => {
    await openSettings(backendWith({ manual: { limit: 2, remaining: 0, next_at: "2026-10-24T14:30:00Z" } }), "/profile/mail");

    expect((await screen.findByRole("button", { name: "Синхронізувати" })).hasAttribute("disabled")).toBe(true);
  });

  test("над «Вхідними»: збій синку скриньки видно, а без налаштувань рядка нема", async () => {
    await openSettings(backendWith({ sync_failed: true, sync_error: "Gmail down" }), "/profile/mail");
    expect(await screen.findByText("Синк: останній запуск не вдався · 2 з 2 ручних запитів")).toBeDefined();
  });

  test("над «Вхідними»: налаштування недоступні — рядка синку нема, листи є", async () => {
    await openSettings(backendWith({}, { settings: () => json(500, {}) }), "/profile/mail");

    await screen.findByRole("list", { name: "Список листів" });
    await waitFor(() => expect(screen.queryByText(/ручних запитів/)).toBeNull());
    expect(screen.getByRole("button", { name: "Синхронізувати" }).hasAttribute("disabled")).toBe(true);
  });
});

describe("зміна адреси", () => {
  async function openRotate(backend: MailBackend) {
    const user = userEvent.setup();
    await openSettings(backend);
    await user.click(await section("Змінити адресу пересилання").findByRole("button", { name: "Змінити адресу" }));
    return { user, dialog: within(await screen.findByRole("alertdialog", { name: "Змінити адресу пересилання?" })) };
  }

  test("діалог попереджає, що стара адреса перестане працювати", async () => {
    const { dialog } = await openRotate(backendWith());

    expect(dialog.getByText(/Стара адреса перестане працювати одразу/)).toBeDefined();
    expect(dialog.getByText(/оновити пересилання й фільтри Gmail/)).toBeDefined();
  });

  test("підтвердження: нова адреса й нагадування оновити Gmail", async () => {
    const backend = backendWith();
    const { user, dialog } = await openRotate(backend);

    await user.click(dialog.getByRole("button", { name: "Змінити адресу" }));

    expect(await section("Адреса для пересилання").findByText("mailroom+zyxwvutsrqpo@example.com")).toBeDefined();
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(screen.getByRole("status", { name: "Результат" }).textContent).toBe("Адресу змінено. Онови пересилання й фільтри Gmail.");
    expect(backend.rotateRequests).toBe(1);
  });

  test("скасування нічого не міняє", async () => {
    const backend = backendWith();
    const { user, dialog } = await openRotate(backend);

    await user.click(dialog.getByRole("button", { name: "Скасувати" }));

    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(backend.rotateRequests).toBe(0);
    expect(section("Адреса для пересилання").getByText("mailroom+abcdefghijkl@example.com")).toBeDefined();
  });

  test.each([
    [500, "Не вдалося змінити адресу. Спробуй ще раз."],
    [401, "Сесія завершилась. Увійди знову, щоб змінити адресу."],
    [503, "Пошту не налаштовано: на сервері нема адреси скриньки застосунку."],
  ])("збій (%i) лишає діалог відкритим з повідомленням", async (status, message) => {
    const { user, dialog } = await openRotate(backendWith({}, { rotate: () => json(status, {}) }));

    await user.click(dialog.getByRole("button", { name: "Змінити адресу" }));

    expect(await dialog.findByRole("alert")).toBeDefined();
    expect(dialog.getByText(message)).toBeDefined();
    expect(screen.getByRole("alertdialog")).toBeDefined();
  });

  test("подвійний клік не змінює адресу двічі", async () => {
    const backend = backendWith();
    const { dialog } = await openRotate(backend);
    const confirm = dialog.getByRole("button", { name: "Змінити адресу" });

    // Два кліки в одному кадрі: другий приходить до того, як кнопку вимкнено.
    fireEvent.click(confirm);
    fireEvent.click(confirm);

    await screen.findByRole("region", { name: "Адреса для пересилання" });
    expect(await section("Адреса для пересилання").findByText("mailroom+zyxwvutsrqpo@example.com")).toBeDefined();
    expect(backend.rotateRequests).toBe(1);
  });
});
