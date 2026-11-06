/** «Джерела»: вимкнути / увімкнути (PATCH) і видалити (діалог, DELETE). Повідомлення — в `role=status`. */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { detailsOf, openSources, rowOf, sourceNames } from "./sourcesHarness";
import { apiCompany, apiFeed, problem, sourceId, sourcesBackend } from "./sourcesBackend";
import { json } from "./testClient";

const COMPANIES = [
  apiCompany(1, { name: "Northstar", slug: "northstar-eng", platform: "greenhouse" }),
  apiCompany(2, { name: "Cloudline", slug: "cloudline", platform: "ashby", enabled: false }),
  apiCompany(3, { name: "LumaPay", slug: "lumapay", platform: "ashby" }),
];
const location = () => screen.getByTestId("location").textContent;
const result = () => screen.getByRole("status", { name: "Результат" });

async function expand(user: ReturnType<typeof userEvent.setup>, name: string) {
  await user.click(within(await rowOf(name)).getByRole("button", { name }));
  return within(await detailsOf(name));
}

describe("вимкнути й увімкнути", () => {
  test("«Вимкнути» шле PATCH, оновлює стан у списку й повідомляє в role=status", async () => {
    const user = userEvent.setup();
    const backend = sourcesBackend({ companies: COMPANIES });
    await openSources(backend);
    const details = await expand(user, "Northstar");

    await user.click(details.getByRole("button", { name: "Вимкнути" }));

    expect(await within(await rowOf("Northstar")).findByText("Вимкнено")).toBeDefined();
    expect(backend.bodies[`PATCH /api/sources/companies/${sourceId(1)}`]).toEqual([{ enabled: false }]);
    expect(result().textContent).toBe("Northstar вимкнено.");
    expect(within(await detailsOf("Northstar")).getByRole("button", { name: "Увімкнути" })).toBeDefined();
    expect(within(await detailsOf("Northstar")).getByText("Нові прогони пропускають це джерело. Збережена статистика та імпортовані вакансії залишаються.")).toBeDefined();
  });

  test("«Увімкнути» повертає стан «Працює» й повідомляє", async () => {
    const user = userEvent.setup();
    const backend = sourcesBackend({ companies: COMPANIES });
    await openSources(backend);
    const details = await expand(user, "Cloudline");

    await user.click(details.getByRole("button", { name: "Увімкнути" }));

    expect(await within(await rowOf("Cloudline")).findByText("Працює")).toBeDefined();
    expect(backend.bodies[`PATCH /api/sources/companies/${sourceId(2)}`]).toEqual([{ enabled: true }]);
    expect(result().textContent).toBe("Cloudline увімкнено.");
  });

  test("стрічка змінюється за своїм шляхом /feeds", async () => {
    const user = userEvent.setup();
    const backend = sourcesBackend({ feeds: [apiFeed(21)] });
    await openSources(backend, "/sources?tab=feeds");
    const details = await expand(user, "DOU · category=Python&remote");

    await user.click(details.getByRole("button", { name: "Вимкнути" }));

    await screen.findByText("DOU · category=Python&remote вимкнено.");
    expect(backend.bodies[`PATCH /api/sources/feeds/${sourceId(21)}`]).toEqual([{ enabled: false }]);
  });

  test("деталі лишаються розгорнутими після зміни стану", async () => {
    const user = userEvent.setup();
    await openSources(sourcesBackend({ companies: COMPANIES }));
    const details = await expand(user, "Northstar");

    await user.click(details.getByRole("button", { name: "Вимкнути" }));

    await screen.findByText("Northstar вимкнено.");
    expect(within(await rowOf("Northstar")).getByRole("button", { name: "Northstar" }).getAttribute("aria-expanded")).toBe("true");
  });

  test("кнопка неактивна, поки йде запит: два кліки — один PATCH", async () => {
    const user = userEvent.setup();
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const backend = sourcesBackend({ companies: COMPANIES }, { toggle: () => gate.then(() => json(200, { ...COMPANIES[0], enabled: false })) });
    await openSources(backend);
    const details = await expand(user, "Northstar");

    await user.click(details.getByRole("button", { name: "Вимкнути" }));
    const pending = details.getByRole("button", { name: "Вимкнути" }) as HTMLButtonElement;
    expect(pending.disabled).toBe(true);
    await user.click(pending);
    release();

    await screen.findByText("Northstar вимкнено.");
    expect(backend.requests.filter((request) => request.startsWith("PATCH"))).toHaveLength(1);
  });

  test("джерела вже нема (404): список перезавантажується з повідомленням", async () => {
    const user = userEvent.setup();
    const backend = sourcesBackend(
      { companies: COMPANIES },
      {
        toggle: () => {
          backend.companies = backend.companies.filter((company) => company.id !== sourceId(1));
          return problem(404, "not_found", "Не знайдено");
        },
      },
    );
    await openSources(backend);
    const details = await expand(user, "Northstar");

    await user.click(details.getByRole("button", { name: "Вимкнути" }));

    await waitFor(async () => expect(await sourceNames()).toEqual(["Cloudline", "LumaPay"]));
    expect(result().textContent).toBe("Джерела вже немає — список оновлено.");
    expect(screen.getByRole("tab", { name: "Компанії · 2" })).toBeDefined();
  });

  test("збій сервера: стан не змінюється, повідомлення про помилку", async () => {
    const user = userEvent.setup();
    const backend = sourcesBackend({ companies: COMPANIES }, { toggle: () => problem(500, "internal_error", "Внутрішня помилка.") });
    await openSources(backend);
    const details = await expand(user, "Northstar");

    await user.click(details.getByRole("button", { name: "Вимкнути" }));

    await waitFor(() => expect(result().textContent).toBe("Не вдалося змінити джерело. Спробуй ще раз."));
    expect(within(await rowOf("Northstar")).getByText("Працює")).toBeDefined();
    expect((within(await detailsOf("Northstar")).getByRole("button", { name: "Вимкнути" }) as HTMLButtonElement).disabled).toBe(false);
  });

  test("сесія завершилась: повідомлення про вхід", async () => {
    const user = userEvent.setup();
    const backend = sourcesBackend({ companies: COMPANIES }, { toggle: () => problem(401, "not_authenticated", "Потрібен вхід") });
    await openSources(backend);
    const details = await expand(user, "Northstar");

    await user.click(details.getByRole("button", { name: "Вимкнути" }));

    await waitFor(() => expect(result().textContent).toBe("Сесія завершилась. Увійди знову, щоб змінити джерело."));
  });
});

describe("видалити", () => {
  test("«Видалити» питає підтвердження: «Видалити джерело?» з поясненням", async () => {
    const user = userEvent.setup();
    await openSources(sourcesBackend({ companies: COMPANIES }));
    const details = await expand(user, "Northstar");

    await user.click(details.getByRole("button", { name: "Видалити" }));

    const dialog = await screen.findByRole("alertdialog", { name: "Видалити джерело?" });
    expect(within(dialog).getByText("Джерело «Northstar» та його статистику буде видалено. Імпортовані вакансії залишаться.")).toBeDefined();
    expect(within(dialog).getByRole("button", { name: "Так, видалити" })).toBeDefined();
    expect(within(dialog).getByRole("button", { name: "Скасувати" })).toBeDefined();
  });

  test("«Скасувати» нічого не видаляє", async () => {
    const user = userEvent.setup();
    const backend = sourcesBackend({ companies: COMPANIES });
    await openSources(backend);
    const details = await expand(user, "Northstar");
    await user.click(details.getByRole("button", { name: "Видалити" }));

    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Скасувати" }));

    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect(backend.requests.filter((request) => request.startsWith("DELETE"))).toEqual([]);
    expect(await sourceNames()).toEqual(["Northstar", "Cloudline", "LumaPay"]);
  });

  test("«Так, видалити» шле DELETE, прибирає рядок і пояснює, що вакансії залишились", async () => {
    const user = userEvent.setup();
    const backend = sourcesBackend({ companies: COMPANIES });
    await openSources(backend);
    const details = await expand(user, "Northstar");
    await user.click(details.getByRole("button", { name: "Видалити" }));

    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Так, видалити" }));

    await waitFor(async () => expect(await sourceNames()).toEqual(["Cloudline", "LumaPay"]));
    expect(backend.requests).toContain(`DELETE /api/sources/companies/${sourceId(1)}`);
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(result().textContent).toBe("Джерело видалено. Імпортовані вакансії залишились.");
    expect(screen.getByRole("tab", { name: "Компанії · 2" })).toBeDefined();
    await waitFor(() => expect(location()).toBe("/sources"));
  });

  test("стрічка видаляється за шляхом /feeds", async () => {
    const user = userEvent.setup();
    const backend = sourcesBackend({ feeds: [apiFeed(21), apiFeed(22, { source: "djinni", query: "primary_keyword=Python" })] });
    await openSources(backend, "/sources?tab=feeds");
    const details = await expand(user, "DOU · category=Python&remote");
    await user.click(details.getByRole("button", { name: "Видалити" }));

    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByText(/Джерело «DOU · category=Python&remote» та його статистику буде видалено\./)).toBeDefined();
    await user.click(within(dialog).getByRole("button", { name: "Так, видалити" }));

    await waitFor(async () => expect(await sourceNames()).toEqual(["Djinni · primary_keyword=Python"]));
    expect(backend.requests).toContain(`DELETE /api/sources/feeds/${sourceId(21)}`);
  });

  test("джерела вже нема (404): діалог закривається, список перезавантажується з повідомленням", async () => {
    const user = userEvent.setup();
    const backend = sourcesBackend(
      { companies: COMPANIES },
      {
        remove: () => {
          backend.companies = backend.companies.filter((company) => company.id !== sourceId(1));
          return problem(404, "not_found", "Не знайдено");
        },
      },
    );
    await openSources(backend);
    const details = await expand(user, "Northstar");
    await user.click(details.getByRole("button", { name: "Видалити" }));

    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Так, видалити" }));

    await waitFor(async () => expect(await sourceNames()).toEqual(["Cloudline", "LumaPay"]));
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(result().textContent).toBe("Джерела вже немає — список оновлено.");
  });

  test("збій сервера: діалог лишається з повідомленням, джерело на місці", async () => {
    const user = userEvent.setup();
    const backend = sourcesBackend({ companies: COMPANIES }, { remove: () => problem(500, "internal_error", "Внутрішня помилка.") });
    await openSources(backend);
    const details = await expand(user, "Northstar");
    await user.click(details.getByRole("button", { name: "Видалити" }));

    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Так, видалити" }));

    const dialog = await screen.findByRole("alertdialog");
    expect(await within(dialog).findByText("Не вдалося видалити джерело. Спробуй ще раз.")).toBeDefined();
    expect((within(dialog).getByRole("button", { name: "Так, видалити" }) as HTMLButtonElement).disabled).toBe(false);
    await user.click(within(dialog).getByRole("button", { name: "Скасувати" }));
    expect(await sourceNames()).toEqual(["Northstar", "Cloudline", "LumaPay"]);
  });

  test("повторне відкриття діалогу після збою не показує старої помилки", async () => {
    const user = userEvent.setup();
    const backend = sourcesBackend({ companies: COMPANIES }, { remove: () => problem(500, "internal_error", "Внутрішня помилка.") });
    await openSources(backend);
    const details = await expand(user, "Northstar");
    await user.click(details.getByRole("button", { name: "Видалити" }));
    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Так, видалити" }));
    await screen.findByText("Не вдалося видалити джерело. Спробуй ще раз.");
    await user.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "Скасувати" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());

    await user.click(details.getByRole("button", { name: "Видалити" }));

    expect(within(await screen.findByRole("alertdialog")).queryByText("Не вдалося видалити джерело. Спробуй ще раз.")).toBeNull();
  });

  test("сесія завершилась: повідомлення про вхід усередині діалогу", async () => {
    const user = userEvent.setup();
    const backend = sourcesBackend({ companies: COMPANIES }, { remove: () => problem(401, "not_authenticated", "Потрібен вхід") });
    await openSources(backend);
    const details = await expand(user, "Northstar");
    await user.click(details.getByRole("button", { name: "Видалити" }));

    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Так, видалити" }));

    expect(await screen.findByText("Сесія завершилась. Увійди знову, щоб видалити джерело.")).toBeDefined();
  });
});
