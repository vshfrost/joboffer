import { describe, expect, test } from "vitest";

import {
  deadlineText,
  gapOf,
  jobFullLabel,
  jobLabel,
  KIND_LABELS,
  KIT_QUESTION_LABELS,
  progressText,
  remainingText,
  STATUS_LABELS,
  STEP_KIND_LABELS,
  readinessText,
  STORY_PARTS,
} from "./prep";

describe("підписи", () => {
  test("статуси теми: без плану, заплановано, вивчаю, практика, готово", () => {
    expect(STATUS_LABELS).toEqual({ new: "Без плану", planned: "Заплановано", learning: "Вивчаю", practicing: "Практика", ready: "Готово" });
  });

  test("види теми: технічна, поведінкова, доменна", () => {
    expect(KIND_LABELS).toEqual({ tech: "Технічна", behavioral: "Поведінкова", domain: "Доменна" });
  });

  test("види кроку: вивчення, практика, перевірка", () => {
    expect(STEP_KIND_LABELS).toEqual({ learn: "Вивчення", practice: "Практика", check: "Перевірка" });
  });
});

describe("прогрес теми", () => {
  test("залишок часу — «Лишилось ~N хв»", () => {
    expect(remainingText({ stepsTotal: 5, minutesLeft: 150 })).toBe("Лишилось ~150 хв");
  });

  test("усе виконано — «Лишилось ~0 хв»", () => {
    expect(remainingText({ stepsTotal: 3, minutesLeft: 0 })).toBe("Лишилось ~0 хв");
  });

  test("тема без кроків — «Плану ще немає», а не нуль хвилин", () => {
    expect(remainingText({ stepsTotal: 0, minutesLeft: 0 })).toBe("Плану ще немає");
  });

  test("виконано з усіх кроків — «N/M»", () => {
    expect(progressText({ stepsDone: 2, stepsTotal: 5 })).toBe("2/5");
    expect(progressText({ stepsDone: 0, stepsTotal: 0 })).toBe("0/0");
  });

  test("дедлайн — день як є, без дедлайну — «—»", () => {
    expect(deadlineText("2026-11-03")).toBe("2026-11-03");
    expect(deadlineText(null)).toBe("—");
  });
});

describe("вакансія в посиланні", () => {
  test("у списку: компанія, інакше назва, інакше номер", () => {
    expect(jobLabel({ jobId: 24, title: "Senior Backend Engineer", company: "Northstar" })).toBe("Northstar");
    expect(jobLabel({ jobId: 24, title: "Senior Backend Engineer", company: null })).toBe("Senior Backend Engineer");
    expect(jobLabel({ jobId: 24, title: null, company: null })).toBe("Вакансія #24");
  });

  test("на сторінці теми: «назва · компанія», що відома, інакше номер", () => {
    expect(jobFullLabel({ jobId: 24, title: "Senior Backend Engineer", company: "Northstar" })).toBe("Senior Backend Engineer · Northstar");
    expect(jobFullLabel({ jobId: 24, title: "Senior Backend Engineer", company: null })).toBe("Senior Backend Engineer");
    expect(jobFullLabel({ jobId: 24, title: null, company: "Northstar" })).toBe("Northstar");
    expect(jobFullLabel({ jobId: 24, title: null, company: null })).toBe("Вакансія #24");
  });
});

describe("пакет до інтерв'ю", () => {
  test("вид питання — українською", () => {
    expect(KIT_QUESTION_LABELS).toEqual({ technical: "Технічне", behavioral: "Поведінкове" });
  });

  test("STAR: літери, підписи й поля історії в порядку S, T, A, R", () => {
    expect(STORY_PARTS).toEqual([
      { letter: "S", label: "Ситуація", field: "situation" },
      { letter: "T", label: "Завдання", field: "task" },
      { letter: "A", label: "Дії", field: "action" },
      { letter: "R", label: "Результат", field: "result" },
    ]);
  });
});

describe("готовність до вакансії", () => {
  test("число — з відсотком", () => {
    expect(readinessText(37)).toBe("37%");
  });

  test("нуль — це 0%, а не відсутність", () => {
    expect(readinessText(0)).toBe("0%");
  });

  test("тем нема — тире, а не 0%", () => {
    expect(readinessText(null)).toBe("—");
  });
});

describe("прогалина теми для вакансії", () => {
  const jobs = [
    { jobId: 2, title: null, company: null, score: 70, gap: "Прогалина вакансії 2." },
    { jobId: 1, title: null, company: null, score: 80, gap: "Прогалина вакансії 1." },
  ];

  test("береться прогалина саме цієї вакансії", () => {
    expect(gapOf({ jobs }, 1)).toBe("Прогалина вакансії 1.");
  });

  test("тема не згадує вакансію — прогалини нема", () => {
    expect(gapOf({ jobs }, 9)).toBe("");
  });
});
