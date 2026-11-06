import { describe, expect, test } from "vitest";

import { retryMinutes, safeNextPath } from "./session";

describe("safeNextPath", () => {
  test.each(["/vacancies", "/vacancies?tab=archived", "/vacancies/42#notes", "/profile"])(
    "внутрішній шлях %s лишається як є",
    (path) => {
      expect(safeNextPath(path)).toBe(path);
    },
  );

  test.each([
    { raw: "https://evil.example", why: "абсолютна адреса" },
    { raw: "//evil", why: "адреса без схеми" },
    { raw: "//evil.example/path", why: "адреса без схеми зі шляхом" },
    { raw: "/\\evil.example", why: "зворотний слеш після слеша" },
    { raw: "\\\\evil.example", why: "два зворотні слеші" },
    { raw: "/\t/evil.example", why: "табуляція, яку браузер прибирає з адреси" },
    { raw: "/\n/evil.example", why: "перенос рядка, який браузер прибирає з адреси" },
    { raw: "javascript:alert(1)", why: "схема javascript" },
    { raw: "vacancies", why: "відносний шлях" },
    { raw: "", why: "порожній рядок" },
    { raw: null, why: "параметра нема" },
    { raw: undefined, why: "параметра нема (undefined)" },
  ])("$why ($raw) веде на головну", ({ raw }) => {
    expect(safeNextPath(raw)).toBe("/");
  });

  test.each(["/login", "/login?next=/vacancies", "/login/", "/login#x"])(
    "сам екран входу (%s) не може бути метою — інакше вхід зациклиться",
    (raw) => {
      expect(safeNextPath(raw)).toBe("/");
    },
  );
});

describe("retryMinutes", () => {
  test.each([
    [600, 10],
    [599, 10],
    [601, 11],
    [61, 2],
    [60, 1],
    [1, 1],
    [0, 1],
  ])("%i с → ~%i хв (округлення вгору, не менше 1)", (seconds, minutes) => {
    expect(retryMinutes(seconds)).toBe(minutes);
  });
});
