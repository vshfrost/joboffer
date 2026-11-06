import { describe, expect, test } from "vitest";

import type { Profile } from "../domain/profile";
import { ProfileUnavailableError, ProfileValidationError } from "../domain/profileErrors";
import type { ProfileApi } from "../ports/profileApi";
import { createProfileServices } from "./profile";

const PROFILE: Profile = {
  target: { roles: ["SRE"], seniority: [], minSalaryEur: null, targetDomains: [] },
  locations: { workModes: [], locations: [], includeUnknownMode: true, relocation: false },
  rules: { titleKeywords: [], titleExclude: [], stopWords: [] },
  contacts: { fullName: "", email: "", phone: "", linkedinUrl: "", city: "", githubUrl: "", workAuthorization: "" },
};

/** Порт, що завжди кидає `failure` (або віддає профіль, якщо нічого не кидати). */
function api(failure?: Error): ProfileApi {
  return {
    get() {
      return failure === undefined ? Promise.resolve(PROFILE) : Promise.reject(failure);
    },
    save() {
      return failure === undefined ? Promise.resolve(PROFILE) : Promise.reject(failure);
    },
  };
}

describe("завантаження профілю", () => {
  test("профіль із порту — успіх", async () => {
    expect(await createProfileServices(api()).load()).toEqual({ ok: true, profile: PROFILE });
  });

  test("недоступний сервер — результат без винятку", async () => {
    expect(await createProfileServices(api(new ProfileUnavailableError("503"))).load()).toEqual({ ok: false });
  });

  test("несподівана помилка не ковтається", async () => {
    await expect(createProfileServices(api(new RangeError("bug"))).load()).rejects.toThrow("bug");
  });
});

describe("збереження розділу", () => {
  const target = PROFILE.target;

  test("успіх повертає профіль від сервера", async () => {
    expect(await createProfileServices(api()).save("target", target)).toEqual({ ok: true, profile: PROFILE });
  });

  test("422 — помилки полів, окрема копія", async () => {
    const error = new ProfileValidationError({ min_salary_eur: "Мінімальна зарплата не може бути від'ємною." });
    const outcome = await createProfileServices(api(error)).save("target", target);
    expect(outcome).toEqual({
      ok: false,
      kind: "invalid",
      fieldErrors: { min_salary_eur: "Мінімальна зарплата не може бути від'ємною." },
    });
    if (!outcome.ok && outcome.kind === "invalid") {
      expect(outcome.fieldErrors).not.toBe(error.fieldErrors);
    }
  });

  test("недоступний сервер — результат без винятку", async () => {
    expect(await createProfileServices(api(new ProfileUnavailableError("503"))).save("target", target)).toEqual({
      ok: false,
      kind: "unavailable",
    });
  });

  test("несподівана помилка не ковтається", async () => {
    await expect(createProfileServices(api(new RangeError("bug"))).save("target", target)).rejects.toThrow("bug");
  });
});
