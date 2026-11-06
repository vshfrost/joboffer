/** Підроблений бекенд профілю для тестів: `GET /api/profile` і `PUT /api/profile/<розділ>` над станом у памʼяті. */

import { fakeBackend, json, MEANS_LOGGED_IN, type Handler } from "./testClient";

export interface ApiProfile {
  target: { roles: string[]; seniority: string[]; min_salary_eur: number | null; target_domains: string[] };
  locations: {
    work_modes: string[];
    locations: { place: string; aliases: string[]; work_modes: string[] }[];
    include_unknown_mode: boolean;
    relocation: boolean;
  };
  rules: { title_keywords: string[]; title_exclude: string[]; stop_words: string[] };
  contacts: {
    full_name: string;
    email: string;
    phone: string;
    linkedin_url: string;
    city: string;
    github_url: string;
    work_authorization: string;
  };
}

export const EMPTY_PROFILE: ApiProfile = {
  target: { roles: [], seniority: [], min_salary_eur: null, target_domains: [] },
  locations: { work_modes: [], locations: [], include_unknown_mode: true, relocation: false },
  rules: { title_keywords: [], title_exclude: [], stop_words: [] },
  contacts: {
    full_name: "",
    email: "",
    phone: "",
    linkedin_url: "",
    city: "",
    github_url: "",
    work_authorization: "",
  },
};

export const FULL_PROFILE: ApiProfile = {
  target: {
    roles: ["Backend Engineer", "SRE"],
    seniority: ["senior", "lead"],
    min_salary_eur: 65000,
    target_domains: ["fintech", "payments"],
  },
  locations: {
    work_modes: ["remote", "hybrid"],
    locations: [
      { place: "Valencia", aliases: ["Валенсія"], work_modes: ["hybrid"] },
      { place: "Madrid", aliases: [], work_modes: ["remote", "onsite"] },
    ],
    include_unknown_mode: false,
    relocation: true,
  },
  rules: { title_keywords: ["backend"], title_exclude: ["junior", "intern"], stop_words: ["crypto"] },
  contacts: {
    full_name: "Test User",
    email: "user@example.com",
    phone: "+34 600 000 000",
    linkedin_url: "https://linkedin.com/in/user",
    city: "Valencia, Spain",
    github_url: "https://github.com/user",
    work_authorization: "Spain / EU work authorization",
  },
};

export type Section = keyof ApiProfile;

export interface ProfileBackend {
  fetchFn: typeof fetch;
  /** Збережені на «сервері» розділи: PUT змінює лише свій. */
  state: ApiProfile;
  /** Усі PUT профілю в порядку надходження. */
  puts: { section: string; body: unknown }[];
}

export function validationError(...errors: [field: string, message: string][]): Response {
  return json(422, {
    code: "invalid_fields",
    message: errors.map(([, message]) => message).join(" "),
    field_errors: errors.map(([field, message]) => ({ field, message })),
    correlation_id: "test",
  });
}

/** `overrides` замінюють відповідь за ключем «МЕТОД /шлях» (наприклад, `PUT /api/profile/target`). */
export function profileBackend(
  initial: ApiProfile = FULL_PROFILE,
  overrides: Record<string, Handler> = {},
): ProfileBackend {
  const backend: ProfileBackend = { fetchFn: fetch, state: structuredClone(initial), puts: [] };
  const routes: Record<string, Handler> = {
    ...MEANS_LOGGED_IN,
    "GET /api/profile": () => json(200, backend.state),
  };
  for (const section of ["target", "locations", "rules", "contacts"] as const) {
    routes[`PUT /api/profile/${section}`] = (init) => {
      const body: unknown = JSON.parse(String(init?.body));
      backend.puts.push({ section, body });
      (backend.state[section] as unknown) = body;
      return json(200, backend.state);
    };
  }
  backend.fetchFn = fakeBackend({ ...routes, ...overrides });
  return backend;
}

