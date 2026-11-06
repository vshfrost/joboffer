import { describe, expect, test } from "vitest";

import { AnalysisNotFoundError, JobAppliedError, JobNotFoundError, JobsUnavailableError, JobsValidationError } from "../domain/jobsErrors";
import type { JobAnalysis } from "../domain/analysis";
import type { AddedJob, Job, JobList, JobsQuery } from "../domain/jobs";
import type { JobsApi } from "../ports/jobsApi";
import { createJobsServices } from "./jobs";

const LIST: JobList = {
  items: [
    { id: 1, source: "manual", url: null, title: "Dev", company: "Acme", createdAt: "2026-10-20T10:00:00Z", needsText: false, dismissed: false, score: null, filtersPassed: null, workMode: null, triageScore: null, triageVerdict: null, triageReason: null, status: null, isNew: false },
  ],
  sources: ["manual"],
  counts: { inProgress: 0, appliedUnreviewed: 0, needsText: false },
};
const JOB: Job = {
  id: 1,
  source: "manual",
  url: null,
  title: "Dev",
  company: "Acme",
  location: null,
  text: "Опис",
  createdAt: "2026-10-20T10:00:00Z",
  needsText: false,
  dismissedAt: null,
  dismissReason: null,
  triage: null,
};
const ANALYSIS: JobAnalysis = {
  id: 1,
  score: 0,
  summary: "Коротко",
  mustHave: [],
  niceToHave: [],
  keywords: [],
  seniority: null,
  workMode: null,
  location: null,
  languages: [],
  salaryMinEur: null,
  salaryMaxEur: null,
  relocation: null,
  reasons: [],
  gaps: [],
  filtersPassed: true,
  flags: [],
  updatedAt: "2026-10-22T09:00:00Z",
  staleSince: null,
};
const ADDED: AddedJob = { id: 7, outcome: "created" };
const INPUT = { text: "Опис", url: "", title: "", company: "" };
const QUERY: JobsQuery = { query: "", days: "", source: "", needsText: false, dismissed: false, triageVerdict: "", workMode: "", status: "", stage: "", limit: 200 };

/** Порт, що кидає `failure` з будь-якого виклику (або віддає дані, якщо нічого не кидати). */
function api(failure?: Error): JobsApi {
  const settle = <T>(value: T) => (failure === undefined ? Promise.resolve(value) : Promise.reject(failure));
  return {
    list: () => settle(LIST),
    get: () => settle(JOB),
    getAnalysis: () => settle(ANALYSIS),
    dismiss: () => settle(undefined),
    restore: () => settle(undefined),
    add: () => settle(ADDED),
  };
}

describe("збережений аналіз", () => {
  test("дані з порту — успіх", async () => {
    expect(await createJobsServices(api()).loadAnalysis(1)).toEqual({ ok: true, analysis: ANALYSIS });
  });

  test("аналізу ще нема — стан даних «none», не збій", async () => {
    expect(await createJobsServices(api(new AnalysisNotFoundError())).loadAnalysis(1)).toEqual({ ok: false, kind: "none" });
  });

  test("недоступний сервер — «unavailable»", async () => {
    expect(await createJobsServices(api(new JobsUnavailableError("503"))).loadAnalysis(1)).toEqual({ ok: false, kind: "unavailable" });
  });

  test("несподівана помилка не ковтається", async () => {
    await expect(createJobsServices(api(new TypeError("bug"))).loadAnalysis(1)).rejects.toBeInstanceOf(TypeError);
  });
});

describe("список вакансій", () => {
  test("дані з порту — успіх", async () => {
    expect(await createJobsServices(api()).list(QUERY)).toEqual({ ok: true, list: LIST });
  });

  test("недоступний сервер — результат без винятку", async () => {
    expect(await createJobsServices(api(new JobsUnavailableError("503"))).list(QUERY)).toEqual({ ok: false });
  });

  test("несподівана помилка не ковтається", async () => {
    await expect(createJobsServices(api(new RangeError("bug"))).list(QUERY)).rejects.toThrow("bug");
  });
});

describe("вакансія", () => {
  test("дані з порту — успіх", async () => {
    expect(await createJobsServices(api()).load(1)).toEqual({ ok: true, job: JOB });
  });

  test("нема або чужа — not-found", async () => {
    expect(await createJobsServices(api(new JobNotFoundError())).load(1)).toEqual({ ok: false, kind: "not-found" });
  });

  test("недоступний сервер — unavailable", async () => {
    expect(await createJobsServices(api(new JobsUnavailableError("503"))).load(1)).toEqual({ ok: false, kind: "unavailable" });
  });

  test("несподівана помилка не ковтається", async () => {
    await expect(createJobsServices(api(new RangeError("bug"))).load(1)).rejects.toThrow("bug");
  });
});

describe("приховування", () => {
  test("успіх", async () => {
    expect(await createJobsServices(api()).dismiss([1], "не цікаво")).toEqual({ ok: true });
  });

  test("422 — текст сервера й тексти біля полів", async () => {
    const failure = new JobsValidationError({ reason: "Вкажи причину приховування." });
    expect(await createJobsServices(api(failure)).dismiss([1], "")).toEqual({
      ok: false,
      kind: "invalid",
      message: "Вкажи причину приховування.",
      fieldErrors: { reason: "Вкажи причину приховування." },
    });
  });

  test("на вакансію є подача — applied", async () => {
    expect(await createJobsServices(api(new JobAppliedError())).dismiss([1], "x")).toEqual({ ok: false, kind: "applied" });
  });

  test("недоступний сервер — unavailable", async () => {
    expect(await createJobsServices(api(new JobsUnavailableError("503"))).dismiss([1], "x")).toEqual({
      ok: false,
      kind: "unavailable",
    });
  });

  test("несподівана помилка не ковтається", async () => {
    await expect(createJobsServices(api(new RangeError("bug"))).dismiss([1], "x")).rejects.toThrow("bug");
  });
});

describe("повернення", () => {
  test("успіх", async () => {
    expect(await createJobsServices(api()).restore(1)).toEqual({ ok: true });
  });

  test("нема або чужа — not-found", async () => {
    expect(await createJobsServices(api(new JobNotFoundError())).restore(1)).toEqual({ ok: false, kind: "not-found" });
  });

  test("недоступний сервер — unavailable", async () => {
    expect(await createJobsServices(api(new JobsUnavailableError("503"))).restore(1)).toEqual({ ok: false, kind: "unavailable" });
  });

  test("несподівана помилка не ковтається", async () => {
    await expect(createJobsServices(api(new RangeError("bug"))).restore(1)).rejects.toThrow("bug");
  });
});

describe("додавання", () => {
  test("успіх — що саме сталося й номер вакансії", async () => {
    expect(await createJobsServices(api()).add(INPUT)).toEqual({ ok: true, added: ADDED });
  });

  test("422 — загальний текст і тексти біля полів", async () => {
    const failure = new JobsValidationError({ text: "Встав текст опису вакансії.", url: "Посилання має починатися з http:// або https://." });
    expect(await createJobsServices(api(failure)).add(INPUT)).toEqual({
      ok: false,
      kind: "invalid",
      message: "Встав текст опису вакансії. Посилання має починатися з http:// або https://.",
      fieldErrors: { text: "Встав текст опису вакансії.", url: "Посилання має починатися з http:// або https://." },
    });
  });

  test("недоступний сервер — unavailable", async () => {
    expect(await createJobsServices(api(new JobsUnavailableError("503"))).add(INPUT)).toEqual({ ok: false, kind: "unavailable" });
  });

  test("несподівана помилка не ковтається", async () => {
    await expect(createJobsServices(api(new RangeError("bug"))).add(INPUT)).rejects.toThrow("bug");
  });
});
