/** «Джерела»: деталі під рядком — лічильники останнього прогону, коди помилок, джерело без прогону. */
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { detailsOf, openSources, rowOf, sourceButtons } from "./sourcesHarness";
import { apiCompany, apiFeed, apiRun, sourceId, sourcesBackend } from "./sourcesBackend";
import { FAILURE_CODES, FAILURE_TEXT } from "../domain/sources";

const COMPANIES = [
  apiCompany(1, { name: "Northstar", slug: "northstar-eng", platform: "greenhouse" }),
  apiCompany(2, { name: "Orbit Labs", slug: "orbit", platform: "lever", last_run: apiRun({ error: "timeout", imported: 0 }) }),
  apiCompany(3, { name: "Cloudline", slug: "cloudline", platform: "ashby", enabled: false }),
  apiCompany(4, { name: "Nova Works", slug: "nova", platform: "lever", last_run: null }),
];
const location = () => screen.getByTestId("location").textContent;

describe("розгортання", () => {
  test("натискання назви розгортає деталі під рядком (aria-expanded), повторне — згортає", async () => {
    const user = userEvent.setup();
    await openSources(sourcesBackend({ companies: COMPANIES }));
    const toggle = within(await rowOf("Northstar")).getByRole("button", { name: "Northstar" });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");

    await user.click(toggle);

    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    const row = await rowOf("Northstar");
    expect(within(row.nextElementSibling as HTMLElement).getByRole("heading", { level: 2, name: "Northstar" })).toBeDefined();
    await user.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("heading", { level: 2, name: "Northstar" })).toBeNull();
  });

  test("відкрите джерело живе в адресі; одночасно розгорнуте лише одне", async () => {
    const user = userEvent.setup();
    await openSources(sourcesBackend({ companies: COMPANIES }));

    await user.click(within(await rowOf("Northstar")).getByRole("button", { name: "Northstar" }));
    expect(location()).toBe(`/sources?open=${sourceId(1)}`);
    await user.click(within(await rowOf("Orbit Labs")).getByRole("button", { name: "Orbit Labs" }));

    expect(location()).toBe(`/sources?open=${sourceId(2)}`);
    const expanded = (await sourceButtons()).filter((button) => button.getAttribute("aria-expanded") === "true");
    expect(expanded.map((button) => button.textContent)).toEqual(["Orbit Labs"]);
    await user.click(within(await rowOf("Orbit Labs")).getByRole("button", { name: "Orbit Labs" }));
    expect(location()).toBe("/sources");
  });

  test("кнопка вказує на свої деталі через aria-controls", async () => {
    const user = userEvent.setup();
    await openSources(sourcesBackend({ companies: COMPANIES }));

    await user.click(within(await rowOf("Northstar")).getByRole("button", { name: "Northstar" }));

    const details = await detailsOf("Northstar");
    expect(within(details).getByRole("heading", { level: 2, name: "Northstar" })).toBeDefined();
  });

  test("джерело з адреси розгорнуте одразу", async () => {
    await openSources(sourcesBackend({ companies: COMPANIES }), `/sources?open=${sourceId(2)}`);

    expect(within(await rowOf("Orbit Labs")).getByRole("button", { name: "Orbit Labs" }).getAttribute("aria-expanded")).toBe("true");
  });

  test("чужий, зниклий або з іншої вкладки id у адресі нічого не розгортає", async () => {
    await openSources(sourcesBackend({ companies: COMPANIES, feeds: [apiFeed(21)] }), `/sources?tab=feeds&open=${sourceId(1)}`);
    expect((await sourceButtons()).filter((button) => button.getAttribute("aria-expanded") === "true")).toEqual([]);
  });

  test("id, якого нема в списку, нічого не розгортає", async () => {
    await openSources(sourcesBackend({ companies: COMPANIES }), "/sources?open=nope");

    expect((await sourceButtons()).filter((button) => button.getAttribute("aria-expanded") === "true")).toEqual([]);
  });
});

describe("деталі джерела з прогоном", () => {
  async function expand(name: string, backend = sourcesBackend({ companies: COMPANIES, feeds: [apiFeed(21)] })) {
    const user = userEvent.setup();
    await openSources(backend);
    await user.click(within(await rowOf(name)).getByRole("button", { name }));
    return within(await detailsOf(name));
  }

  test("заголовок, вид джерела, стан і слаг", async () => {
    const details = await expand("Northstar");

    expect(details.getByText("Greenhouse · Сторінка компанії")).toBeDefined();
    expect(details.getByText("Працює")).toBeDefined();
    expect(details.getByText("northstar-eng")).toBeDefined();
  });

  test("стрічка: «DOU · RSS-стрічка» й параметри запиту", async () => {
    const user = userEvent.setup();
    await openSources(sourcesBackend({ feeds: [apiFeed(21)] }), "/sources?tab=feeds");
    await user.click(within(await rowOf("DOU · category=Python&remote")).getByRole("button", { name: "DOU · category=Python&remote" }));

    const details = within(await detailsOf("DOU · category=Python&remote"));
    expect(details.getByText("DOU · RSS-стрічка")).toBeDefined();
    expect(details.getByText("category=Python&remote", { selector: "code" })).toBeDefined();
  });

  test("час останнього прогону за Мадридом", async () => {
    const details = await expand("Northstar");

    expect(details.getByText("Останній прогін: 2026-07-01 · 12:05 (Мадрид)")).toBeDefined();
  });

  test("5 лічильників: знайдено, імпортовано, відсіяно, дублі, дописано текст", async () => {
    const details = await expand("Northstar");

    const stats = details.getByText("Знайдено", { selector: "dt" }).closest("dl") as HTMLElement;
    const pairs = Array.from(stats.querySelectorAll("dt")).map((term) => [term.textContent, term.nextElementSibling?.textContent]);
    expect(pairs).toEqual([
      ["Знайдено", "160"],
      ["Імпортовано", "3"],
      ["Відсіяно", "146"],
      ["Дублі", "10"],
      ["Дописано текст", "1"],
    ]);
  });

  test("цифри — `.sr-count` у реєстрі й `.sr-stats dd` у деталях (колір --jo-metric задає тема)", async () => {
    const details = await expand("Northstar");

    const list = await screen.findByLabelText("Список джерел");
    const counts = Array.from(list.querySelectorAll(".sr-count")).map((count) => count.textContent);
    expect(counts).toEqual(["3", "—", "3", "—"]);
    expect(details.getByText("Знайдено", { selector: "dt" }).closest("dl")?.classList.contains("sr-stats")).toBe(true);
    expect(list.querySelectorAll(".sr-stats dd")).toHaveLength(5);
  });

  test("«Як рахуються результати» — пояснення під кнопками", async () => {
    const details = await expand("Northstar");

    const disclosure = details.getByText("Як рахуються результати").closest("details") as HTMLElement;
    expect(within(disclosure).getByText(/Імпортовано — нові вакансії, що пройшли фільтри профілю\./)).toBeDefined();
    expect(within(disclosure).getByText(/Ці числа стосуються лише останнього прогону\./)).toBeDefined();
  });

  test("дії: «Вимкнути» й «Видалити» для ввімкненого, «Увімкнути» для вимкненого", async () => {
    const enabled = await expand("Northstar");
    expect(enabled.getByRole("button", { name: "Вимкнути" })).toBeDefined();
    expect(enabled.getByRole("button", { name: "Видалити" })).toBeDefined();
  });
});

describe("вимкнене джерело", () => {
  test("«Увімкнути», пояснення й збережена статистика", async () => {
    const user = userEvent.setup();
    await openSources(sourcesBackend({ companies: COMPANIES }));
    await user.click(within(await rowOf("Cloudline")).getByRole("button", { name: "Cloudline" }));

    const details = within(await detailsOf("Cloudline"));
    expect(details.getByText("Вимкнено")).toBeDefined();
    expect(details.getByRole("button", { name: "Увімкнути" })).toBeDefined();
    expect(details.queryByRole("button", { name: "Вимкнути" })).toBeNull();
    expect(details.getByText("Нові прогони пропускають це джерело. Збережена статистика та імпортовані вакансії залишаються.")).toBeDefined();
    expect(details.getByText("Знайдено", { selector: "dt" })).toBeDefined();
  });
});

describe("помилка прогону", () => {
  test.each(FAILURE_CODES)("код %s → людський текст і час спроби, без лічильників", async (code) => {
    const user = userEvent.setup();
    const backend = sourcesBackend({ companies: [apiCompany(1, { name: "Orbit Labs", last_run: apiRun({ error: code }) })] });
    await openSources(backend);
    await user.click(within(await rowOf("Orbit Labs")).getByRole("button", { name: "Orbit Labs" }));

    const details = within(await detailsOf("Orbit Labs"));
    expect(details.getByText(FAILURE_TEXT[code])).toBeDefined();
    expect(details.getByText(/Остання спроба: 2026-07-01 · 12:05 \(Мадрид\)\. Інші джерела оновилися\. Наступний загальний прогін повторить спробу\./)).toBeDefined();
    expect(details.getByText("Помилка")).toBeDefined();
    expect(details.queryByText("Знайдено", { selector: "dt" })).toBeNull();
  });

  test("timeout — «Перевищено час очікування»", async () => {
    const user = userEvent.setup();
    await openSources(sourcesBackend({ companies: COMPANIES }));
    await user.click(within(await rowOf("Orbit Labs")).getByRole("button", { name: "Orbit Labs" }));

    expect(within(await detailsOf("Orbit Labs")).getByText("Перевищено час очікування")).toBeDefined();
  });
});

describe("джерело без прогону", () => {
  test("`last_run: null` → «Ще не оновлювалось» і пояснення замість статистики", async () => {
    const user = userEvent.setup();
    await openSources(sourcesBackend({ companies: COMPANIES }));
    await user.click(within(await rowOf("Nova Works")).getByRole("button", { name: "Nova Works" }));

    const details = within(await detailsOf("Nova Works"));
    expect(details.getByText("Ще не оновлювалось")).toBeDefined();
    expect(details.getByText("Це джерело ще не оновлювалось. Статистика з’явиться після першого прогону.")).toBeDefined();
    expect(details.queryByText("Знайдено", { selector: "dt" })).toBeNull();
    expect(details.queryByText(/Останній прогін/)).toBeNull();
  });
});
