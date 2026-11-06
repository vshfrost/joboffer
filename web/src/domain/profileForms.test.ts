import { describe, expect, test } from "vitest";

import type { Locations, Rules, Target } from "./profile";
import {
  formToLocations,
  formToRules,
  formToTarget,
  locationsToForm,
  newLocationRow,
  rulesToForm,
  targetToForm,
  uniqueCount,
  type LocationRowForm,
  type LocationsForm,
  type TargetForm,
} from "./profileForms";

const TARGET: Target = {
  roles: ["Backend Engineer", "SRE"],
  seniority: ["senior", "lead"],
  minSalaryEur: 65000,
  targetDomains: ["fintech", "payments"],
};

const FORM: TargetForm = {
  roles: "Backend Engineer\nSRE",
  seniority: ["senior", "lead"],
  minSalary: "65000",
  targetDomains: "fintech\npayments",
};

const SALARY_ERROR = "Мінімальна зарплата — ціле число в EUR, напр. 60000.";

function parse(overrides: Partial<TargetForm>) {
  return formToTarget({ ...FORM, ...overrides });
}

describe("targetToForm", () => {
  test("ролі й галузі — по одній на рядок, зарплата — число рядком", () => {
    expect(targetToForm(TARGET)).toEqual(FORM);
  });

  test("порожня ціль дає порожні поля, а не «null»", () => {
    const empty: Target = { roles: [], seniority: [], minSalaryEur: null, targetDomains: [] };
    expect(targetToForm(empty)).toEqual({ roles: "", seniority: [], minSalary: "", targetDomains: "" });
  });
});

describe("formToTarget", () => {
  test("форма з цілі й назад дає ту саму ціль", () => {
    expect(formToTarget(targetToForm(TARGET))).toEqual({ ok: true, value: TARGET });
  });

  test("рядки обрізаються, порожні відкидаються", () => {
    const parsed = parse({ roles: "  SRE  \n\n   \nBackend Engineer\n", targetDomains: "\n fintech " });
    expect(parsed).toEqual({
      ok: true,
      value: { ...TARGET, roles: ["SRE", "Backend Engineer"], targetDomains: ["fintech"] },
    });
  });

  test.each([
    ["65 000", 65000],
    ["65_000", 65000],
    ["  70000  ", 70000],
    ["0", 0],
  ])("зарплата «%s» — це %d", (minSalary, expected) => {
    expect(parse({ minSalary })).toMatchObject({ ok: true, value: { minSalaryEur: expected } });
  });

  test("порожня зарплата — не вказано", () => {
    expect(parse({ minSalary: "   " })).toMatchObject({ ok: true, value: { minSalaryEur: null } });
  });

  test.each(["abc", "-5", "65.5", "65 тис", "1e5", "99999999999999999999"])(
    "зарплата «%s» — помилка біля поля",
    (minSalary) => {
      expect(parse({ minSalary })).toEqual({ ok: false, errors: { min_salary_eur: SALARY_ERROR } });
    },
  );
});

const LOCATIONS: Locations = {
  workModes: ["remote", "hybrid"],
  locations: [
    { place: "Valencia", aliases: ["Валенсія", "Valéncia"], workModes: ["hybrid"] },
    { place: "Madrid", aliases: [], workModes: ["remote", "onsite"] },
  ],
  includeUnknownMode: false,
  relocation: true,
};

describe("locationsToForm / formToLocations", () => {
  test("рядки форми повторюють місця у збереженому порядку, синоніми — по одному на рядок", () => {
    const form = locationsToForm(LOCATIONS);
    expect(form.workModes).toEqual(["remote", "hybrid"]);
    expect(form.includeUnknownMode).toBe(false);
    expect(form.relocation).toBe(true);
    expect(form.rows.map(({ place, aliases, workModes }) => ({ place, aliases, workModes }))).toEqual([
      { place: "Valencia", aliases: "Валенсія\nValéncia", workModes: ["hybrid"] },
      { place: "Madrid", aliases: "", workModes: ["remote", "onsite"] },
    ]);
  });

  test("ключі рядків різні, щоб React і фокус розрізняли рядки", () => {
    const keys = locationsToForm(LOCATIONS).rows.map((row) => row.key);
    expect(new Set(keys).size).toBe(2);
  });

  test("форма з локацій і назад дає ті самі локації", () => {
    expect(formToLocations(locationsToForm(LOCATIONS))).toEqual(LOCATIONS);
  });

  test("формати впорядковано як у домені: remote, hybrid, onsite", () => {
    const form = locationsToForm(LOCATIONS);
    const shuffled = {
      ...form,
      workModes: ["onsite", "remote"] as LocationsForm["workModes"],
      rows: form.rows.map((row) => ({ ...row, workModes: ["onsite", "hybrid", "remote"] as LocationsForm["workModes"] })),
    };
    const value = formToLocations(shuffled);
    expect(value.workModes).toEqual(["remote", "onsite"]);
    expect(value.locations.map((location) => location.workModes)).toEqual([
      ["remote", "hybrid", "onsite"],
      ["remote", "hybrid", "onsite"],
    ]);
  });

  test("синоніми обрізаються, порожні рядки відкидаються", () => {
    const form = locationsToForm(LOCATIONS);
    const edited = { ...form, rows: [{ ...(form.rows[0] as LocationRowForm), aliases: "  Валенсія \n\n  \nVLC" }] };
    expect(formToLocations(edited).locations[0]?.aliases).toEqual(["Валенсія", "VLC"]);
  });

  test("порожній рядок форми іде на сервер як є: індекс помилки збігається з рядком", () => {
    const form = locationsToForm(LOCATIONS);
    const blank: LocationRowForm = { key: "new-1", place: "", aliases: "", workModes: [] };
    const value = formToLocations({ ...form, rows: [...form.rows, blank] });
    expect(value.locations).toHaveLength(3);
    expect(value.locations[2]).toEqual({ place: "", aliases: [], workModes: [] });
  });

  test("порожні локації — порожня форма, а нові рядки мають власні ключі", () => {
    const empty: Locations = { workModes: [], locations: [], includeUnknownMode: true, relocation: false };
    expect(locationsToForm(empty)).toEqual({ workModes: [], rows: [], includeUnknownMode: true, relocation: false });
    expect(newLocationRow("new-1")).toEqual({ key: "new-1", place: "", aliases: "", workModes: [] });
  });
});

describe("rulesToForm / formToRules", () => {
  const RULES: Rules = { titleKeywords: ["backend", "python"], titleExclude: ["junior"], stopWords: [] };

  test("списки — по одному слову на рядок", () => {
    expect(rulesToForm(RULES)).toEqual({ titleKeywords: "backend\npython", titleExclude: "junior", stopWords: "" });
  });

  test("форма з правил і назад дає ті самі правила", () => {
    expect(formToRules(rulesToForm(RULES))).toEqual(RULES);
  });

  test("рядки обрізаються, порожні відкидаються", () => {
    const value = formToRules({ titleKeywords: " a \n\n b ", titleExclude: "\n", stopWords: "  " });
    expect(value).toEqual({ titleKeywords: ["a", "b"], titleExclude: [], stopWords: [] });
  });
});

describe("uniqueCount", () => {
  test.each([
    ["", 0],
    ["  \n \n", 0],
    ["a\nb\nc", 3],
    ["Python\npython\n PYTHON ", 1],
    ["a\n\nb\n", 2],
  ])("«%s» → %d", (text, expected) => {
    expect(uniqueCount(text)).toBe(expected);
  });
});
