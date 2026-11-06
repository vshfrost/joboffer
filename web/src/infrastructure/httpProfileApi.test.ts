import { describe, expect, test, vi } from "vitest";

import type { Profile } from "../domain/profile";
import { ProfileUnavailableError, ProfileValidationError } from "../domain/profileErrors";
import { createApiClient } from "./apiClient";
import { createHttpProfileApi } from "./httpProfileApi";

const BODY = {
  target: { roles: ["SRE"], seniority: ["senior"], min_salary_eur: 65000, target_domains: ["fintech"] },
  locations: {
    work_modes: ["remote"],
    locations: [{ place: "Valencia", aliases: ["VLC"], work_modes: ["hybrid"] }],
    include_unknown_mode: false,
    relocation: true,
  },
  rules: { title_keywords: ["a"], title_exclude: ["b"], stop_words: ["c"] },
  contacts: {
    full_name: "N",
    email: "e@x.y",
    phone: "1",
    linkedin_url: "https://l",
    city: "C",
    github_url: "https://g",
    work_authorization: "W",
  },
};

const PROFILE: Profile = {
  target: { roles: ["SRE"], seniority: ["senior"], minSalaryEur: 65000, targetDomains: ["fintech"] },
  locations: {
    workModes: ["remote"],
    locations: [{ place: "Valencia", aliases: ["VLC"], workModes: ["hybrid"] }],
    includeUnknownMode: false,
    relocation: true,
  },
  rules: { titleKeywords: ["a"], titleExclude: ["b"], stopWords: ["c"] },
  contacts: {
    fullName: "N",
    email: "e@x.y",
    phone: "1",
    linkedinUrl: "https://l",
    city: "C",
    githubUrl: "https://g",
    workAuthorization: "W",
  },
};

/** Межа — fetch: відповідь або збій мережі. */
function apiWith(respond: (init: RequestInit | undefined) => Response | Promise<Response>) {
  const fetchFn = vi.fn<typeof fetch>((_input, init) => Promise.resolve(respond(init)));
  return { api: createHttpProfileApi(createApiClient(fetchFn, "/api")), fetchFn };
}

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

describe("GET /profile", () => {
  test("розбирає відповідь у доменний профіль", async () => {
    const { api, fetchFn } = apiWith(() => json(200, BODY));
    expect(await api.get()).toEqual(PROFILE);
    expect(fetchFn.mock.calls[0]?.[0]).toBe("/api/profile");
  });

  test("не 200 — недоступний", async () => {
    await expect(apiWith(() => json(503, {})).api.get()).rejects.toBeInstanceOf(ProfileUnavailableError);
  });

  test("збій мережі — недоступний, навіть якщо кинули не Error", async () => {
    const api = createHttpProfileApi(createApiClient(() => Promise.reject(new TypeError("fetch failed")), "/api"));
    await expect(api.get()).rejects.toBeInstanceOf(ProfileUnavailableError);
    const client = { request: () => Promise.reject("boom"), setCsrfToken: () => undefined };
    await expect(createHttpProfileApi(client).get()).rejects.toThrow("Мережа недоступна");
  });

  const broken: [string, (body: typeof BODY) => unknown][] = [
    ["тіло не обʼєкт", () => ["x"]],
    ["розділу нема", (body) => ({ ...body, rules: undefined })],
    ["розділ не обʼєкт", (body) => ({ ...body, target: 1 })],
    ["ролі не масив", (body) => ({ ...body, target: { ...body.target, roles: "SRE" } })],
    ["роль не рядок", (body) => ({ ...body, target: { ...body.target, roles: [1] } })],
    ["невідомий рівень", (body) => ({ ...body, target: { ...body.target, seniority: ["wizard"] } })],
    ["зарплата не число", (body) => ({ ...body, target: { ...body.target, min_salary_eur: "65" } })],
    ["локації не масив", (body) => ({ ...body, locations: { ...body.locations, locations: {} } })],
    ["локація не обʼєкт", (body) => ({ ...body, locations: { ...body.locations, locations: [1] } })],
    ["місце не рядок", (body) => ({ ...body, locations: { ...body.locations, locations: [{ place: 1, aliases: [], work_modes: [] }] } })],
    ["невідомий формат", (body) => ({ ...body, locations: { ...body.locations, work_modes: ["office"] } })],
    ["прапорець не булів", (body) => ({ ...body, locations: { ...body.locations, relocation: "yes" } })],
    ["контакт не рядок", (body) => ({ ...body, contacts: { ...body.contacts, email: 1 } })],
  ];

  test.each(broken)("відповідь не за контрактом (%s) — недоступний", async (_name, mutate) => {
    const { api } = apiWith(() => json(200, mutate(BODY)));
    await expect(api.get()).rejects.toBeInstanceOf(ProfileUnavailableError);
  });

  test("зарплата null — не вказано", async () => {
    const { api } = apiWith(() => json(200, { ...BODY, target: { ...BODY.target, min_salary_eur: null } }));
    expect((await api.get()).target.minSalaryEur).toBeNull();
  });
});

describe("PUT /profile/<розділ>", () => {
  test.each([
    ["target", PROFILE.target, BODY.target],
    ["locations", PROFILE.locations, BODY.locations],
    ["rules", PROFILE.rules, BODY.rules],
    ["contacts", PROFILE.contacts, BODY.contacts],
  ] as const)("розділ %s шле своє тіло в snake_case й повертає профіль", async (section, value, expectedBody) => {
    const { api, fetchFn } = apiWith(() => json(200, BODY));
    expect(await api.save(section, value as never)).toEqual(PROFILE);
    const [url, init] = fetchFn.mock.calls[0] ?? [];
    expect([url, init?.method]).toEqual([`/api/profile/${section}`, "PUT"]);
    expect(JSON.parse(String(init?.body))).toEqual(expectedBody);
  });

  test("422 — помилки полів за шляхом, перша помилка поля виграє", async () => {
    const { api } = apiWith(() =>
      json(422, {
        field_errors: [
          { field: "locations.1.place", message: "Дубль." },
          { field: "locations.1.place", message: "Друга." },
          { field: "email", message: "Email." },
        ],
      }),
    );
    const error = await api.save("contacts", PROFILE.contacts).catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ProfileValidationError);
    expect((error as ProfileValidationError).fieldErrors).toEqual({ "locations.1.place": "Дубль.", email: "Email." });
  });

  test.each([
    ["тіло не обʼєкт", []],
    ["без field_errors", {}],
    ["порожні field_errors", { field_errors: [] }],
    ["елемент не обʼєкт", { field_errors: [1] }],
    ["поле не рядок", { field_errors: [{ field: 1, message: "x" }] }],
    ["повідомлення не рядок", { field_errors: [{ field: "a", message: 1 }] }],
  ])("422 %s — недоступний, а не мовчазний успіх", async (_name, body) => {
    const { api } = apiWith(() => json(422, body));
    await expect(api.save("rules", PROFILE.rules)).rejects.toBeInstanceOf(ProfileUnavailableError);
  });

  test.each([401, 403, 500])("статус %d — недоступний", async (status) => {
    const { api } = apiWith(() => json(status, { code: "x" }));
    await expect(api.save("rules", PROFILE.rules)).rejects.toBeInstanceOf(ProfileUnavailableError);
  });

  test("200 не за контрактом — недоступний", async () => {
    const { api } = apiWith(() => json(200, { target: 1 }));
    await expect(api.save("rules", PROFILE.rules)).rejects.toBeInstanceOf(ProfileUnavailableError);
  });
});
