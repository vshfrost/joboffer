import { describe, expect, test } from "vitest";

import type { InterviewKit, JobPrep, PrepOverview, Topic } from "../domain/prep";
import { PrepNotFoundError, PrepUnauthorizedError, PrepUnavailableError, PrepValidationError } from "../domain/prepErrors";
import type { PrepApi } from "../ports/prepApi";
import { createPrepServices, type PrepServices } from "./prep";

const TOPIC: Topic = {
  id: 7,
  slug: "ddd-symfony",
  title: "DDD у Symfony",
  kind: "tech",
  summary: "Межі агрегатів.",
  status: "planned",
  percent: 0,
  stepsDone: 0,
  stepsTotal: 1,
  minutesLeft: 45,
  deadline: null,
  priority: 86,
  jobs: [],
  quiz: { total: 0, due: 0 },
  nextStepId: 31,
  steps: [],
};
const OVERVIEW: PrepOverview = { topics: [], quiz: { total: 0, due: 0 } };
const JOB_PREP: JobPrep = { readiness: 40, topics: [] };
const KIT: InterviewKit = { id: 3, jobId: 24, version: 2, createdOn: "2026-10-27", questions: [], stories: [], companyQuestions: [] };

/** Порт, у якого кожен метод кидає `error`. */
function failing(error: unknown): PrepApi {
  const fail = () => Promise.reject(error);
  return { topics: fail, topic: fail, completeStep: fail, setReady: fail, jobPrep: fail, interviewKit: fail };
}

function working(): PrepApi {
  return {
    topics: () => Promise.resolve(OVERVIEW),
    topic: () => Promise.resolve(TOPIC),
    completeStep: () => Promise.resolve(TOPIC),
    setReady: () => Promise.resolve(TOPIC),
    jobPrep: () => Promise.resolve(JOB_PREP),
    interviewKit: () => Promise.resolve(KIT),
  };
}

const CALLS: [string, (services: PrepServices) => Promise<{ ok: boolean }>][] = [
  ["topics", (services) => services.topics()],
  ["topic", (services) => services.topic(7)],
  ["completeStep", (services) => services.completeStep(31, "")],
  ["setReady", (services) => services.setReady(7, true)],
  ["jobPrep", (services) => services.jobPrep(24)],
  ["interviewKit", (services) => services.interviewKit(24)],
];
const WITH_NOT_FOUND = CALLS.filter(([name]) => name !== "topics");

describe("успіх", () => {
  test("кожна операція віддає результат порту", async () => {
    const services = createPrepServices(working());

    expect(await services.topics()).toEqual({ ok: true, overview: OVERVIEW });
    expect(await services.topic(7)).toEqual({ ok: true, topic: TOPIC });
    expect(await services.completeStep(31, "Зробив")).toEqual({ ok: true, topic: TOPIC });
    expect(await services.setReady(7, true)).toEqual({ ok: true, topic: TOPIC });
    expect(await services.jobPrep(24)).toEqual({ ok: true, jobPrep: JOB_PREP });
    expect(await services.interviewKit(24)).toEqual({ ok: true, kit: KIT });
  });

  test("порт отримує номери й аргументи без змін", async () => {
    const calls: unknown[][] = [];
    const api: PrepApi = {
      ...working(),
      completeStep: (stepId, note) => {
        calls.push(["completeStep", stepId, note]);
        return Promise.resolve(TOPIC);
      },
      setReady: (topicId, ready) => {
        calls.push(["setReady", topicId, ready]);
        return Promise.resolve(TOPIC);
      },
    };
    const services = createPrepServices(api);

    await services.completeStep(31, "Нотатка");
    await services.setReady(7, false);

    expect(calls).toEqual([
      ["completeStep", 31, "Нотатка"],
      ["setReady", 7, false],
    ]);
  });
});

describe("проблеми", () => {
  test.each(CALLS)("%s: без сесії — unauthorized", async (_name, call) => {
    expect(await call(createPrepServices(failing(new PrepUnauthorizedError())))).toEqual({ ok: false, kind: "unauthorized" });
  });

  test.each(CALLS)("%s: сервер недоступний — unavailable", async (_name, call) => {
    expect(await call(createPrepServices(failing(new PrepUnavailableError("x"))))).toEqual({ ok: false, kind: "unavailable" });
  });

  test.each(WITH_NOT_FOUND)("%s: нема чи чуже — not-found", async (_name, call) => {
    expect(await call(createPrepServices(failing(new PrepNotFoundError())))).toEqual({ ok: false, kind: "not-found" });
  });

  test("«виконано»: сервер відхилив нотатку — invalid із текстом біля поля", async () => {
    const services = createPrepServices(failing(new PrepValidationError("Нотатка задовга.", { note: "Нотатка — до 2000 символів." })));

    expect(await services.completeStep(31, "x")).toEqual({ ok: false, kind: "invalid", message: "Нотатка задовга.", fieldErrors: { note: "Нотатка — до 2000 символів." } });
  });

  test.each(CALLS)("%s: непередбачена помилка не ховається", async (_name, call) => {
    await expect(call(createPrepServices(failing(new RangeError("баг"))))).rejects.toThrow("баг");
  });
});
