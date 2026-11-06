import { describe, expect, test } from "vitest";

import {
  bannerTitle,
  FAILURE_CODES,
  FAILURE_TEXT,
  feedName,
  FILTERED_REASON_TEXT,
  FILTERED_REASONS,
  hasSourceFilters,
  hideTitle,
  importedText,
  nextRequestAt,
  parseSourcesQuery,
  PLATFORM_LABELS,
  platformLabel,
  plural,
  quotaText,
  sourceCountText,
  sourceState,
  sourcesQueryParams,
  STATE_FILTER_LABELS,
  STATE_LABELS,
  stampText,
  visibleSources,
  type LastRun,
  type Source,
  type SourcesQuery,
} from "./sources";

const RUN: LastRun = { ranAt: "2026-07-01T10:05:00Z", found: 160, imported: 3, filtered: 146, duplicate: 10, completed: 1, error: null };

function source(overrides: Partial<Source> = {}): Source {
  return { kind: "company", id: "id-1", platform: "greenhouse", name: "Northstar", key: "northstar-eng", enabled: true, lastRun: RUN, ...overrides };
}

const NO_FILTERS: SourcesQuery = { tab: "companies", q: "", status: "", open: "" };

describe("запит із адреси сторінки", () => {
  test("порожня адреса — вкладка «Компанії» без пошуку й фільтра", () => {
    expect(parseSourcesQuery(new URLSearchParams(""))).toEqual(NO_FILTERS);
  });

  test("усе розпізнане береться як є", () => {
    const params = new URLSearchParams("tab=feeds&q=dou&status=error&open=abc");

    expect(parseSourcesQuery(params)).toEqual({ tab: "feeds", q: "dou", status: "error", open: "abc" });
  });

  test("нерозпізнана вкладка й стан стають значеннями за замовчуванням, пошук обрізається", () => {
    const params = new URLSearchParams({ tab: "other", status: "paused", q: "  acme  " });

    expect(parseSourcesQuery(params)).toEqual({ tab: "companies", q: "acme", status: "", open: "" });
  });

  test.each(["enabled", "error", "disabled"] as const)("стан %s розпізнається", (status) => {
    expect(parseSourcesQuery(new URLSearchParams({ status })).status).toBe(status);
  });

  test("у адресу пишеться лише те, що відрізняється від значень за замовчуванням", () => {
    expect(sourcesQueryParams(NO_FILTERS).toString()).toBe("");
    expect(sourcesQueryParams({ tab: "feeds", q: "acme corp", status: "disabled", open: "abc" }).toString()).toBe(
      "tab=feeds&q=acme+corp&status=disabled&open=abc",
    );
  });

  test("«Скинути фільтри» є, коли задано пошук або стан", () => {
    expect(hasSourceFilters(NO_FILTERS)).toBe(false);
    expect(hasSourceFilters({ ...NO_FILTERS, tab: "feeds", open: "abc" })).toBe(false);
    expect(hasSourceFilters({ ...NO_FILTERS, q: "acme" })).toBe(true);
    expect(hasSourceFilters({ ...NO_FILTERS, status: "error" })).toBe(true);
  });
});

describe("стан джерела", () => {
  test("успішний прогін — «Працює»", () => {
    expect(sourceState(source())).toBe("ok");
  });

  test("прогону ще не було — «Ще не оновлювалось»", () => {
    expect(sourceState(source({ lastRun: null }))).toBe("pending");
  });

  test("прогін із кодом помилки — «Помилка»", () => {
    expect(sourceState(source({ lastRun: { ...RUN, error: "timeout" } }))).toBe("error");
  });

  test("вимкнене джерело — «Вимкнено», навіть із помилкою чи без прогону", () => {
    expect(sourceState(source({ enabled: false }))).toBe("disabled");
    expect(sourceState(source({ enabled: false, lastRun: { ...RUN, error: "timeout" } }))).toBe("disabled");
    expect(sourceState(source({ enabled: false, lastRun: null }))).toBe("disabled");
  });

  test("назви станів", () => {
    expect(STATE_LABELS).toEqual({ ok: "Працює", error: "Помилка", pending: "Ще не оновлювалось", disabled: "Вимкнено" });
  });

  test("назви фільтра стану", () => {
    expect(STATE_FILTER_LABELS).toEqual({ "": "Усі", enabled: "Увімкнені", error: "З помилками", disabled: "Вимкнені" });
  });
});

describe("тексти", () => {
  test("кожен із 7 кодів помилки має людський текст", () => {
    expect(FAILURE_CODES).toHaveLength(7);
    expect(FAILURE_TEXT).toEqual({
      timeout: "Перевищено час очікування",
      not_found: "Джерело не знайдено на платформі",
      rate_limited: "Платформа обмежила кількість запитів",
      unavailable: "Платформа тимчасово недоступна",
      rejected: "Платформа відхилила запит",
      invalid: "Відповідь платформи не вдалося розібрати",
      unsupported: "Цей вид джерела поки не підтримується",
    });
  });

  test("кожна з 4 причин «не проходить фільтр» має текст", () => {
    expect(FILTERED_REASONS).toEqual(["title", "excluded", "format", "location"]);
    expect(FILTERED_REASON_TEXT).toEqual({
      title: "Назва не збігається з ціллю профілю",
      excluded: "Виключений рівень у назві",
      format: "Формат роботи не відповідає профілю",
      location: "Локація не відповідає профілю",
    });
  });

  test("платформи й стрічки мають назви", () => {
    expect(PLATFORM_LABELS).toEqual({ greenhouse: "Greenhouse", ashby: "Ashby", lever: "Lever", dou: "DOU", djinni: "Djinni" });
    expect(platformLabel("ashby")).toBe("Ashby");
    expect(platformLabel("unknown")).toBe("unknown");
  });

  test("стрічка не має назви на сервері: вона складається з джерела й параметрів", () => {
    expect(feedName("dou", "category=Python&remote")).toBe("DOU · category=Python&remote");
    expect(feedName("djinni", "primary_keyword=Python")).toBe("Djinni · primary_keyword=Python");
  });

  test("імпортовано — число останнього прогону; без прогону й після помилки — «—»", () => {
    expect(importedText(source())).toBe("3");
    expect(importedText(source({ lastRun: { ...RUN, imported: 0 } }))).toBe("0");
    expect(importedText(source({ lastRun: null }))).toBe("—");
    expect(importedText(source({ lastRun: { ...RUN, error: "timeout" } }))).toBe("—");
  });

  test("момент — день і час за Мадридом (літній і зимовий)", () => {
    expect(stampText("2026-07-01T10:05:00Z")).toBe("2026-07-01 · 12:05");
    expect(stampText("2026-12-01T10:05:00Z")).toBe("2026-12-01 · 11:05");
  });

  test("ліміт «Оновити зараз»", () => {
    expect(quotaText({ limit: 2, remaining: 1, nextAt: null, lastRunAt: null })).toBe("1/2 ручних запитів за 30 хв");
    expect(quotaText({ limit: 2, remaining: 0, nextAt: "2026-07-01T10:30:00Z", lastRunAt: null })).toBe("0/2 ручних запитів за 30 хв");
  });
});

describe("множина", () => {
  const FORMS = ["вакансія", "вакансії", "вакансій"] as const;

  test.each([
    [0, "вакансій"],
    [1, "вакансія"],
    [2, "вакансії"],
    [4, "вакансії"],
    [5, "вакансій"],
    [11, "вакансій"],
    [12, "вакансій"],
    [14, "вакансій"],
    [21, "вакансія"],
    [22, "вакансії"],
    [25, "вакансій"],
  ])("%i → %s", (count, expected) => {
    expect(plural(count, FORMS)).toBe(expected);
  });

  test("підпис під таблицею", () => {
    expect(sourceCountText("companies", 1)).toBe("1 компанія");
    expect(sourceCountText("companies", 3)).toBe("3 компанії");
    expect(sourceCountText("companies", 5)).toBe("5 компаній");
    expect(sourceCountText("feeds", 1)).toBe("1 стрічка");
    expect(sourceCountText("feeds", 2)).toBe("2 стрічки");
    expect(sourceCountText("feeds", 7)).toBe("7 стрічок");
  });

  test("банер «Уже не проходять фільтр»", () => {
    expect(bannerTitle(1)).toBe("1 вакансія вже не проходить фільтр профілю");
    expect(bannerTitle(3)).toBe("3 вакансії вже не проходять фільтр профілю");
    expect(bannerTitle(5)).toBe("5 вакансій вже не проходять фільтр профілю");
  });

  test("заголовок підтвердження приховування", () => {
    expect(hideTitle(1)).toBe("Приховати 1 вакансію?");
    expect(hideTitle(2)).toBe("Приховати 2 вакансії?");
    expect(hideTitle(5)).toBe("Приховати 5 вакансій?");
  });
});

describe("Retry-After", () => {
  test("наступний запит — поточний момент плюс секунди з Retry-After", () => {
    expect(nextRequestAt(Date.parse("2026-07-01T10:00:00Z"), 1500)).toBe("2026-07-01T10:25:00.000Z");
  });
});

describe("пошук і фільтр стану", () => {
  const companies = [
    source({ id: "a", name: "Northstar", key: "northstar-eng", platform: "greenhouse" }),
    source({ id: "b", name: "LumaPay", key: "lumapay", platform: "ashby", enabled: false }),
    source({ id: "c", name: "Orbit Labs", key: "orbit", platform: "lever", lastRun: { ...RUN, error: "timeout" } }),
  ];
  const ids = (found: Source[]) => found.map((item) => item.id);

  test("без пошуку й фільтра — усі джерела у своєму порядку", () => {
    expect(ids(visibleSources(companies, NO_FILTERS))).toEqual(["a", "b", "c"]);
  });

  test.each([
    ["north", ["a"]],
    ["LUMAPAY", ["b"]],
    ["orbit-labs", []],
    ["orbit", ["c"]],
    ["lever", ["c"]],
    ["Ashby", ["b"]],
    ["greenhouse", ["a"]],
  ])("пошук «%s» шукає за назвою, слагом і платформою без урахування регістру", (q, expected) => {
    expect(ids(visibleSources(companies, { ...NO_FILTERS, q }))).toEqual(expected);
  });

  test("пошук знаходить стрічку за параметрами запиту", () => {
    const feeds = [source({ kind: "feed", id: "f", platform: "dou", name: "DOU · category=Python&remote", key: "category=Python&remote" })];

    expect(ids(visibleSources(feeds, { ...NO_FILTERS, tab: "feeds", q: "remote" }))).toEqual(["f"]);
    expect(ids(visibleSources(feeds, { ...NO_FILTERS, tab: "feeds", q: "djinni" }))).toEqual([]);
  });

  test.each([
    ["enabled", ["a", "c"]],
    ["disabled", ["b"]],
    ["error", ["c"]],
  ] as const)("фільтр «%s»", (status, expected) => {
    expect(ids(visibleSources(companies, { ...NO_FILTERS, status }))).toEqual(expected);
  });

  test("пошук і фільтр діють разом", () => {
    expect(ids(visibleSources(companies, { ...NO_FILTERS, q: "o", status: "enabled" }))).toEqual(["a", "c"]);
    expect(ids(visibleSources(companies, { ...NO_FILTERS, q: "luma", status: "enabled" }))).toEqual([]);
  });
});
