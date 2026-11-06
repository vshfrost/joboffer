import { describe, expect, test } from "vitest";

import {
  atsBadge,
  atsStatus,
  issuesText,
  keywordSummary,
  madridDateTime,
  pagesText,
  photoMark,
  splitByKind,
  type JobDocument,
  type LintReport,
} from "./documents";

function document(id: number, kind: "cv" | "cl", version: number, overrides: Partial<JobDocument> = {}): JobDocument {
  return { id, jobId: 1, kind, version, createdAt: "2026-10-22T09:40:00Z", fileName: "A_CV.pdf", pdfAvailable: true, photoId: null, lint: null, ...overrides };
}

const REPORT: LintReport = { passed: true, pages: 2, issues: [], keywords: { covered: ["Python", "FastAPI"], missing: ["Kafka"], percent: 67 } };

describe("splitByKind", () => {
  test("остання версія кожного виду й історія новіші першими, нумерація видів незалежна", () => {
    const documents = [document(5, "cl", 2), document(4, "cv", 3), document(3, "cl", 1), document(2, "cv", 2), document(1, "cv", 1)];

    const split = splitByKind(documents);

    expect(split.cv.latest?.id).toBe(4);
    expect(split.cv.history.map((item) => item.version)).toEqual([2, 1]);
    expect(split.cl.latest?.id).toBe(5);
    expect(split.cl.history.map((item) => item.version)).toEqual([1]);
  });

  test("порядок рівня сервера не вгадується: остання — з найбільшою версією свого виду", () => {
    const split = splitByKind([document(1, "cv", 1), document(2, "cv", 2)]);

    expect(split.cv.latest?.version).toBe(2);
    expect(split.cv.history.map((item) => item.version)).toEqual([1]);
  });

  test("лише CV: листа нема", () => {
    const split = splitByKind([document(1, "cv", 1)]);

    expect(split.cl).toEqual({ latest: null, history: [] });
    expect(split.cv.history).toEqual([]);
  });

  test("жодного документа", () => {
    expect(splitByKind([])).toEqual({ cv: { latest: null, history: [] }, cl: { latest: null, history: [] } });
  });
});

describe("ATS-статус", () => {
  test("без звіту — «немає звіту», а не «пройдено»", () => {
    expect(atsStatus(null)).toBe("no-report");
    expect(atsBadge(null)).toEqual({ tone: "neutral", text: "ATS: немає звіту" });
  });

  test("пройдено, коли нема issues", () => {
    expect(atsStatus(REPORT)).toBe("passed");
    expect(atsBadge(REPORT)).toEqual({ tone: "success", text: "✓ ATS: перевірку пройдено" });
  });

  test("зауваження: кількість у тексті", () => {
    const report = { ...REPORT, passed: false, issues: [{ code: "pages", message: "3 сторінок" }] };

    expect(atsStatus(report)).toBe("issues");
    expect(atsBadge(report)).toEqual({ tone: "warning", text: "ATS · 1 зауваження" });
  });

  test("покриття ключових слів не міняє статус", () => {
    const none = { ...REPORT, keywords: { covered: [], missing: ["Kafka", "Go"], percent: 0 } };

    expect(atsStatus(none)).toBe("passed");
    expect(atsStatus({ ...REPORT, keywords: null })).toBe("passed");
  });

  test.each([
    [1, "1 зауваження"],
    [2, "2 зауваження"],
    [4, "4 зауваження"],
    [5, "5 зауважень"],
    [11, "11 зауважень"],
    [12, "12 зауважень"],
    [14, "14 зауважень"],
    [21, "21 зауваження"],
    [22, "22 зауваження"],
    [25, "25 зауважень"],
  ])("%i → %s", (count, text) => {
    expect(issuesText(count)).toBe(text);
  });
});

describe("покриття ключових слів", () => {
  test("без звіту покриття не перевірено", () => {
    expect(keywordSummary(null)).toBe("Покриття не перевірено");
  });

  test("вакансію не аналізовано — покриття не рахувалося", () => {
    expect(keywordSummary({ ...REPORT, keywords: null })).toBe("Покриття не рахувалося: вакансію не аналізовано");
  });

  test("знайдено / усього й відсоток від сервера", () => {
    expect(keywordSummary(REPORT)).toBe("Ключові слова: 2/3 · 67%");
  });

  test("в аналізі нема ключових слів — не 0/0 і не 100 %", () => {
    expect(keywordSummary({ ...REPORT, keywords: { covered: [], missing: [], percent: 100 } })).toBe("В аналізі нема ключових слів");
  });

  test("жодного знайденого — 0 %", () => {
    expect(keywordSummary({ ...REPORT, keywords: { covered: [], missing: ["Go"], percent: 0 } })).toBe("Ключові слова: 0/1 · 0%");
  });
});

test("сторінки", () => {
  expect(pagesText(1)).toBe("1 стор.");
  expect(pagesText(3)).toBe("3 стор.");
});

describe("дата й час за Мадридом", () => {
  test.each([
    ["2026-10-22T09:40:00Z", "2026-10-22, 11:40"],
    ["2026-12-01T09:40:00Z", "2026-12-01, 10:40"],
    ["2026-10-21T22:30:00Z", "2026-10-22, 00:30"],
  ])("%s → %s", (iso, text) => {
    expect(madridDateTime(iso)).toBe(text);
  });
});

describe("позначка фото в шапці CV", () => {
  test("CV з фото і без", () => {
    expect(photoMark(document(1, "cv", 1, { photoId: 3 }))).toBe("з фото");
    expect(photoMark(document(2, "cv", 2, { photoId: null }))).toBe("без фото");
  });

  test("лист фото не має — позначки нема", () => {
    expect(photoMark(document(3, "cl", 1))).toBeNull();
  });
});
