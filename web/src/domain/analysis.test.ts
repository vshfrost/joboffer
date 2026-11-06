import { describe, expect, test } from "vitest";

import {
  NOT_STATED,
  relocationText,
  salaryText,
  scoreText,
  SENIORITY_LABELS,
  VERDICT_LABELS,
  VERDICTS,
  WORK_MODE_LABELS,
  WORK_MODES,
} from "./analysis";

describe("scoreText", () => {
  test("без оцінки — «Не оцінено»", () => {
    expect(scoreText(null)).toBe("Не оцінено");
  });

  test.each([
    [0, "0%"],
    [1, "1%"],
    [78, "78%"],
    [100, "100%"],
  ])("оцінка %i — %s (нуль — валідна оцінка, не «Не оцінено»)", (score, text) => {
    expect(scoreText(score)).toBe(text);
  });
});

describe("salaryText", () => {
  const nbsp = " ";

  test("нічого не сказано — «не вказано»", () => {
    expect(salaryText(null, null)).toBe(NOT_STATED);
    expect(NOT_STATED).toBe("не вказано");
  });

  test("вилка", () => {
    expect(salaryText(60000, 80000)).toBe(`60${nbsp}000–80${nbsp}000 EUR на рік`);
  });

  test("лише низ вилки", () => {
    expect(salaryText(60000, null)).toBe(`від 60${nbsp}000 EUR на рік`);
  });

  test("лише верх вилки", () => {
    expect(salaryText(null, 80000)).toBe(`до 80${nbsp}000 EUR на рік`);
  });

  test("однакові краї — одна сума", () => {
    expect(salaryText(70000, 70000)).toBe(`70${nbsp}000 EUR на рік`);
  });

  test("нуль — теж сума", () => {
    expect(salaryText(0, 0)).toBe("0 EUR на рік");
  });
});

describe("relocationText", () => {
  test("так, ні і не вказано — три різні відповіді", () => {
    expect(relocationText(true)).toBe("Допомога з переїздом є");
    expect(relocationText(false)).toBe("Допомоги з переїздом нема");
    expect(relocationText(null)).toBe("не вказано");
  });
});

describe("підписи", () => {
  test("вердикти тріажу — слова макета A", () => {
    expect(VERDICTS.map((verdict) => VERDICT_LABELS[verdict])).toEqual(["Аналізувати", "Можливо", "Пропустити"]);
  });

  test("формати й рівні", () => {
    expect(WORK_MODES.map((mode) => WORK_MODE_LABELS[mode])).toEqual(["Remote", "Hybrid", "Onsite"]);
    expect(Object.values(SENIORITY_LABELS)).toEqual(["Junior", "Middle", "Senior", "Lead", "Principal"]);
  });
});
