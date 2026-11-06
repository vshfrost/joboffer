import { describe, expect, test } from "vitest";

import type { Application } from "../domain/applications";
import { ApplicationNotFoundError, ApplicationsUnavailableError, ApplicationsValidationError } from "../domain/applicationsErrors";
import type { ApplicationsApi } from "../ports/applicationsApi";
import { createApplicationsServices } from "./applications";

const APPLICATION: Application = {
  jobId: 7,
  status: "applied",
  appliedOn: "2026-10-22",
  channel: "email",
  ats: null,
  companyDomains: [],
  companyEmails: [],
  statusChangedAt: "2026-10-22T09:00:00Z",
  allowedTransitions: ["replied", "interview", "offer", "rejected", "withdrawn"],
};
const INPUT = { channel: "email", appliedOn: "2026-10-22", ats: "", companyDomains: [], companyEmails: [] };

function services(overrides: Partial<ApplicationsApi>) {
  const api: ApplicationsApi = {
    get: () => Promise.resolve(APPLICATION),
    save: () => Promise.resolve(APPLICATION),
    setStatus: () => Promise.resolve(APPLICATION),
    ...overrides,
  };
  return createApplicationsServices(api);
}

const failing = (error: Error) => () => Promise.reject(error);

describe("load", () => {
  test("подача, а для неподаної — null", async () => {
    expect(await services({}).load(7)).toEqual({ ok: true, application: APPLICATION });
    expect(await services({ get: () => Promise.resolve(null) }).load(7)).toEqual({ ok: true, application: null });
  });

  test("збій сервера — ok: false", async () => {
    expect(await services({ get: failing(new ApplicationsUnavailableError("x")) }).load(7)).toEqual({ ok: false });
  });

  test("невідома помилка не ковтається", async () => {
    await expect(services({ get: failing(new TypeError("bug")) }).load(7)).rejects.toThrow("bug");
  });
});

describe.each([
  ["save", (s: ReturnType<typeof services>) => s.save(7, INPUT), "save" as const],
  ["move", (s: ReturnType<typeof services>) => s.move(7, "replied"), "setStatus" as const],
])("%s", (_name, run, method) => {
  test("успіх віддає подачу з відповіді сервера", async () => {
    expect(await run(services({}))).toEqual({ ok: true, application: APPLICATION });
  });

  test("422: загальний текст і тексти біля полів", async () => {
    const error = new ApplicationsValidationError({ channel: "Канал — один з: email.", applied_on: "Дата подачі не може бути в майбутньому." });
    expect(await run(services({ [method]: failing(error) }))).toEqual({
      ok: false,
      kind: "invalid",
      message: "Канал — один з: email. Дата подачі не може бути в майбутньому.",
      fieldErrors: { channel: "Канал — один з: email.", applied_on: "Дата подачі не може бути в майбутньому." },
    });
  });

  test("404 — not-found, збій — unavailable", async () => {
    expect(await run(services({ [method]: failing(new ApplicationNotFoundError()) }))).toEqual({ ok: false, kind: "not-found" });
    expect(await run(services({ [method]: failing(new ApplicationsUnavailableError("x")) }))).toEqual({ ok: false, kind: "unavailable" });
  });

  test("невідома помилка не ковтається", async () => {
    await expect(run(services({ [method]: failing(new TypeError("bug")) }))).rejects.toThrow("bug");
  });
});
