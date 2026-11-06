import { describe, expect, test } from "vitest";

import { filterConditions, hasActiveFilters, jobsQuery, jobTitle, madridDay, NO_FILTERS, parseJobNumber, TAB_LABELS, TABS } from "./jobs";

describe("jobsQuery", () => {
  test("таб «Відкриті вакансії» просить етап open, без схованих", () => {
    expect(jobsQuery(NO_FILTERS)).toEqual({
      query: "",
      days: "",
      source: "",
      needsText: false,
      dismissed: false,
      triageVerdict: "",
      workMode: "",
      status: "",
      stage: "open",
      limit: 200,
    });
  });

  test("таб «Потрібен текст» просить лише вакансії без тексту й без етапу", () => {
    expect(jobsQuery({ ...NO_FILTERS, tab: "needs-text" })).toMatchObject({ needsText: true, dismissed: false, stage: "" });
  });

  test("таб «Сховані» просить лише сховані й без етапу", () => {
    expect(jobsQuery({ ...NO_FILTERS, tab: "dismissed" })).toMatchObject({ needsText: false, dismissed: true, stage: "" });
  });

  test("пошук, свіжість і джерело передаються як є", () => {
    expect(jobsQuery({ ...NO_FILTERS, query: "rust", days: "7", source: "manual" })).toMatchObject({
      query: "rust",
      days: "7",
      source: "manual",
    });
  });
});

describe("jobsQuery: вердикт тріажу й формат", () => {
  test("вердикт і формат передаються як є", () => {
    expect(jobsQuery({ ...NO_FILTERS, verdict: "skip", mode: "hybrid" })).toMatchObject({ triageVerdict: "skip", workMode: "hybrid" });
  });
});

describe("hasActiveFilters", () => {
  test("таб не є фільтром", () => {
    expect(hasActiveFilters({ ...NO_FILTERS, tab: "dismissed" })).toBe(false);
  });

  test.each([{ query: "x" }, { days: "7" }, { source: "manual" }, { verdict: "maybe" as const }, { mode: "remote" as const }])("%o звужує список", (patch) => {
    expect(hasActiveFilters({ ...NO_FILTERS, ...patch })).toBe(true);
  });
});

describe("madridDay", () => {
  test.each([
    ["2026-01-15T12:00:00Z", "2026-01-15"],
    ["2026-01-15T23:00:00Z", "2026-01-16"],
    ["2026-07-01T21:59:00Z", "2026-07-01"],
    ["2026-07-01T22:00:00Z", "2026-07-02"],
  ])("%s → %s", (iso, day) => {
    expect(madridDay(iso)).toBe(day);
  });
});

describe("parseJobNumber", () => {
  test.each([
    ["1", 1],
    ["42", 42],
    ["2147483647", 2147483647],
  ])("%s — номер %i", (raw, value) => {
    expect(parseJobNumber(raw)).toBe(value);
  });

  test.each(["", "0", "-1", "01", "1.5", "abc", "1e3", " 1", "+1", "99999999999999999999"])("%j — не номер", (raw) => {
    expect(parseJobNumber(raw)).toBeNull();
  });

  test("без параметра — не номер", () => {
    expect(parseJobNumber(undefined)).toBeNull();
  });
});

describe("jobTitle", () => {
  test("повна назва як є", () => {
    expect(jobTitle({ title: "Senior Backend Engineer" })).toBe("Senior Backend Engineer");
  });

  test("без назви — «Без назви»", () => {
    expect(jobTitle({ title: null })).toBe("Без назви");
  });
});

describe("таби", () => {
  test("п'ять табів у порядку: відкриті, у процесі, подано, потрібен текст, сховані", () => {
    expect(TABS).toEqual(["open", "in-progress", "applied", "needs-text", "dismissed"]);
    expect(TABS.map((tab) => TAB_LABELS[tab])).toEqual(["Відкриті вакансії", "У процесі", "Подано", "Потрібен текст", "Сховані"]);
  });

  test("таб за замовчуванням — «Відкриті вакансії»", () => {
    expect(NO_FILTERS.tab).toBe("open");
  });

  test("таб «У процесі» просить етап in_progress", () => {
    expect(jobsQuery({ ...NO_FILTERS, tab: "in-progress" })).toMatchObject({ stage: "in_progress", status: "", needsText: false, dismissed: false });
  });

  test("таб «Подано» просить етап applied", () => {
    expect(jobsQuery({ ...NO_FILTERS, tab: "applied" })).toMatchObject({ stage: "applied", status: "", needsText: false, dismissed: false });
  });

  test("вибраний статус подачі йде в запит у табі «Подано»", () => {
    expect(jobsQuery({ ...NO_FILTERS, tab: "applied", status: "interview" })).toMatchObject({ stage: "applied", status: "interview" });
  });
});

describe("умови фільтрів", () => {
  test("без умов — порожньо, а пошук умовою не є", () => {
    expect(filterConditions(NO_FILTERS)).toEqual([]);
    expect(filterConditions({ ...NO_FILTERS, query: "rust" })).toEqual([]);
  });

  test("кожна задана умова — з назвою групи й підписом значення", () => {
    expect(filterConditions({ ...NO_FILTERS, days: "7", source: "manual", verdict: "maybe", mode: "remote" })).toEqual([
      { key: "days", group: "Свіжість", value: "За тиждень" },
      { key: "source", group: "Джерело", value: "manual" },
      { key: "verdict", group: "Вердикт тріажу", value: "Можливо" },
      { key: "mode", group: "Формат", value: "Remote" },
    ]);
  });

  test("статус подачі — умова, з підписом статусу", () => {
    expect(filterConditions({ ...NO_FILTERS, tab: "applied", status: "replied" })).toEqual([{ key: "status", group: "Статус подачі", value: "Є відповідь" }]);
  });
});
