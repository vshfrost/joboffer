import { describe, expect, test } from "vitest";

import type { Contacts, Locations, Rules, Target } from "./profile";
import {
  groupThousands,
  levelLabel,
  modeLabel,
  plural,
  summarizeContacts,
  summarizeLocations,
  summarizeRules,
  summarizeTarget,
} from "./profileSummary";

describe("plural", () => {
  test.each([
    [1, "слово"],
    [2, "слова"],
    [4, "слова"],
    [5, "слів"],
    [11, "слів"],
    [12, "слів"],
    [14, "слів"],
    [21, "слово"],
    [22, "слова"],
    [25, "слів"],
    [111, "слів"],
    [0, "слів"],
  ])("%d → %s", (count, expected) => {
    expect(plural(count, "слово", "слова", "слів")).toBe(expected);
  });
});

describe("groupThousands", () => {
  test.each([
    [999, "999"],
    [1000, "1 000"],
    [65000, "65 000"],
    [1234567, "1 234 567"],
  ])("%d → %s", (value, expected) => {
    expect(groupThousands(value)).toBe(expected);
  });
});

test("підписи форматів і рівнів", () => {
  expect(["remote", "hybrid", "onsite"].map((mode) => modeLabel(mode as "remote"))).toEqual(["Remote", "Hybrid", "Офіс"]);
  expect(levelLabel("principal")).toBe("Principal");
});

describe("підсумки розділів", () => {
  test("порожня ціль — порожній стан", () => {
    const empty: Target = { roles: [], seniority: [], minSalaryEur: null, targetDomains: [] };
    expect(summarizeTarget(empty)).toEqual({ empty: true, lines: ["Ціль ще не задано"] });
  });

  test("ціль лише із зарплатою не має порожнього рядка рівнів", () => {
    const pay: Target = { roles: [], seniority: [], minSalaryEur: 0, targetDomains: [] };
    expect(summarizeTarget(pay)).toEqual({ empty: false, lines: ["від 0 € брутто / рік"] });
  });

  test("ролі — перші дві й «ще N»", () => {
    const target: Target = { roles: ["A", "B", "C", "D"], seniority: ["lead"], minSalaryEur: null, targetDomains: [] };
    expect(summarizeTarget(target).lines).toEqual(["A · B · ще 2", "Lead"]);
  });

  test("локації: перші дві через «/», решта — «ще N»", () => {
    const locations: Locations = {
      workModes: [],
      locations: [
        { place: "A", aliases: [], workModes: ["remote"] },
        { place: "B", aliases: [], workModes: ["hybrid", "onsite"] },
        { place: "C", aliases: [], workModes: ["remote"] },
      ],
      includeUnknownMode: true,
      relocation: false,
    };
    expect(summarizeLocations(locations).lines).toEqual(["A · Remote / B · Hybrid, Офіс / ще 1"]);
    expect(summarizeLocations({ ...locations, locations: [] })).toEqual({ empty: true, lines: ["Локації ще не додано"] });
  });

  test("правила: лічильники з правильною множиною, порожні — порожній стан", () => {
    const rules: Rules = { titleKeywords: ["a"], titleExclude: ["a", "b", "c", "d", "e"], stopWords: ["a", "b"] };
    expect(summarizeRules(rules).lines).toEqual(["1 слово для пошуку · 5 виключень · 2 стоп-слова"]);
    expect(summarizeRules({ titleKeywords: [], titleExclude: [], stopWords: [] })).toEqual({
      empty: true,
      lines: ["Правила ще не задано"],
    });
  });

  test("контакти: ім’я й email, або лише те, що є", () => {
    const base: Contacts = { fullName: "", email: "", phone: "", linkedinUrl: "", city: "", githubUrl: "", workAuthorization: "" };
    expect(summarizeContacts({ ...base, email: "a@b.c" }).lines).toEqual(["a@b.c"]);
    expect(summarizeContacts({ ...base, fullName: "N", email: "a@b.c" }).lines).toEqual(["N", "a@b.c"]);
    expect(summarizeContacts(base)).toEqual({ empty: true, lines: ["Контакти не вказано"] });
  });
});
