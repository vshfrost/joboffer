import { describe, expect, test, vi } from "vitest";

import { ApplicationNotFoundError, ApplicationsUnavailableError, ApplicationsValidationError } from "../domain/applicationsErrors";
import { createApiClient } from "./apiClient";
import { createHttpApplicationsApi } from "./httpApplicationsApi";

const BODY = {
  job_id: 7,
  status: "interview",
  applied_on: "2026-10-22",
  channel: "ats",
  ats: "lever",
  company_domains: ["acme.com"],
  company_emails: ["hr@acme.com"],
  status_changed_at: "2026-10-23T09:00:00Z",
  allowed_transitions: ["offer", "rejected", "withdrawn"],
};
const APPLICATION = {
  jobId: 7,
  status: "interview",
  appliedOn: "2026-10-22",
  channel: "ats",
  ats: "lever",
  companyDomains: ["acme.com"],
  companyEmails: ["hr@acme.com"],
  statusChangedAt: "2026-10-23T09:00:00Z",
  allowedTransitions: ["offer", "rejected", "withdrawn"],
};
const INPUT = { channel: "ats", appliedOn: "2026-10-22", ats: "lever", companyDomains: ["acme.com"], companyEmails: ["hr@acme.com"] };

/** Межа — fetch: відповідь або збій мережі. */
function apiWith(respond: (input: string, init: RequestInit | undefined) => Response | Promise<Response>) {
  const fetchFn = vi.fn<typeof fetch>((input, init) => Promise.resolve(respond(String(input), init)));
  const client = createApiClient(fetchFn, "/api");
  client.setCsrfToken("csrf-1");
  return { api: createHttpApplicationsApi(client), fetchFn };
}

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const invalid = (...errors: [string, string][]) =>
  json(422, { code: "invalid_fields", message: "x", field_errors: errors.map(([field, message]) => ({ field, message })) });

describe("get", () => {
  test("читає подачу з GET /jobs/{id}/application", async () => {
    const { api, fetchFn } = apiWith(() => json(200, BODY));
    expect(await api.get(7)).toEqual(APPLICATION);
    expect(fetchFn).toHaveBeenCalledWith("/api/jobs/7/application", expect.objectContaining({ method: "GET" }));
  });

  test("подача без ATS і контактів", async () => {
    const { api } = apiWith(() => json(200, { ...BODY, ats: null, company_domains: [], company_emails: [], allowed_transitions: [] }));
    expect(await api.get(7)).toMatchObject({ ats: null, companyDomains: [], companyEmails: [], allowedTransitions: [] });
  });

  test("404 — подачі нема: null", async () => {
    const { api } = apiWith(() => json(404, { code: "not_found", message: "Не знайдено", field_errors: [] }));
    expect(await api.get(7)).toBeNull();
  });

  test("інша відповідь і збій мережі — недоступно", async () => {
    await expect(apiWith(() => json(500, {})).api.get(7)).rejects.toBeInstanceOf(ApplicationsUnavailableError);
    await expect(apiWith(() => Promise.reject(new Error("offline"))).api.get(7)).rejects.toBeInstanceOf(ApplicationsUnavailableError);
    await expect(apiWith(() => Promise.reject("offline")).api.get(7)).rejects.toThrow("Мережа недоступна");
  });
});

describe("збій клієнта", () => {
  test("кинуте не-Error значення стає текстом «Мережа недоступна»", async () => {
    const client = { request: () => Promise.reject("offline"), setCsrfToken: () => {} };
    await expect(createHttpApplicationsApi(client).get(7)).rejects.toThrow("Мережа недоступна");
  });
});

describe("контракт відповіді", () => {
  const broken: [string, unknown][] = [
    ["не об'єкт", []],
    ["статус поза переліком", { ...BODY, status: "hired" }],
    ["канал поза переліком", { ...BODY, channel: "phone" }],
    ["ATS поза переліком", { ...BODY, ats: "workday" }],
    ["номер не ціле", { ...BODY, job_id: "7" }],
    ["дата не текст", { ...BODY, applied_on: 20261022 }],
    ["домени не список", { ...BODY, company_domains: "acme.com" }],
    ["адреса не текст", { ...BODY, company_emails: [1] }],
    ["дозволені переходи поза переліком", { ...BODY, allowed_transitions: ["hired"] }],
    ["дозволені переходи не список", { ...BODY, allowed_transitions: null }],
  ];

  test.each(broken)("%s — збій контракту", async (_name, body) => {
    await expect(apiWith(() => json(200, body)).api.get(7)).rejects.toThrow(ApplicationsUnavailableError);
    await expect(apiWith(() => json(200, body)).api.save(7, INPUT)).rejects.toThrow(ApplicationsUnavailableError);
  });
});

describe("save", () => {
  test("PUT /jobs/{id}/application з тілом у форматі API", async () => {
    const { api, fetchFn } = apiWith(() => json(200, BODY));
    expect(await api.save(7, INPUT)).toEqual(APPLICATION);
    const [, init] = fetchFn.mock.calls[0] ?? [];
    expect(fetchFn.mock.calls[0]?.[0]).toBe("/api/jobs/7/application");
    expect(init?.method).toBe("PUT");
    expect(JSON.parse(String(init?.body))).toEqual({
      channel: "ats",
      applied_on: "2026-10-22",
      ats: "lever",
      company_domains: ["acme.com"],
      company_emails: ["hr@acme.com"],
    });
    expect((init?.headers as Record<string, string>)["X-CSRF-Token"]).toBe("csrf-1");
  });

  test("422 — тексти біля полів; перший текст на поле", async () => {
    const { api } = apiWith(() => invalid(["channel", "Канал — один з: email."], ["channel", "Другий"], ["applied_on", "Дата подачі — у форматі YYYY-MM-DD."]));
    const error = await api.save(7, INPUT).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApplicationsValidationError);
    expect((error as ApplicationsValidationError).fieldErrors).toEqual({ channel: "Канал — один з: email.", applied_on: "Дата подачі — у форматі YYYY-MM-DD." });
  });

  test("422 без розпізнаних полів — збій контракту", async () => {
    for (const body of [[], {}, { field_errors: [] }, { field_errors: [1] }, { field_errors: [{ field: 1, message: "x" }] }]) {
      await expect(apiWith(() => json(422, body)).api.save(7, INPUT)).rejects.toBeInstanceOf(ApplicationsUnavailableError);
    }
  });

  test("404 — вакансії нема", async () => {
    await expect(apiWith(() => json(404, {})).api.save(7, INPUT)).rejects.toBeInstanceOf(ApplicationNotFoundError);
  });

  test("інша відповідь — недоступно", async () => {
    await expect(apiWith(() => json(500, {})).api.save(7, INPUT)).rejects.toBeInstanceOf(ApplicationsUnavailableError);
  });
});

describe("setStatus", () => {
  test("POST /jobs/{id}/application/status зі статусом", async () => {
    const { api, fetchFn } = apiWith(() => json(200, BODY));
    expect(await api.setStatus(7, "interview")).toEqual(APPLICATION);
    const [url, init] = fetchFn.mock.calls[0] ?? [];
    expect(url).toBe("/api/jobs/7/application/status");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ status: "interview" });
  });

  test("422 — перехід неможливий: текст біля статусу", async () => {
    const { api } = apiWith(() => invalid(["status", "Подачу вже закрито (rejected): статус більше не змінюється."]));
    const error = await api.setStatus(7, "offer").catch((caught: unknown) => caught);
    expect((error as ApplicationsValidationError).fieldErrors).toEqual({ status: "Подачу вже закрито (rejected): статус більше не змінюється." });
  });

  test("404 — подачі нема", async () => {
    await expect(apiWith(() => json(404, {})).api.setStatus(7, "offer")).rejects.toBeInstanceOf(ApplicationNotFoundError);
  });

  test("інша відповідь — недоступно", async () => {
    await expect(apiWith(() => json(503, {})).api.setStatus(7, "offer")).rejects.toBeInstanceOf(ApplicationsUnavailableError);
  });
});
