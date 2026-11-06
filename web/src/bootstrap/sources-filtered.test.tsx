/** «Уже не проходять фільтр»: банер лише при filtered_out_count > 0, перегляд, вибір, підтвердження, 409. */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { openSources } from "./sourcesHarness";
import { apiCompany, apiFiltered, problem, sourcesBackend, type SourcesBackend } from "./sourcesBackend";
import { json, renderClient } from "./testClient";
import { setViewport } from "./viewport";

const FILTERED = [
  apiFiltered(204, { title: "Junior Backend Engineer", company: "Cedar", reason: "excluded" }),
  apiFiltered(218, { title: "Senior Platform Engineer", company: "Aster", reason: "location" }),
  apiFiltered(225, { title: "Backend Engineer", company: "Helio", reason: "format" }),
];
const location = () => screen.getByTestId("location").textContent;

async function openFiltered(backend: SourcesBackend) {
  setViewport("desktop");
  renderClient("/sources/filtered", backend.fetchFn);
  await screen.findByRole("heading", { level: 1, name: "Уже не проходять фільтр" });
}

const checkbox = (name: RegExp | string) => screen.getByRole("checkbox", { name });
const hideButton = (count: number) => screen.getByRole("button", { name: `Приховати вибрані · ${count}` }) as HTMLButtonElement;
const result = () => screen.getByRole("status", { name: "Результат" });

describe("банер на сторінці джерел", () => {
  test("filtered_out_count = 0 — банера нема", async () => {
    await openSources(sourcesBackend({ companies: [apiCompany(1)] }));

    await screen.findByLabelText("Список джерел");
    expect(screen.queryByRole("region", { name: "Вакансії поза фільтром" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Переглянути" })).toBeNull();
  });

  test("filtered_out_count > 0 — банер із кількістю й посиланням «Переглянути»", async () => {
    await openSources(sourcesBackend({ companies: [apiCompany(1)], filtered: FILTERED }));

    const banner = within(await screen.findByRole("region", { name: "Вакансії поза фільтром" }));
    expect(banner.getByText("3 вакансії вже не проходять фільтр профілю")).toBeDefined();
    expect(banner.getByText("Переглянь причини та вибери, які приховати.")).toBeDefined();
    expect(banner.getByRole("link", { name: "Переглянути" }).getAttribute("href")).toBe("/sources/filtered");
  });

  test("одна вакансія — «1 вакансія вже не проходить фільтр профілю»", async () => {
    await openSources(sourcesBackend({ companies: [apiCompany(1)], filtered: [FILTERED[0] as (typeof FILTERED)[number]] }));

    expect(await screen.findByText("1 вакансія вже не проходить фільтр профілю")).toBeDefined();
  });

  test("«Переглянути» відкриває перегляд", async () => {
    const user = userEvent.setup();
    await openSources(sourcesBackend({ companies: [apiCompany(1)], filtered: FILTERED }));

    await user.click(await screen.findByRole("link", { name: "Переглянути" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Уже не проходять фільтр" })).toBeDefined();
    expect(location()).toBe("/sources/filtered");
  });
});

describe("перегляд", () => {
  test("заголовок, пояснення, документ і «← До джерел»", async () => {
    await openFiltered(sourcesBackend({ filtered: FILTERED }));

    expect(screen.getByText("Лише вакансії з джерел, без аналізу й подачі. Приховані зберігаються в базі.")).toBeDefined();
    expect(document.title).toBe("Уже не проходять фільтр · joboffer");
    expect(screen.getByRole("link", { name: "← До джерел" }).getAttribute("href")).toBe("/sources");
  });

  test("поки вантажиться — статус зі скелетоном", async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    await openFiltered(sourcesBackend({ filtered: FILTERED }, { filtered: () => gate.then(() => json(200, FILTERED)) }));

    expect(screen.getByRole("status", { name: "Завантажуємо вакансії" })).toBeDefined();
    release();
    expect(await screen.findByRole("checkbox", { name: /#204/ })).toBeDefined();
  });

  test("рядок: «#номер · посада», компанія й причина", async () => {
    await openFiltered(sourcesBackend({ filtered: FILTERED }));

    const row = within((await screen.findByRole("checkbox", { name: /#204/ })).closest("li") as HTMLElement);
    expect(row.getByText("#204 · Junior Backend Engineer")).toBeDefined();
    expect(row.getByText("Cedar")).toBeDefined();
    expect(row.getByText("Виключений рівень у назві")).toBeDefined();
  });

  test.each([
    ["title", "Назва не збігається з ціллю профілю"],
    ["excluded", "Виключений рівень у назві"],
    ["format", "Формат роботи не відповідає профілю"],
    ["location", "Локація не відповідає профілю"],
  ])("причина %s → «%s»", async (reason, text) => {
    await openFiltered(sourcesBackend({ filtered: [apiFiltered(1, { reason })] }));

    expect(await screen.findByText(text)).toBeDefined();
  });

  test("вакансія без назви чи компанії має запасні підписи", async () => {
    await openFiltered(sourcesBackend({ filtered: [apiFiltered(7, { title: null, company: null })] }));

    expect(await screen.findByText("#7 · (без посади)")).toBeDefined();
    expect(screen.getByText("(без компанії)")).toBeDefined();
  });

  test("порожній перелік — «Список порожній»", async () => {
    await openFiltered(sourcesBackend({ filtered: [] }));

    expect(await screen.findByRole("heading", { name: "Список порожній" })).toBeDefined();
    expect(screen.getByText("Усі вакансії з джерел проходять фільтр профілю.")).toBeDefined();
    expect(screen.queryByRole("button", { name: /Приховати вибрані/ })).toBeNull();
  });

  test("помилка мережі з повтором", async () => {
    const user = userEvent.setup();
    let attempts = 0;
    await openFiltered(
      sourcesBackend(
        { filtered: FILTERED },
        {
          filtered: () => {
            attempts += 1;
            return attempts === 1 ? Promise.reject(new Error("offline")) : undefined;
          },
        },
      ),
    );

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("Не вдалося завантажити вакансії.")).toBeDefined();
    await user.click(within(alert).getByRole("button", { name: "Спробувати ще раз" }));

    expect(await screen.findByRole("checkbox", { name: /#204/ })).toBeDefined();
  });

  test("сесія завершилась: текст без повтору", async () => {
    await openFiltered(sourcesBackend({}, { filtered: () => problem(401, "not_authenticated", "Потрібен вхід") }));

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("Сесія завершилась. Увійди знову, щоб побачити вакансії.")).toBeDefined();
    expect(within(alert).queryByRole("button")).toBeNull();
  });
});

describe("вибір", () => {
  test("спершу нічого не вибрано: «Вибрано: 0», «Приховати вибрані · 0» неактивна", async () => {
    await openFiltered(sourcesBackend({ filtered: FILTERED }));

    await screen.findByRole("checkbox", { name: /#204/ });
    expect(screen.getByText("Вибрано: 0")).toBeDefined();
    expect(hideButton(0).disabled).toBe(true);
    expect(checkbox(/#204/).getAttribute("aria-checked")).toBe("false");
    expect(screen.getByText("Нічого не приховується автоматично.")).toBeDefined();
  });

  test("чекбокси вибирають вакансії; кнопка показує кількість", async () => {
    const user = userEvent.setup();
    await openFiltered(sourcesBackend({ filtered: FILTERED }));

    await user.click(await screen.findByRole("checkbox", { name: /#204/ }));
    await user.click(checkbox(/#225/));

    expect(screen.getByText("Вибрано: 2")).toBeDefined();
    expect(hideButton(2).disabled).toBe(false);
    await user.click(checkbox(/#204/));
    expect(hideButton(1).disabled).toBe(false);
  });

  test("«Вибрати всі · 3» вибирає все, повторне — знімає вибір", async () => {
    const user = userEvent.setup();
    await openFiltered(sourcesBackend({ filtered: FILTERED }));

    await user.click(await screen.findByRole("checkbox", { name: "Вибрати всі · 3" }));
    expect(screen.getByText("Вибрано: 3")).toBeDefined();
    expect(checkbox("Вибрати всі · 3").getAttribute("aria-checked")).toBe("true");
    expect(checkbox(/#218/).getAttribute("aria-checked")).toBe("true");

    await user.click(checkbox("Вибрати всі · 3"));
    expect(screen.getByText("Вибрано: 0")).toBeDefined();
    expect(hideButton(0).disabled).toBe(true);
  });

  test("вибір усіх по одному відмічає «Вибрати всі»", async () => {
    const user = userEvent.setup();
    await openFiltered(sourcesBackend({ filtered: FILTERED }));

    for (const number of ["#204", "#218", "#225"]) {
      await user.click(await screen.findByRole("checkbox", { name: new RegExp(number) }));
    }

    expect(checkbox("Вибрати всі · 3").getAttribute("aria-checked")).toBe("true");
  });

  test("неповний вибір не відмічає «Вибрати всі»; клік по ньому вибирає решту", async () => {
    const user = userEvent.setup();
    await openFiltered(sourcesBackend({ filtered: FILTERED }));
    await user.click(await screen.findByRole("checkbox", { name: /#204/ }));
    expect(checkbox("Вибрати всі · 3").getAttribute("aria-checked")).toBe("false");

    await user.click(checkbox("Вибрати всі · 3"));

    expect(screen.getByText("Вибрано: 3")).toBeDefined();
  });

  test("рядок із чекбоксом — ціль від 44 px для грубого вказівника", async () => {
    await openFiltered(sourcesBackend({ filtered: FILTERED }));

    const label = (await screen.findByRole("checkbox", { name: /#204/ })).closest("li") as HTMLElement;
    expect(label.className).toMatch(/pointer-coarse:min-h-11/);
  });
});

describe("приховування", () => {
  async function selectTwo(user: ReturnType<typeof userEvent.setup>) {
    await user.click(await screen.findByRole("checkbox", { name: /#204/ }));
    await user.click(checkbox(/#218/));
  }

  test("«Приховати вибрані · 2» питає підтвердження «Приховати 2 вакансії?»", async () => {
    const user = userEvent.setup();
    await openFiltered(sourcesBackend({ filtered: FILTERED }));
    await selectTwo(user);

    await user.click(hideButton(2));

    const dialog = await screen.findByRole("alertdialog", { name: "Приховати 2 вакансії?" });
    expect(within(dialog).getByText("Вакансії зникнуть з основного списку з причиною «фільтр профілю». Дані залишаться в базі.")).toBeDefined();
    expect(within(dialog).getByRole("button", { name: "Так, приховати" })).toBeDefined();
  });

  test("«Скасувати» нічого не ховає й лишає вибір", async () => {
    const user = userEvent.setup();
    const backend = sourcesBackend({ filtered: FILTERED });
    await openFiltered(backend);
    await selectTwo(user);
    await user.click(hideButton(2));

    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Скасувати" }));

    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect(backend.dismissed).toEqual([]);
    expect(screen.getByText("Вибрано: 2")).toBeDefined();
  });

  test("підтвердження шле POST з номерами; вакансії зникають, вибір скидається, є повідомлення", async () => {
    const user = userEvent.setup();
    const backend = sourcesBackend({ filtered: FILTERED });
    await openFiltered(backend);
    await selectTwo(user);
    await user.click(hideButton(2));

    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Так, приховати" }));

    await waitFor(() => expect(screen.queryByRole("checkbox", { name: /#204/ })).toBeNull());
    expect(backend.dismissed).toEqual([[204, 218]]);
    expect(screen.queryByRole("checkbox", { name: /#218/ })).toBeNull();
    expect(checkbox(/#225/)).toBeDefined();
    expect(screen.getByText("Вибрано: 0")).toBeDefined();
    expect(hideButton(0).disabled).toBe(true);
    expect(result().textContent).toBe("Вибрані вакансії приховано.");
    expect(screen.getByRole("checkbox", { name: "Вибрати всі · 1" })).toBeDefined();
  });

  test("сховано все — «Список порожній»", async () => {
    const user = userEvent.setup();
    await openFiltered(sourcesBackend({ filtered: FILTERED }));
    await user.click(await screen.findByRole("checkbox", { name: "Вибрати всі · 3" }));
    await user.click(hideButton(3));

    await user.click(within(await screen.findByRole("alertdialog", { name: "Приховати 3 вакансії?" })).getByRole("button", { name: "Так, приховати" }));

    expect(await screen.findByRole("heading", { name: "Список порожній" })).toBeDefined();
  });

  test("після приховування лічильник банера на сторінці джерел оновлено", async () => {
    const user = userEvent.setup();
    await openSources(sourcesBackend({ companies: [apiCompany(1)], filtered: FILTERED }));
    await user.click(await screen.findByRole("link", { name: "Переглянути" }));
    await user.click(await screen.findByRole("checkbox", { name: /#204/ }));
    await user.click(hideButton(1));
    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Так, приховати" }));
    await screen.findByText("Вибрані вакансії приховано.");

    await user.click(screen.getByRole("link", { name: "← До джерел" }));

    expect(await screen.findByText("2 вакансії вже не проходять фільтр профілю")).toBeDefined();
  });

  test("сховано все — банер на сторінці джерел зникає", async () => {
    const user = userEvent.setup();
    await openSources(sourcesBackend({ companies: [apiCompany(1)], filtered: [FILTERED[0] as (typeof FILTERED)[number]] }));
    await user.click(await screen.findByRole("link", { name: "Переглянути" }));
    await user.click(await screen.findByRole("checkbox", { name: /#204/ }));
    await user.click(hideButton(1));
    await user.click(within(await screen.findByRole("alertdialog", { name: "Приховати 1 вакансію?" })).getByRole("button", { name: "Так, приховати" }));
    await screen.findByRole("heading", { name: "Список порожній" });

    await user.click(screen.getByRole("link", { name: "← До джерел" }));

    await screen.findByLabelText("Список джерел");
    expect(screen.queryByRole("region", { name: "Вакансії поза фільтром" })).toBeNull();
  });

  test("409: нічого не сховано, список перезавантажено, вибір скинуто, повідомлення", async () => {
    const user = userEvent.setup();
    const backend = sourcesBackend({ filtered: FILTERED });
    await openFiltered(backend);
    await selectTwo(user);
    // Поки користувач вибирав, профіль змінився: #218 уже проходить фільтр.
    backend.filtered = backend.filtered.filter((job) => job.number !== 218);
    await user.click(hideButton(2));

    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Так, приховати" }));

    await waitFor(() => expect(result().textContent).toBe("Список змінився: нічого не приховано. Перевір актуальний список і вибери вакансії знову."));
    expect(backend.dismissed).toEqual([]);
    await waitFor(() => expect(screen.queryByRole("checkbox", { name: /#218/ })).toBeNull());
    expect(checkbox(/#204/).getAttribute("aria-checked")).toBe("false");
    expect(screen.getByText("Вибрано: 0")).toBeDefined();
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  test("збій сервера: повідомлення, вибір лишається", async () => {
    const user = userEvent.setup();
    const backend = sourcesBackend({ filtered: FILTERED }, { dismiss: () => problem(500, "internal_error", "Внутрішня помилка.") });
    await openFiltered(backend);
    await selectTwo(user);
    await user.click(hideButton(2));

    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Так, приховати" }));

    await waitFor(() => expect(result().textContent).toBe("Не вдалося приховати вакансії. Спробуй ще раз."));
    expect(screen.getByText("Вибрано: 2")).toBeDefined();
  });

  test("сесія завершилась: повідомлення про вхід", async () => {
    const user = userEvent.setup();
    const backend = sourcesBackend({ filtered: FILTERED }, { dismiss: () => problem(401, "not_authenticated", "Потрібен вхід") });
    await openFiltered(backend);
    await selectTwo(user);
    await user.click(hideButton(2));

    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Так, приховати" }));

    await waitFor(() => expect(result().textContent).toBe("Сесія завершилась. Увійди знову, щоб приховати вакансії."));
  });

  test("порожній вибір сервер відхиляє «Нема що ховати.», а UI його не шле: кнопка неактивна", async () => {
    const user = userEvent.setup();
    const backend = sourcesBackend({ filtered: FILTERED });
    await openFiltered(backend);
    await screen.findByRole("checkbox", { name: /#204/ });

    await user.click(hideButton(0));

    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(backend.requests.filter((request) => request.endsWith("/dismiss"))).toEqual([]);
  });
});
