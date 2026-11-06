/** «Відповіді»: три черги з лічильниками, пошук, сторінки, порожні стани й помилки. Усе живе в адресі сторінки. */
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { apiReply, apiReviewed, apiUnmatched, repliesBackend, type RepliesBackend, type RepliesOverrides } from "./repliesBackend";
import { json, renderClient } from "./testClient";
import { setViewport } from "./viewport";

async function openReplies(backend: RepliesBackend, path = "/replies") {
  setViewport("desktop");
  renderClient(path, backend.fetchFn);
  await screen.findByRole("heading", { level: 1, name: "Відповіді" });
}

async function rows() {
  return within(await screen.findByRole("list", { name: "Список відповідей" })).getAllByRole("listitem");
}

async function subjects() {
  return (await rows()).map((row) => within(row).getByRole("button").textContent ?? "");
}

function many(count: number) {
  return Array.from({ length: count }, (_, index) => apiReply(index + 1, { untrusted_subject: `Subject ${index + 1}` }));
}

const MIXED = [
  apiReply(1, { untrusted_subject: "Matched one" }),
  apiReply(2, { untrusted_subject: "Matched two" }),
  apiUnmatched(3, { untrusted_subject: "Unmatched one" }),
  apiReviewed(4, { untrusted_subject: "Reviewed one" }),
  apiReviewed(5, { untrusted_subject: "Reviewed two", type: "rejection" }),
  apiReviewed(6, { untrusted_subject: "Reviewed three", job: null, type: "other" }),
];

describe("черги", () => {
  test("заголовок, опис і назва вкладки браузера", async () => {
    await openReplies(repliesBackend(MIXED));

    expect(screen.getByText("Розбери листи та підтвердь зміни у подачах.")).toBeDefined();
    expect(document.title).toBe("Відповіді · joboffer");
  });

  test("три таби з лічильниками; за замовчуванням вибрано «До розбору»", async () => {
    const backend = repliesBackend(MIXED);
    await openReplies(backend);

    const tabs = screen.getByRole("tablist", { name: "Черги відповідей" });
    expect(await within(tabs).findByRole("tab", { name: "До розбору · 2", selected: true })).toBeDefined();
    expect(within(tabs).getByRole("tab", { name: "Без вакансії · 1", selected: false })).toBeDefined();
    expect(within(tabs).getByRole("tab", { name: "Розібрані · 3", selected: false })).toBeDefined();
    expect(backend.boardUrls).toEqual(["/api/replies"]);
  });

  test("«До розбору»: лише листи зі збігом; рядок — відправник, день і час за Мадридом, тема, статус і вакансія", async () => {
    await openReplies(repliesBackend(MIXED));

    expect(await subjects()).toHaveLength(2);
    const [first] = await rows();
    const row = within(first as HTMLElement);
    expect(row.getByText("Elena Talent")).toBeDefined();
    expect(row.getByText("2026-10-24")).toBeDefined();
    expect(row.getByText("15:40")).toBeDefined();
    expect(row.getByText("Matched one")).toBeDefined();
    expect(row.getByText("До розбору")).toBeDefined();
    expect(row.getByText("#104 · Northstar")).toBeDefined();
    expect(await screen.findByText("Відповіді компаній · 2")).toBeDefined();
  });

  test("без імені відправника показується адреса", async () => {
    await openReplies(repliesBackend([apiReply(1, { untrusted_from_name: "" })]));

    const [row] = await rows();
    expect(within(row as HTMLElement).getByText("elena@northstar.example")).toBeDefined();
  });

  test("«Без вакансії»: перемикання пише чергу в адресу й запитує її в сервера", async () => {
    const user = userEvent.setup();
    const backend = repliesBackend(MIXED);
    await openReplies(backend);
    await rows();

    await user.click(screen.getByRole("tab", { name: "Без вакансії · 1" }));

    expect(await screen.findByText("Unmatched one")).toBeDefined();
    expect(screen.queryByText("Matched one")).toBeNull();
    const [row] = await rows();
    expect(within(row as HTMLElement).getByText("Без вакансії")).toBeDefined();
    expect(within(row as HTMLElement).queryByText(/^#\d+/)).toBeNull();
    expect(screen.getByTestId("location").textContent).toBe("/replies?queue=unmatched");
    expect(backend.boardUrls.at(-1)).toBe("/api/replies?queue=unmatched");
    expect(screen.getByRole("tab", { name: "Без вакансії · 1", selected: true })).toBeDefined();
  });

  test("«Розібрані»: у рядку тип відповіді замість черги", async () => {
    await openReplies(repliesBackend(MIXED), "/replies?queue=reviewed");

    expect(await subjects()).toHaveLength(3);
    const labels = (await rows()).map((row) => within(row).getByTestId("status").textContent);
    expect(labels).toEqual(["Запрошення", "Відмова", "Інше"]);
    expect(screen.getByRole("tab", { name: "Розібрані · 3", selected: true })).toBeDefined();
  });

  test("ручне пересилання має позначку «Переслано вручну» в рядку", async () => {
    const forwarded = { untrusted_from_address: "careers@orbit.example", untrusted_from_name: "Recruiting team", untrusted_subject: "Update" };
    await openReplies(repliesBackend([apiReply(1, { manual_forward: forwarded }), apiReply(2)]));

    const [first, second] = await rows();
    expect(within(first as HTMLElement).getByText("Переслано вручну")).toBeDefined();
    expect(within(second as HTMLElement).queryByText("Переслано вручну")).toBeNull();
  });

  test("невідома черга в адресі — «До розбору»", async () => {
    const backend = repliesBackend(MIXED);
    await openReplies(backend, "/replies?queue=nonsense");

    expect(await subjects()).toHaveLength(2);
    expect(screen.getByRole("tab", { name: "До розбору · 2", selected: true })).toBeDefined();
  });

  test("поки відповідь вантажиться — статус із скелетоном; лічильники лишаються з попередньої відповіді", async () => {
    const user = userEvent.setup();
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    let first = true;
    const backend = repliesBackend(MIXED, {
      board: () => {
        if (first) {
          first = false;
          return undefined;
        }
        return gate.then(() => json(200, { queue: "unmatched", items: [], page: { number: 1, size: 20, total: 0, first: 1, last: 0, has_newer: false, has_older: false }, counts: { matched: 2, unmatched: 1, reviewed: 3 } }));
      },
    });
    await openReplies(backend);
    await rows();

    await user.click(screen.getByRole("tab", { name: "Без вакансії · 1" }));

    expect(screen.getByRole("status", { name: "Завантажуємо відповіді…" })).toBeDefined();
    expect(screen.getByRole("tab", { name: "Розібрані · 3" })).toBeDefined();
    release();
    expect(await screen.findByText("Відповідей без вакансії немає")).toBeDefined();
    expect(screen.queryByRole("status", { name: "Завантажуємо відповіді…" })).toBeNull();
  });

  test("відповідь на застарілий запит не затирає новішу чергу", async () => {
    const user = userEvent.setup();
    let releaseMatched: () => void = () => {};
    const late = json(200, {
      queue: "matched",
      items: [apiReply(1, { untrusted_subject: "Late matched" })],
      page: { number: 1, size: 20, total: 1, first: 1, last: 1, has_newer: false, has_older: false },
      counts: { matched: 2, unmatched: 1, reviewed: 3 },
    });
    const backend = repliesBackend(MIXED, {
      board: (url) =>
        url.searchParams.get("queue") === null
          ? new Promise<Response>((resolve) => {
              releaseMatched = () => resolve(late);
            })
          : undefined,
    });
    await openReplies(backend);

    await user.click(screen.getByRole("tab", { name: /Розібрані/ }));
    expect(await screen.findByText("Reviewed one")).toBeDefined();
    releaseMatched();
    await new Promise((resolve) => setTimeout(resolve, 20));

    expect(screen.queryByText("Late matched")).toBeNull();
    expect(screen.getByText("Reviewed one")).toBeDefined();
  });
});

describe("пошук і сторінки", () => {
  test("пошук за Enter пише запит в адресу, зберігає чергу й не змінює лічильники", async () => {
    const user = userEvent.setup();
    const backend = repliesBackend([
      apiUnmatched(1, { untrusted_subject: "Offer from Acme" }),
      apiUnmatched(2, { untrusted_subject: "Newsletter" }),
      apiReply(3),
    ]);
    await openReplies(backend, "/replies?queue=unmatched");
    await rows();

    await user.type(screen.getByRole("searchbox", { name: "Пошук" }), "acme{Enter}");

    expect(await screen.findByText("Відповіді компаній · 1")).toBeDefined();
    const found = await subjects();
    expect(found).toHaveLength(1);
    expect(found[0]).toContain("Offer from Acme");
    expect(screen.getByTestId("location").textContent).toBe("/replies?queue=unmatched&q=acme");
    expect(backend.boardUrls.at(-1)).toBe("/api/replies?queue=unmatched&q=acme");
    expect(screen.getByRole("tab", { name: "Без вакансії · 2" })).toBeDefined();
    expect(screen.getByRole("tab", { name: "До розбору · 1" })).toBeDefined();
  });

  test("кнопка «Знайти» шукає, пошук пробільної рядка скидає запит", async () => {
    const user = userEvent.setup();
    const backend = repliesBackend([apiReply(1, { untrusted_subject: "Offer from Acme" }), apiReply(2, { untrusted_subject: "Other" })]);
    await openReplies(backend);
    await rows();

    await user.type(screen.getByRole("searchbox", { name: "Пошук" }), "  acme  ");
    await user.click(screen.getByRole("button", { name: "Знайти" }));
    expect(await screen.findByText("Відповіді компаній · 1")).toBeDefined();
    expect(screen.getByTestId("location").textContent).toBe("/replies?q=acme");

    await user.clear(screen.getByRole("searchbox", { name: "Пошук" }));
    await user.type(screen.getByRole("searchbox", { name: "Пошук" }), "   ");
    await user.click(screen.getByRole("button", { name: "Знайти" }));
    expect(await screen.findByText("Відповіді компаній · 2")).toBeDefined();
    expect(screen.getByTestId("location").textContent).toBe("/replies");
  });

  test("пошук з адреси видно в полі; запит довший за 200 символів обрізається", async () => {
    const backend = repliesBackend(many(1));
    await openReplies(backend, `/replies?q=${"a".repeat(250)}`);
    await screen.findByText("Немає збігів");

    expect((screen.getByRole("searchbox", { name: "Пошук" }) as HTMLInputElement).value).toBe("a".repeat(200));
    expect(backend.boardUrls).toEqual([`/api/replies?q=${"a".repeat(200)}`]);
  });

  test("порожня видача за пошуком — «Немає збігів» і «Скинути пошук»", async () => {
    const user = userEvent.setup();
    const backend = repliesBackend(many(2));
    await openReplies(backend, "/replies?q=zzz");

    expect(await screen.findByText("Немає збігів")).toBeDefined();
    expect(screen.getByText("Спробуй інший запит.")).toBeDefined();
    await user.click(screen.getByRole("button", { name: "Скинути пошук" }));

    expect(await subjects()).toHaveLength(2);
    expect(screen.getByTestId("location").textContent).toBe("/replies");
    expect(screen.queryByRole("button", { name: "Скинути пошук" })).toBeNull();
  });

  test("розмір сторінки: вибір пише per_page в адресу й у запит, сторінка скидається на першу", async () => {
    const user = userEvent.setup();
    const backend = repliesBackend(many(60));
    await openReplies(backend, "/replies?page=2");
    await rows();

    await user.selectOptions(screen.getByRole("combobox", { name: "На сторінці" }), "50");

    expect(await screen.findByText("1–50 з 60")).toBeDefined();
    expect(screen.getByTestId("location").textContent).toBe("/replies?per_page=50");
    expect(backend.boardUrls.at(-1)).toBe("/api/replies?per_page=50");
  });

  test("сторінки: «Старіші» і «Новіші» пишуть page в адресу, діапазон і стан кнопок відповідають", async () => {
    const user = userEvent.setup();
    const backend = repliesBackend(many(45));
    await openReplies(backend);
    await rows();

    expect(screen.getByText("1–20 з 45")).toBeDefined();
    expect((screen.getByRole("button", { name: "Новіші листи" }) as HTMLButtonElement).disabled).toBe(true);
    await user.click(screen.getByRole("button", { name: "Старіші листи" }));

    expect(await screen.findByText("21–40 з 45")).toBeDefined();
    expect(screen.getByTestId("location").textContent).toBe("/replies?page=2");
    expect(backend.boardUrls.at(-1)).toBe("/api/replies?page=2");

    await user.click(screen.getByRole("button", { name: "Новіші листи" }));
    expect(await screen.findByText("1–20 з 45")).toBeDefined();
    expect(screen.getByTestId("location").textContent).toBe("/replies");
  });

  test("перемикання черги скидає сторінку на першу", async () => {
    const user = userEvent.setup();
    const backend = repliesBackend([...many(25), apiUnmatched(100)]);
    await openReplies(backend, "/replies?page=2");
    await rows();

    await user.click(screen.getByRole("tab", { name: /Без вакансії/ }));

    expect(await screen.findByText("1–1 з 1")).toBeDefined();
    expect(screen.getByTestId("location").textContent).toBe("/replies?queue=unmatched");
  });

  test("сторінка за межею списку — пояснення і «На першу сторінку»", async () => {
    const user = userEvent.setup();
    const backend = repliesBackend(many(3));
    await openReplies(backend, "/replies?page=9");

    expect(await screen.findByText("На цій сторінці відповідей нема")).toBeDefined();
    expect(screen.getByText("0 листів на цій сторінці з 3")).toBeDefined();
    await user.click(screen.getByRole("button", { name: "На першу сторінку" }));

    expect(await subjects()).toHaveLength(3);
    expect(screen.getByTestId("location").textContent).toBe("/replies");
  });

  test("нерозпізнані page і per_page в адресі — значення за замовчуванням", async () => {
    const backend = repliesBackend(many(2));
    await openReplies(backend, "/replies?page=abc&per_page=7");

    expect(await subjects()).toHaveLength(2);
    expect(backend.boardUrls).toEqual(["/api/replies"]);
  });
});

describe("порожні стани", () => {
  test.each([
    { path: "/replies", title: "У цій черзі все розібрано", hint: "Нові відповіді з’являться після пересилання та синхронізації пошти." },
    { path: "/replies?queue=unmatched", title: "Відповідей без вакансії немає", hint: "Усі листи компаній зіставлено з подачами." },
    { path: "/replies?queue=reviewed", title: "Розібраних відповідей поки немає", hint: "Розібрані листи з’являться тут." },
  ])("порожня черга $path", async ({ path, title, hint }) => {
    await openReplies(repliesBackend([]), path);

    expect(await screen.findByText(title)).toBeDefined();
    expect(screen.getByText(hint)).toBeDefined();
    expect(screen.queryByRole("button", { name: "Скинути пошук" })).toBeNull();
  });
});

describe("помилки", () => {
  async function failing(override: NonNullable<RepliesOverrides["board"]>) {
    const backend = repliesBackend(many(2), { board: override });
    await openReplies(backend);
    return backend;
  }

  test("мережа недоступна — повідомлення і «Спробувати ще раз», який знову вантажить чергу", async () => {
    const user = userEvent.setup();
    let offline = true;
    await failing(() => (offline ? Promise.reject(new Error("offline")) : undefined));

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("Не вдалося завантажити відповіді.")).toBeDefined();
    offline = false;
    await user.click(within(alert).getByRole("button", { name: "Спробувати ще раз" }));

    expect(await subjects()).toHaveLength(2);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  test("помилка сервера і відповідь не за контрактом — те саме повідомлення", async () => {
    const user = userEvent.setup();
    let mode: "server" | "contract" = "server";
    await failing(() => (mode === "server" ? json(500, {}) : json(200, { items: "oops" })));

    expect(await screen.findByText("Не вдалося завантажити відповіді.")).toBeDefined();
    mode = "contract";
    await user.click(screen.getByRole("button", { name: "Спробувати ще раз" }));

    expect(await screen.findByText("Не вдалося завантажити відповіді.")).toBeDefined();
  });

  test("сесія завершилась — окреме пояснення без повтору", async () => {
    await failing(() => json(401, {}));

    expect(await screen.findByText("Сесія завершилась. Увійди знову, щоб побачити відповіді.")).toBeDefined();
    expect(screen.queryByRole("button", { name: "Спробувати ще раз" })).toBeNull();
  });
});
