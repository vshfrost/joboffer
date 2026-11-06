/** «Оновити зараз»: ліміт ручних запитів, «Запит у черзі» (не «оновлено»), 0 запитів, 429 з Retry-After. */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { openSources, sourceNames } from "./sourcesHarness";
import { apiCompany, apiRefresh, problem, sourcesBackend } from "./sourcesBackend";
import { json } from "./testClient";

const COMPANIES = [apiCompany(1, { name: "Northstar" })];

afterEach(() => {
  vi.restoreAllMocks();
});

function bar() {
  return within(screen.getByRole("region", { name: "Оновлення джерел" }));
}

describe("до запиту", () => {
  test("остання спроба за Мадридом, «2/2 ручних запитів за 30 хв» і активна кнопка", async () => {
    await openSources(sourcesBackend({ companies: COMPANIES }));

    expect(await screen.findByText("Остання спроба оновлення: 2026-07-01 · 12:05 (Мадрид)")).toBeDefined();
    expect(bar().getByText("2/2 ручних запитів за 30 хв")).toBeDefined();
    expect((bar().getByRole("button", { name: "Оновити зараз" }) as HTMLButtonElement).disabled).toBe(false);
    expect(bar().queryByText(/Наступний запит/)).toBeNull();
  });

  test("прогонів ще не було (last_run_at = null) — «Оновлень ще не було»", async () => {
    await openSources(sourcesBackend({ companies: COMPANIES, refresh: apiRefresh({ last_run_at: null }) }));

    expect(await screen.findByText("Оновлень ще не було")).toBeDefined();
  });

  test("ліміт береться з відповіді сервера, а не з коду", async () => {
    await openSources(sourcesBackend({ companies: COMPANIES, refresh: apiRefresh({ limit: 5, remaining: 3 }) }));

    expect(await bar().findByText("3/5 ручних запитів за 30 хв")).toBeDefined();
  });
});

describe("запит", () => {
  test("POST /refresh: «Запит у черзі», а не «оновлено»; лічильник зменшується, список не перезавантажується", async () => {
    const user = userEvent.setup();
    const backend = sourcesBackend({ companies: COMPANIES });
    await openSources(backend);
    await sourceNames();

    await user.click(bar().getByRole("button", { name: "Оновити зараз" }));

    await bar().findByText("Запит у черзі · очікує серверного прогону");
    const queued = bar().getByRole("button", { name: "Запит у черзі" }) as HTMLButtonElement;
    expect(queued.disabled).toBe(true);
    expect(bar().getByText("1/2 ручних запитів за 30 хв")).toBeDefined();
    expect(screen.queryByText(/оновлено/i)).toBeNull();
    expect(backend.refreshRequests).toBe(1);
    expect(backend.requests.filter((request) => request === "GET /api/sources")).toHaveLength(1);
  });

  test("останній запит: «0/2…» і «Наступний запит: … (Мадрид)» за next_at сервера", async () => {
    const user = userEvent.setup();
    await openSources(sourcesBackend({ companies: COMPANIES, refresh: apiRefresh({ remaining: 1 }) }));

    await user.click(await bar().findByRole("button", { name: "Оновити зараз" }));

    expect(await bar().findByText("0/2 ручних запитів за 30 хв")).toBeDefined();
    expect(bar().getByText("Наступний запит: 2026-07-01 · 12:30 (Мадрид)")).toBeDefined();
  });

  test("два швидкі кліки — один запит", async () => {
    const user = userEvent.setup();
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const backend = sourcesBackend({ companies: COMPANIES }, { refresh: () => gate.then(() => json(202, apiRefresh({ remaining: 1 }))) });
    await openSources(backend);

    const button = await bar().findByRole("button", { name: "Оновити зараз" });
    await user.click(button);
    expect((bar().getByRole("button", { name: "Оновити зараз" }) as HTMLButtonElement).disabled).toBe(true);
    await user.click(bar().getByRole("button", { name: "Оновити зараз" }));
    release();

    await bar().findByRole("button", { name: "Запит у черзі" });
    expect(backend.refreshRequests).toBe(1);
  });

  test("збій сервера: повідомлення, кнопка знову активна", async () => {
    const user = userEvent.setup();
    await openSources(sourcesBackend({ companies: COMPANIES }, { refresh: () => problem(500, "internal_error", "Внутрішня помилка.") }));

    await user.click(await bar().findByRole("button", { name: "Оновити зараз" }));

    await waitFor(() => expect(screen.getByRole("status", { name: "Результат" }).textContent).toBe("Не вдалося запросити оновлення. Спробуй ще раз."));
    expect((bar().getByRole("button", { name: "Оновити зараз" }) as HTMLButtonElement).disabled).toBe(false);
  });

  test("сесія завершилась: повідомлення про вхід", async () => {
    const user = userEvent.setup();
    await openSources(sourcesBackend({ companies: COMPANIES }, { refresh: () => problem(401, "not_authenticated", "Потрібен вхід") }));

    await user.click(await bar().findByRole("button", { name: "Оновити зараз" }));

    await waitFor(() => expect(screen.getByRole("status", { name: "Результат" }).textContent).toBe("Сесія завершилась. Увійди знову, щоб оновити джерела."));
  });
});

describe("ліміт вичерпано", () => {
  test("0 запитів із сервера: кнопка неактивна й «Наступний запит: … (Мадрид)»", async () => {
    const user = userEvent.setup();
    const backend = sourcesBackend({ companies: COMPANIES, refresh: apiRefresh({ remaining: 0, next_at: "2026-07-01T10:30:00Z" }) });
    await openSources(backend);

    const button = (await bar().findByRole("button", { name: "Оновити зараз" })) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(bar().getByText("0/2 ручних запитів за 30 хв")).toBeDefined();
    expect(bar().getByText("Наступний запит: 2026-07-01 · 12:30 (Мадрид)")).toBeDefined();
    await user.click(button);
    expect(backend.refreshRequests).toBe(0);
  });

  test("429 із Retry-After: кнопка неактивна, «Наступний запит» = зараз + Retry-After за Мадридом, текст сервера", async () => {
    vi.spyOn(Date, "now").mockReturnValue(Date.parse("2026-07-01T10:00:00Z"));
    const user = userEvent.setup();
    const backend = sourcesBackend({ companies: COMPANIES }, { refresh: () => problem(429, "refresh_limit", "Оновлення джерел уже запитано 2 рази за 30 хв — наступне о 12:25 (Мадрид).", [], { "Retry-After": "1500" }) });
    await openSources(backend);

    await user.click(await bar().findByRole("button", { name: "Оновити зараз" }));

    expect(await bar().findByText("Наступний запит: 2026-07-01 · 12:25 (Мадрид)")).toBeDefined();
    expect(bar().getByText("0/2 ручних запитів за 30 хв")).toBeDefined();
    expect((bar().getByRole("button", { name: "Оновити зараз" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByRole("status", { name: "Результат" }).textContent).toBe("Оновлення джерел уже запитано 2 рази за 30 хв — наступне о 12:25 (Мадрид).");
  });

  test("429 без Retry-After: кнопка неактивна й текст сервера, без «Наступний запит»", async () => {
    const user = userEvent.setup();
    const backend = sourcesBackend({ companies: COMPANIES }, { refresh: () => problem(429, "refresh_limit", "Забагато запитів.") });
    await openSources(backend);

    await user.click(await bar().findByRole("button", { name: "Оновити зараз" }));

    await waitFor(() => expect(screen.getByRole("status", { name: "Результат" }).textContent).toBe("Забагато запитів."));
    expect((bar().getByRole("button", { name: "Оновити зараз" }) as HTMLButtonElement).disabled).toBe(true);
    expect(bar().queryByText(/Наступний запит/)).toBeNull();
  });
});
