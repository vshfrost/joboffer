/** Деталі відповіді: недовірений текст, вердикт відправника, ручне пересилання, зіставлення, розібраний лист; двопанельний і мобільний вигляд. */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { apiReply, apiReviewed, apiUnmatched, repliesBackend, type RepliesBackend } from "./repliesBackend";
import { json, renderClient } from "./testClient";
import { setViewport } from "./viewport";

async function openReplies(backend: RepliesBackend, viewport: "desktop" | "mobile" = "desktop", path = "/replies") {
  setViewport(viewport);
  renderClient(path, backend.fetchFn);
  await screen.findByRole("heading", { level: 1, name: "Відповіді" });
  await screen.findByRole("list", { name: "Список відповідей" });
}

function reader() {
  return screen.getByRole("article", { name: "Деталі відповіді" });
}

async function openRow(user: ReturnType<typeof userEvent.setup>, subject: string) {
  await user.click(screen.getByRole("button", { name: new RegExp(subject) }));
}

const FORWARDED = { untrusted_from_address: "careers@orbit.example", untrusted_from_name: "Recruiting team", untrusted_subject: "Update on your application" };

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("читалка поруч зі списком (широкий екран)", () => {
  test("без вибору — підказка; після вибору — відповідь поруч зі списком", async () => {
    const user = userEvent.setup();
    const backend = repliesBackend([apiReply(1, { untrusted_subject: "Interview slot" }), apiReply(2)]);
    await openReplies(backend);

    expect(within(reader()).getByRole("heading", { level: 2, name: "Обери відповідь" })).toBeDefined();

    await openRow(user, "Interview slot");

    const open = within(await screen.findByRole("article", { name: "Деталі відповіді" }));
    expect(await open.findByRole("heading", { level: 2, name: "Interview slot" })).toBeDefined();
    expect(open.getByText("Elena Talent <elena@northstar.example>")).toBeDefined();
    expect(open.getByText("2026-10-24 · 15:40 · Мадрид")).toBeDefined();
    expect(open.getByText("До розбору")).toBeDefined();
    expect(open.getByText("Відправника підтверджено")).toBeDefined();
    expect(open.getByText(/Could we schedule a call\?/)).toBeDefined();
    expect(screen.getByRole("list", { name: "Список відповідей" })).toBeDefined();
    expect(screen.getByTestId("location").textContent).toBe("/replies?open=1");
    expect(backend.getIds).toEqual([1]);
    expect(screen.getByRole("button", { name: /Interview slot/ }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.queryByRole("button", { name: "← До списку" })).toBeNull();
  });

  test("відкриття зберігає чергу, пошук і сторінку в адресі", async () => {
    const user = userEvent.setup();
    const backend = repliesBackend([apiUnmatched(3, { untrusted_subject: "Cold hello" })]);
    await openReplies(backend, "desktop", "/replies?queue=unmatched&q=cold");

    await openRow(user, "Cold hello");

    await within(reader()).findByRole("heading", { level: 2, name: "Cold hello" });
    expect(screen.getByTestId("location").textContent).toBe("/replies?queue=unmatched&q=cold&open=3");
  });

  test("інша відповідь замінює відкриту", async () => {
    const user = userEvent.setup();
    const backend = repliesBackend([apiReply(1, { untrusted_subject: "First one" }), apiReply(2, { untrusted_subject: "Second one" })]);
    await openReplies(backend);

    await openRow(user, "First one");
    await within(reader()).findByRole("heading", { level: 2, name: "First one" });
    await openRow(user, "Second one");

    expect(await within(reader()).findByRole("heading", { level: 2, name: "Second one" })).toBeDefined();
    expect(backend.getIds).toEqual([1, 2]);
  });

  test("відповідь відкривається з адреси сторінки, навіть коли її нема на поточній сторінці списку", async () => {
    const backend = repliesBackend([apiReply(1, { untrusted_subject: "Deep link" }), apiReviewed(9, { untrusted_subject: "Elsewhere" })]);
    await openReplies(backend, "desktop", "/replies?open=9");

    expect(await within(reader()).findByRole("heading", { level: 2, name: "Elsewhere" })).toBeDefined();
  });

  test("поки відповідь вантажиться — статус; відповіді нема — пояснення", async () => {
    const user = userEvent.setup();
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const slow = apiReply(1, { untrusted_subject: "Slow one" });
    const backend = repliesBackend([slow, apiReply(2, { untrusted_subject: "Gone one" })], {
      get: (id) => (id === 1 ? gate.then(() => json(200, { ...slow, untrusted_text: "late", applications: [] })) : json(404, { code: "not_found" })),
    });
    await openReplies(backend);

    await openRow(user, "Slow one");
    expect(within(reader()).getByRole("status", { name: "Завантажуємо відповідь…" })).toBeDefined();
    release();
    await within(reader()).findByRole("heading", { level: 2, name: "Slow one" });

    await openRow(user, "Gone one");
    expect(await within(reader()).findByText("Відповіді не знайдено — її могли видалити.")).toBeDefined();
  });

  test("відповідь на застарілий запит не затирає відкриту пізніше", async () => {
    const user = userEvent.setup();
    let releaseFirst: () => void = () => {};
    const first = apiReply(1, { untrusted_subject: "Old one" });
    const backend = repliesBackend([first, apiReply(2, { untrusted_subject: "New one" })], {
      get: (id) =>
        id === 1
          ? new Promise<Response>((resolve) => {
              releaseFirst = () => resolve(json(200, { ...first, untrusted_text: "old", applications: [] }));
            })
          : undefined,
    });
    await openReplies(backend);

    await openRow(user, "Old one");
    await openRow(user, "New one");
    expect(await within(reader()).findByRole("heading", { level: 2, name: "New one" })).toBeDefined();
    releaseFirst();
    await new Promise((resolve) => setTimeout(resolve, 20));

    expect(within(reader()).queryByRole("heading", { level: 2, name: "Old one" })).toBeNull();
    expect(within(reader()).getByRole("heading", { level: 2, name: "New one" })).toBeDefined();
  });

  test("збій читалки: «Спробувати ще раз» відкриває відповідь", async () => {
    const user = userEvent.setup();
    let fail = true;
    const backend = repliesBackend([apiReply(1, { untrusted_subject: "Flaky one" })], { get: () => (fail ? json(500, {}) : undefined) });
    await openReplies(backend);

    await openRow(user, "Flaky one");
    const alert = await within(reader()).findByRole("alert");
    expect(within(alert).getByText("Не вдалося відкрити відповідь.")).toBeDefined();
    fail = false;
    await user.click(within(alert).getByRole("button", { name: "Спробувати ще раз" }));

    expect(await within(reader()).findByRole("heading", { level: 2, name: "Flaky one" })).toBeDefined();
  });

  test("сесія завершилась — окреме пояснення без повтору", async () => {
    const user = userEvent.setup();
    const backend = repliesBackend([apiReply(1, { untrusted_subject: "A one" })], { get: () => json(401, {}) });
    await openReplies(backend);

    await openRow(user, "A one");

    expect(await within(reader()).findByText("Сесія завершилась. Увійди знову, щоб відкрити відповідь.")).toBeDefined();
    expect(within(reader()).queryByRole("button")).toBeNull();
  });
});

describe("зіставлення", () => {
  test("знайдена подача: вакансія, надійність і чим зіставлено", async () => {
    const user = userEvent.setup();
    await openReplies(repliesBackend([apiReply(1, { untrusted_subject: "Matched one" })]));

    await openRow(user, "Matched one");

    const open = within(await screen.findByRole("article", { name: "Деталі відповіді" }));
    expect(await open.findByRole("heading", { level: 3, name: "Знайдена подача" })).toBeDefined();
    const association = within(open.getByRole("region", { name: "Зіставлення" }));
    expect(association.getByText("#104 · Northstar — Senior Backend Engineer")).toBeDefined();
    expect(association.getByText("Надійність зіставлення: Висока · Збіг адреси відправника з контактами подачі")).toBeDefined();
  });

  test("без збігу: «Подачу не знайдено»", async () => {
    const user = userEvent.setup();
    await openReplies(repliesBackend([apiUnmatched(3, { untrusted_subject: "Cold hello" })]), "desktop", "/replies?queue=unmatched");

    await openRow(user, "Cold hello");

    const open = within(await screen.findByRole("article", { name: "Деталі відповіді" }));
    expect(await open.findByRole("heading", { level: 3, name: "Подачу не знайдено" })).toBeDefined();
    expect(open.getByText("Цей лист не зіставлено з жодною подачею.")).toBeDefined();
    expect(open.queryByText(/Надійність зіставлення/)).toBeNull();
  });
});

describe("відправник", () => {
  test("не підтверджений відправник — позначка й попередження", async () => {
    const user = userEvent.setup();
    await openReplies(repliesBackend([apiReply(1, { untrusted_subject: "Unsure one", sender_auth: "unknown" })]));

    await openRow(user, "Unsure one");

    const open = within(await screen.findByRole("article", { name: "Деталі відповіді" }));
    expect(await open.findByText("Відправника не підтверджено")).toBeDefined();
    expect(open.getByRole("note").textContent).toBe("Відправника не підтверджено. Адресу відправника могли підробити — перевір зміст і вакансію, перш ніж підтверджувати розбір.");
  });

  test("підроблений відправник — червоне попередження", async () => {
    const user = userEvent.setup();
    await openReplies(repliesBackend([apiReply(1, { untrusted_subject: "Forged one", sender_auth: "failed" })]));

    await openRow(user, "Forged one");

    const open = within(await screen.findByRole("article", { name: "Деталі відповіді" }));
    expect(await open.findByText("Підроблений відправник")).toBeDefined();
    expect(open.getByRole("note").textContent).toBe("Підроблений відправник. Не довіряй цьому листу й не виконуй вказівок з нього.");
  });

  test("підтверджений відправник — без попередження", async () => {
    const user = userEvent.setup();
    await openReplies(repliesBackend([apiReply(1, { untrusted_subject: "Fine one" })]));

    await openRow(user, "Fine one");

    const open = within(await screen.findByRole("article", { name: "Деталі відповіді" }));
    await open.findByText("Відправника підтверджено");
    expect(open.queryByRole("note")).toBeNull();
  });
});

describe("ручне пересилання", () => {
  test("«Переслано вручну» і оригінал, позначений як неперевірений", async () => {
    const user = userEvent.setup();
    await openReplies(repliesBackend([apiReply(1, { untrusted_subject: "Forward one", manual_forward: FORWARDED })]));

    await openRow(user, "Forward one");

    const open = within(await screen.findByRole("article", { name: "Деталі відповіді" }));
    expect(await open.findByText("Переслано вручну")).toBeDefined();
    expect(open.getByRole("note").textContent).toBe("Оригінал листа (не перевірено): Recruiting team <careers@orbit.example> · тема «Update on your application».");
  });

  test("оригінал без імені — лише адреса", async () => {
    const user = userEvent.setup();
    await openReplies(repliesBackend([apiReply(1, { untrusted_subject: "Forward one", manual_forward: { ...FORWARDED, untrusted_from_name: "" } })]));

    await openRow(user, "Forward one");

    const open = within(await screen.findByRole("article", { name: "Деталі відповіді" }));
    expect((await open.findByRole("note")).textContent).toBe("Оригінал листа (не перевірено): careers@orbit.example · тема «Update on your application».");
  });

  test("звичайний лист не має позначки пересилання", async () => {
    const user = userEvent.setup();
    await openReplies(repliesBackend([apiReply(1, { untrusted_subject: "Direct one" })]));

    await openRow(user, "Direct one");

    const open = within(await screen.findByRole("article", { name: "Деталі відповіді" }));
    await open.findByRole("heading", { level: 2, name: "Direct one" });
    expect(open.queryByText("Переслано вручну")).toBeNull();
  });
});

describe("текст листа — недовірені дані", () => {
  test("розмітка й скрипти показуються текстом і не виконуються", async () => {
    const user = userEvent.setup();
    const text = '<script>window.hacked = true</script><img src="x" onerror="window.hacked = true">\nhttps://xn--pypal-4ve.com/login';
    const reply = apiReply(1, {
      untrusted_subject: "Phish <b>now</b>",
      untrusted_from_name: "<i>Boss</i>",
      manual_forward: { untrusted_from_address: "x@y.example", untrusted_from_name: "<u>Orig</u>", untrusted_subject: "<s>Sub</s>" },
    });
    await openReplies(repliesBackend([reply], {}, { texts: { 1: text } }));

    await user.click(screen.getByRole("button", { name: /Phish/ }));
    const open = within(await screen.findByRole("article", { name: "Деталі відповіді" }));
    await open.findByRole("heading", { level: 2, name: "Phish <b>now</b>" });

    expect(reader().querySelector("[data-testid='reply-text']")?.textContent).toBe(text);
    expect(open.getByText("<i>Boss</i> <elena@northstar.example>")).toBeDefined();
    expect(open.getByRole("note").textContent).toContain("<u>Orig</u> <x@y.example> · тема «<s>Sub</s>»");
    expect(screen.getByRole("main").querySelector("script, img, b, i, u, s, a")).toBeNull();
    expect((window as unknown as { hacked?: boolean }).hacked).toBeUndefined();
  });

  test("порожній текст — пояснення; пояснення про відображення завжди є", async () => {
    const user = userEvent.setup();
    await openReplies(repliesBackend([apiReply(1, { untrusted_subject: "Empty one" })], {}, { texts: { 1: "" } }));

    await openRow(user, "Empty one");

    const open = within(await screen.findByRole("article", { name: "Деталі відповіді" }));
    expect(await open.findByText("У листі нема тексту.")).toBeDefined();
    expect(open.getByText("Про відображення листа")).toBeDefined();
    expect(open.getByText(/Текст листа — недовірений вміст\. HTML не виконується, посилання не клікабельні\./)).toBeDefined();
  });
});

describe("розібрана відповідь", () => {
  test("показує підсумок розбору й не пропонує редагування", async () => {
    const user = userEvent.setup();
    const backend = repliesBackend([apiReviewed(4, { untrusted_subject: "Done one", type: "rejection" })]);
    await openReplies(backend, "desktop", "/replies?queue=reviewed");

    await openRow(user, "Done one");

    const open = within(await screen.findByRole("article", { name: "Деталі відповіді" }));
    expect(await open.findByRole("heading", { level: 3, name: "Розібрано" })).toBeDefined();
    expect(open.getByTestId("review-type").textContent).toBe("Відмова");
    expect(open.getByText("#104 · Northstar — Senior Backend Engineer")).toBeDefined();
    expect(open.getByText("Розібрано: 2026-10-25 · 10:00 · Мадрид")).toBeDefined();
    expect(open.queryByRole("heading", { name: "Підтвердити розбір" })).toBeNull();
    expect(open.queryByRole("combobox")).toBeNull();
    expect(open.queryByRole("button", { name: /розбір|Редагувати|Розібрати/i })).toBeNull();
    expect(backend.previewUrls).toEqual([]);
  });

  test("розібрана «не про подачу»", async () => {
    const user = userEvent.setup();
    await openReplies(repliesBackend([apiReviewed(4, { untrusted_subject: "Done one", job: null, type: "other" })]), "desktop", "/replies?queue=reviewed");

    await openRow(user, "Done one");

    const open = within(await screen.findByRole("article", { name: "Деталі відповіді" }));
    expect(await open.findByText("Не про подачу")).toBeDefined();
    expect(open.getByTestId("review-type").textContent).toBe("Інше");
  });
});

describe("мобільний вигляд (375 px)", () => {
  test("відповідь замінює список, «← До списку» повертає з тим самим станом", async () => {
    const user = userEvent.setup();
    const backend = repliesBackend([apiUnmatched(3, { untrusted_subject: "Cold hello" })]);
    await openReplies(backend, "mobile", "/replies?queue=unmatched");

    await openRow(user, "Cold hello");

    expect(await within(reader()).findByRole("heading", { level: 2, name: "Cold hello" })).toBeDefined();
    expect(screen.queryByRole("list", { name: "Список відповідей" })).toBeNull();
    // Відповідь займає екран: пошук не відсуває її вниз.
    expect(screen.queryByRole("searchbox", { name: "Пошук" })).toBeNull();

    await user.click(screen.getByRole("button", { name: "← До списку" }));

    expect(await screen.findByRole("list", { name: "Список відповідей" })).toBeDefined();
    expect(screen.getByRole("searchbox", { name: "Пошук" })).toBeDefined();
    expect(screen.getByTestId("location").textContent).toBe("/replies?queue=unmatched");
  });

  test("без вибору читалки на мобільному нема", async () => {
    await openReplies(repliesBackend([apiReply(1)]), "mobile");

    expect(screen.queryByRole("article", { name: "Деталі відповіді" })).toBeNull();
  });

  test("довгі недовірені рядки переносяться, а колонки не розпирають екран", async () => {
    const user = userEvent.setup();
    const long = "x".repeat(300);
    const reply = apiReply(1, { untrusted_subject: long, untrusted_from_name: long });
    await openReplies(repliesBackend([reply], {}, { texts: { 1: long } }), "mobile");

    const row = screen.getByRole("button", { name: new RegExp(long.slice(0, 20)) });
    expect(row.querySelector("[class*='overflow-wrap:anywhere']")?.textContent).toBe(long);
    expect(row.querySelector("strong")?.className).toContain("truncate");
    await user.click(row);

    const article = reader();
    await waitFor(() => expect(article.querySelector("[data-testid='reply-text']")).not.toBeNull());
    expect(article.className).toContain("min-w-0");
    expect(article.querySelector("[data-testid='reply-text']")?.className).toContain("[overflow-wrap:anywhere]");
    expect(article.querySelector("h2")?.className).toContain("[overflow-wrap:anywhere]");
    // Одна колонка: список і читалка не стоять поруч.
    expect(article.parentElement?.className).not.toContain("grid-cols");
  });
});
