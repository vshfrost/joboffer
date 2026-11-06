import type { Contacts, Locations, Profile, ProfileSection, Rules, SearchLocation, Target } from "../domain/profile";
import { SENIORITIES, WORK_MODES, type Seniority, type WorkMode } from "../domain/profile";
import { ProfileUnavailableError, ProfileValidationError } from "../domain/profileErrors";
import type { ProfileApi } from "../ports/profileApi";
import type { ApiClient } from "./apiClient";

const CONTRACT = "Відповідь сервера не за контрактом";

export function createHttpProfileApi(client: ApiClient): ProfileApi {
  return {
    async get() {
      const response = await requestOrUnavailable(() => client.request("GET", "/profile"));
      if (response.status !== 200) {
        throw new ProfileUnavailableError(`Профіль: відповідь ${response.status}`);
      }
      return readProfile(response.body);
    },

    async save(section, value) {
      const response = await requestOrUnavailable(() => client.request("PUT", `/profile/${section}`, toBody(section, value)));
      if (response.status === 200) {
        return readProfile(response.body);
      }
      if (response.status === 422) {
        throw new ProfileValidationError(readFieldErrors(response.body));
      }
      throw new ProfileUnavailableError(`Збереження: відповідь ${response.status}`);
    },
  };
}

async function requestOrUnavailable<T>(call: () => Promise<T>): Promise<T> {
  try {
    return await call();
  } catch (error) {
    throw new ProfileUnavailableError(error instanceof Error ? error.message : "Мережа недоступна");
  }
}

function toBody<S extends ProfileSection>(section: S, value: Profile[S]): unknown {
  switch (section) {
    case "target": {
      const target = value as Target;
      return {
        roles: target.roles,
        seniority: target.seniority,
        min_salary_eur: target.minSalaryEur,
        target_domains: target.targetDomains,
      };
    }
    case "locations": {
      const locations = value as Locations;
      return {
        work_modes: locations.workModes,
        locations: locations.locations.map((location) => ({
          place: location.place,
          aliases: location.aliases,
          work_modes: location.workModes,
        })),
        include_unknown_mode: locations.includeUnknownMode,
        relocation: locations.relocation,
      };
    }
    case "rules": {
      const rules = value as Rules;
      return { title_keywords: rules.titleKeywords, title_exclude: rules.titleExclude, stop_words: rules.stopWords };
    }
    case "contacts": {
      const contacts = value as Contacts;
      return {
        full_name: contacts.fullName,
        email: contacts.email,
        phone: contacts.phone,
        linkedin_url: contacts.linkedinUrl,
        city: contacts.city,
        github_url: contacts.githubUrl,
        work_authorization: contacts.workAuthorization,
      };
    }
  }
}

/** `{field_errors: [{field, message}]}` → поле → текст; без розпізнаних полів — збій контракту. */
function readFieldErrors(body: unknown): Record<string, string> {
  const items = isRecord(body) ? body["field_errors"] : undefined;
  if (!Array.isArray(items)) {
    throw new ProfileUnavailableError(CONTRACT);
  }
  const errors: Record<string, string> = {};
  for (const item of items) {
    if (!isRecord(item) || typeof item["field"] !== "string" || typeof item["message"] !== "string") {
      throw new ProfileUnavailableError(CONTRACT);
    }
    errors[item["field"]] ??= item["message"];
  }
  if (Object.keys(errors).length === 0) {
    throw new ProfileUnavailableError(CONTRACT);
  }
  return errors;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function strings(value: unknown): string[] {
  if (!Array.isArray(value) || !value.every((item) => typeof item === "string")) {
    throw new ProfileUnavailableError(CONTRACT);
  }
  return value as string[];
}

function text(value: unknown): string {
  if (typeof value !== "string") {
    throw new ProfileUnavailableError(CONTRACT);
  }
  return value;
}

function flag(value: unknown): boolean {
  if (typeof value !== "boolean") {
    throw new ProfileUnavailableError(CONTRACT);
  }
  return value;
}

function members<T extends string>(value: unknown, allowed: readonly T[]): T[] {
  const items = strings(value);
  if (!items.every((item) => (allowed as readonly string[]).includes(item))) {
    throw new ProfileUnavailableError(CONTRACT);
  }
  return items as T[];
}

function section(body: Record<string, unknown>, key: string): Record<string, unknown> {
  const value = body[key];
  if (!isRecord(value)) {
    throw new ProfileUnavailableError(CONTRACT);
  }
  return value;
}

function readProfile(body: unknown): Profile {
  if (!isRecord(body)) {
    throw new ProfileUnavailableError(CONTRACT);
  }
  const target = section(body, "target");
  const locations = section(body, "locations");
  const rules = section(body, "rules");
  const contacts = section(body, "contacts");
  const salary = target["min_salary_eur"];
  if (salary !== null && typeof salary !== "number") {
    throw new ProfileUnavailableError(CONTRACT);
  }
  const places = locations["locations"];
  if (!Array.isArray(places)) {
    throw new ProfileUnavailableError(CONTRACT);
  }
  return {
    target: {
      roles: strings(target["roles"]),
      seniority: members<Seniority>(target["seniority"], SENIORITIES),
      minSalaryEur: salary ?? null,
      targetDomains: strings(target["target_domains"]),
    },
    locations: {
      workModes: members<WorkMode>(locations["work_modes"], WORK_MODES),
      locations: places.map((place): SearchLocation => {
        if (!isRecord(place)) {
          throw new ProfileUnavailableError(CONTRACT);
        }
        return {
          place: text(place["place"]),
          aliases: strings(place["aliases"]),
          workModes: members<WorkMode>(place["work_modes"], WORK_MODES),
        };
      }),
      includeUnknownMode: flag(locations["include_unknown_mode"]),
      relocation: flag(locations["relocation"]),
    },
    rules: {
      titleKeywords: strings(rules["title_keywords"]),
      titleExclude: strings(rules["title_exclude"]),
      stopWords: strings(rules["stop_words"]),
    },
    contacts: {
      fullName: text(contacts["full_name"]),
      email: text(contacts["email"]),
      phone: text(contacts["phone"]),
      linkedinUrl: text(contacts["linkedin_url"]),
      city: text(contacts["city"]),
      githubUrl: text(contacts["github_url"]),
      workAuthorization: text(contacts["work_authorization"]),
    },
  };
}
