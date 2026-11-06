/** «Джерела»: таблиця на широкому екрані, картки на вузькому (один DOM), без горизонтального скролу, touch-цілі від 44 px. */
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { apiCompany, apiFiltered, apiRun, sourceId, sourcesBackend } from "./sourcesBackend";
import { detailsOf, openSources, rowOf, sourceList, sourceNames } from "./sourcesHarness";

const LONG_SLUG = "a-very-long-company-slug-that-must-wrap-instead-of-pushing-the-page-sideways-0123456789";
const COMPANIES = [
  apiCompany(1, { name: "Northstar", slug: "northstar-eng" }),
  apiCompany(2, { name: "Orbit Labs", slug: LONG_SLUG, last_run: apiRun({ error: "timeout" }) }),
  apiCompany(3, { name: "Nova Works", slug: "nova", last_run: null }),
];

describe("широкий екран", () => {
  test("реєстр — таблиця з рядками, без списку карток", async () => {
    await openSources(sourcesBackend({ companies: COMPANIES }), "/sources", "desktop");

    expect((await sourceList()).tagName).toBe("TABLE");
    expect(screen.queryByRole("list", { name: "Список джерел" })).toBeNull();
    expect(screen.getAllByLabelText("Список джерел")).toHaveLength(1);
    expect(screen.queryByText("Імпортовано ·")).toBeNull();
  });
});

describe("вузький екран (375 px)", () => {
  test("реєстр — список карток із тими самими даними, таблиці в DOM нема", async () => {
    await openSources(sourcesBackend({ companies: COMPANIES }), "/sources", "mobile");

    const list = await sourceList();
    expect(list.tagName).toBe("UL");
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.getAllByLabelText("Список джерел")).toHaveLength(1);
    expect(within(list).getAllByRole("listitem")).toHaveLength(3);
    expect(await sourceNames()).toEqual(["Northstar", "Orbit Labs", "Nova Works"]);
  });

  test("картка: назва, платформа, стан, час за Мадридом і «Імпортовано · N»", async () => {
    await openSources(sourcesBackend({ companies: COMPANIES }), "/sources", "mobile");

    const card = within(await rowOf("Northstar"));
    expect(card.getByText("Greenhouse")).toBeDefined();
    expect(card.getByText("Працює")).toBeDefined();
    expect(card.getByText("2026-07-01")).toBeDefined();
    expect(card.getByText("12:05")).toBeDefined();
    expect(card.getByText("Імпортовано ·")).toBeDefined();
    expect(card.getByText("3")).toBeDefined();
    expect(within(await rowOf("Nova Works")).getByText("Ще не було")).toBeDefined();
  });

  test("деталі розгортаються всередині картки", async () => {
    const user = userEvent.setup();
    await openSources(sourcesBackend({ companies: COMPANIES }), "/sources", "mobile");

    await user.click(within(await rowOf("Northstar")).getByRole("button", { name: "Northstar" }));

    const card = within(await rowOf("Northstar"));
    expect(card.getByRole("button", { name: "Northstar" }).getAttribute("aria-expanded")).toBe("true");
    expect(card.getByRole("heading", { level: 2, name: "Northstar" })).toBeDefined();
    expect(card.getByText("Імпортовано", { selector: "dt" })).toBeDefined();
  });

  test("відкрите з адреси джерело розгорнуте і в картці", async () => {
    await openSources(sourcesBackend({ companies: COMPANIES }), `/sources?open=${sourceId(3)}`, "mobile");

    expect(within(await rowOf("Nova Works")).getByText("Це джерело ще не оновлювалось. Статистика з’явиться після першого прогону.")).toBeDefined();
  });

  test("сторінка не ширша за екран: scrollWidth дорівнює clientWidth", async () => {
    const user = userEvent.setup();
    await openSources(sourcesBackend({ companies: COMPANIES, filtered: [apiFiltered(1)] }), "/sources", "mobile");
    await user.click(within(await rowOf("Orbit Labs")).getByRole("button", { name: "Orbit Labs" }));

    const root = document.documentElement;
    expect(root.scrollWidth).toBe(root.clientWidth);
    const main = screen.getByRole("main");
    expect(main.scrollWidth).toBe(main.clientWidth);
  });

  test("довгі слаги й запити переносяться: елементи мають перенесення будь-де й не розпирають рядок", async () => {
    const user = userEvent.setup();
    await openSources(sourcesBackend({ companies: COMPANIES }), "/sources", "mobile");
    await user.click(within(await rowOf("Orbit Labs")).getByRole("button", { name: "Orbit Labs" }));

    const slug = within(await detailsOf("Orbit Labs")).getByText(LONG_SLUG);
    expect(slug.className).toContain("[overflow-wrap:anywhere]");
    const name = within(await rowOf("Orbit Labs")).getByRole("button", { name: "Orbit Labs" });
    expect(name.className).toContain("[overflow-wrap:anywhere]");
    expect((await rowOf("Orbit Labs")).className).toContain("min-w-0");
  });

  test("touch-цілі від 44 px: кожен інтерактивний елемент сторінки має висоту 44 px для грубого вказівника", async () => {
    const user = userEvent.setup();
    await openSources(sourcesBackend({ companies: COMPANIES, filtered: [apiFiltered(1)] }), "/sources", "mobile");
    await user.click(within(await rowOf("Northstar")).getByRole("button", { name: "Northstar" }));

    const main = screen.getByRole("main");
    const targets = Array.from(main.querySelectorAll<HTMLElement>("button, a[href], select, input, summary"));
    expect(targets.length).toBeGreaterThan(10);
    const small = targets.filter((target) => !/pointer-coarse:(min-)?(h|size)-11/.test(target.className)).map((target) => target.outerHTML.slice(0, 80));
    expect(small).toEqual([]);
  });
});
