import { describe, expect, test } from "vitest";

import { countFacts, FACT_KINDS, filterFacts, hasActiveFilters, isDraftChanged, KIND_LABELS, NO_FILTERS, pendingSummary, SOURCE_LABELS, SOURCES, type Fact } from "./facts";

function fact(id: number, kind: Fact["kind"], text: string, confirmed = false, source: Fact["source"] = "cv", jobId: number | null = null): Fact {
  return { id, kind, text, confirmed, source, jobId, createdAt: "2026-10-20T10:00:00Z", updatedAt: "2026-10-20T10:00:00Z" };
}

const FACTS: Fact[] = [
  fact(3, "experience", "Backend Lead в Acme, 2021–2024", true),
  fact(2, "achievement", "Скоротив p95 затримку на 40%"),
  fact(1, "skill", "Python 3.14", true),
  fact(4, "skill", "Postgres"),
  fact(12, "language", "Англійська — B2"),
];

const ids = (facts: Fact[]) => facts.map((item) => item.id);

describe("категорії", () => {
  test("йдуть у порядку секцій сервера й мають українські назви", () => {
    expect(FACT_KINDS).toEqual(["experience", "achievement", "project", "skill", "education", "language"]);
    expect(FACT_KINDS.map((kind) => KIND_LABELS[kind])).toEqual(["Досвід", "Досягнення", "Проєкти", "Скіли", "Освіта", "Мови"]);
  });
});

describe("джерела фактів", () => {
  test("cv, chat, manual мають підписи «з CV», «з чату», «вручну»", () => {
    expect(SOURCES).toEqual(["cv", "chat", "manual"]);
    expect(SOURCES.map((source) => SOURCE_LABELS[source])).toEqual(["з CV", "з чату", "вручну"]);
  });
});

describe("фільтр за джерелом", () => {
  const MIXED: Fact[] = [fact(1, "skill", "A"), fact(2, "skill", "B", true, "chat", 5), fact(3, "skill", "C", true, "manual"), fact(4, "skill", "D", false, "chat", 6)];

  test("обране джерело лишає лише його факти, порядок зберігається", () => {
    expect(ids(filterFacts(MIXED, { ...NO_FILTERS, source: "chat" }))).toEqual([2, 4]);
    expect(ids(filterFacts(MIXED, { ...NO_FILTERS, source: "manual" }))).toEqual([3]);
    expect(ids(filterFacts(MIXED, { ...NO_FILTERS, source: "cv" }))).toEqual([1]);
  });

  test("без джерела — усі; діє разом зі статусом; рахується активним фільтром", () => {
    expect(ids(filterFacts(MIXED, NO_FILTERS))).toEqual([1, 2, 3, 4]);
    expect(ids(filterFacts(MIXED, { ...NO_FILTERS, source: "chat", status: "pending" }))).toEqual([4]);
    expect(hasActiveFilters({ ...NO_FILTERS, source: "chat" })).toBe(true);
  });
});

describe("filterFacts", () => {
  test("без фільтрів — усі факти в тому ж порядку", () => {
    expect(ids(filterFacts(FACTS, NO_FILTERS))).toEqual([3, 2, 1, 4, 12]);
  });

  test("категорія лишає лише свої факти", () => {
    expect(ids(filterFacts(FACTS, { ...NO_FILTERS, kind: "skill" }))).toEqual([1, 4]);
  });

  test("статус «Потребують перевірки» і «Підтверджені»", () => {
    expect(ids(filterFacts(FACTS, { ...NO_FILTERS, status: "pending" }))).toEqual([2, 4, 12]);
    expect(ids(filterFacts(FACTS, { ...NO_FILTERS, status: "confirmed" }))).toEqual([3, 1]);
  });

  test("пошук за текстом не залежить від регістру й зайвих пробілів", () => {
    expect(ids(filterFacts(FACTS, { ...NO_FILTERS, query: "  PYTHON " }))).toEqual([1]);
    expect(ids(filterFacts(FACTS, { ...NO_FILTERS, query: "acme" }))).toEqual([3]);
  });

  test("пошук за ID: «#12» і «12» знаходять факт 12, а не всі, де є ця цифра", () => {
    expect(ids(filterFacts(FACTS, { ...NO_FILTERS, query: "#12" }))).toEqual([12]);
    expect(ids(filterFacts(FACTS, { ...NO_FILTERS, query: "12" }))).toEqual([12]);
    expect(ids(filterFacts(FACTS, { ...NO_FILTERS, query: "#1" }))).toEqual([1]);
  });

  test("цифри в тексті теж знаходяться", () => {
    expect(ids(filterFacts(FACTS, { ...NO_FILTERS, query: "2021" }))).toEqual([3]);
    expect(ids(filterFacts(FACTS, { ...NO_FILTERS, query: "40%" }))).toEqual([2]);
  });

  test("пошук, статус і категорія діють разом", () => {
    const filters = { query: "post", status: "pending", kind: "skill" } as const;
    expect(ids(filterFacts(FACTS, filters))).toEqual([4]);
    expect(ids(filterFacts(FACTS, { ...filters, status: "confirmed" }))).toEqual([]);
    expect(ids(filterFacts(FACTS, { ...filters, kind: "language" }))).toEqual([]);
  });
});

describe("hasActiveFilters", () => {
  test("порожній пошук із пробілів, «Усі» і всі категорії — не фільтри", () => {
    expect(hasActiveFilters(NO_FILTERS)).toBe(false);
    expect(hasActiveFilters({ ...NO_FILTERS, query: "   " })).toBe(false);
  });

  test("пошук, статус чи категорія — фільтри", () => {
    expect(hasActiveFilters({ ...NO_FILTERS, query: "x" })).toBe(true);
    expect(hasActiveFilters({ ...NO_FILTERS, status: "pending" })).toBe(true);
    expect(hasActiveFilters({ ...NO_FILTERS, kind: "skill" })).toBe(true);
  });
});

describe("countFacts", () => {
  test("рахує всі факти, підтверджені й ті, що чекають, і кожну категорію", () => {
    const counts = countFacts(FACTS);
    expect(counts).toMatchObject({ total: 5, confirmed: 2, pending: 3 });
    expect(counts.kinds).toEqual([
      { kind: "experience", total: 1, pending: 0 },
      { kind: "achievement", total: 1, pending: 1 },
      { kind: "project", total: 0, pending: 0 },
      { kind: "skill", total: 2, pending: 1 },
      { kind: "education", total: 0, pending: 0 },
      { kind: "language", total: 1, pending: 1 },
    ]);
  });

  test("порожня бібліотека — нулі в усіх шести категоріях", () => {
    const counts = countFacts([]);
    expect(counts).toMatchObject({ total: 0, confirmed: 0, pending: 0 });
    expect(counts.kinds).toHaveLength(6);
  });
});

describe("isDraftChanged", () => {
  const original = fact(1, "skill", "Python");

  test("той самий вид і текст (з пробілами по краях) — не змінено", () => {
    expect(isDraftChanged(original, { kind: "skill", text: "  Python " })).toBe(false);
  });

  test("інший текст чи вид — змінено", () => {
    expect(isDraftChanged(original, { kind: "skill", text: "Python 3" })).toBe(true);
    expect(isDraftChanged(original, { kind: "project", text: "Python" })).toBe(true);
  });
});

describe("pendingSummary", () => {
  test.each([
    [1, "1 факт потребує перевірки"],
    [2, "2 факти потребують перевірки"],
    [4, "4 факти потребують перевірки"],
    [5, "5 фактів потребують перевірки"],
    [11, "11 фактів потребують перевірки"],
    [21, "21 факт потребує перевірки"],
  ])("%i → %s", (count, text) => {
    expect(pendingSummary(count)).toBe(text);
  });
});
