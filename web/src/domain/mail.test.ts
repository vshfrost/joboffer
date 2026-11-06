import { describe, expect, test } from "vitest";

import {
  DROP_REASON_TEXT,
  dropReasonText,
  hasMailFilters,
  itemLabel,
  KIND_LABELS,
  madridDay,
  madridTime,
  MAIL_KINDS,
  mailQueryParams,
  parseMailQuery,
  rangeText,
  senderLabel,
  senderName,
  subjectText,
  type MailCategory,
  type MailItem,
  type MailPage,
} from "./mail";

function item(overrides: Partial<MailItem> = {}): MailItem {
  return {
    id: 1,
    dropped: false,
    fromAddress: "talent@acme.example",
    fromName: "María",
    subject: "Re: next steps",
    receivedAt: "2026-10-24T13:45:00Z",
    category: "company",
    senderAuth: "verified",
    reason: null,
    ...overrides,
  };
}

describe("запит із адреси сторінки", () => {
  test("порожня адреса — перші 20 без фільтрів", () => {
    expect(parseMailQuery(new URLSearchParams(""))).toEqual({ q: "", kind: "", page: 1, perPage: 20 });
  });

  test("усе розпізнане береться як є", () => {
    const params = new URLSearchParams("q=acme&kind=dropped&page=3&per_page=50");

    expect(parseMailQuery(params)).toEqual({ q: "acme", kind: "dropped", page: 3, perPage: 50 });
  });

  test.each(MAIL_KINDS)("вид %s розпізнається", (kind) => {
    expect(parseMailQuery(new URLSearchParams({ kind })).kind).toBe(kind);
  });

  test.each([["newsletter"], ["COMPANY"], [""]])("невідомий вид «%s» — без виду", (kind) => {
    expect(parseMailQuery(new URLSearchParams({ kind })).kind).toBe("");
  });

  test.each([["0"], ["-3"], ["abc"], ["2.5"], [""]])("сторінка «%s» — перша", (page) => {
    expect(parseMailQuery(new URLSearchParams({ page })).page).toBe(1);
  });

  test.each([["10"], ["abc"], ["0"], [""]])("розмір «%s» — 20", (size) => {
    expect(parseMailQuery(new URLSearchParams({ per_page: size })).perPage).toBe(20);
  });

  test.each([20, 50, 100])("розмір %i дозволений", (size) => {
    expect(parseMailQuery(new URLSearchParams({ per_page: String(size) })).perPage).toBe(size);
  });

  test("пошук обрізається по краях", () => {
    expect(parseMailQuery(new URLSearchParams({ q: "  acme  " })).q).toBe("acme");
  });
});

describe("запит в адресу сторінки", () => {
  test("значення за замовчуванням не пишуться", () => {
    expect(mailQueryParams({ q: "", kind: "", page: 1, perPage: 20 }).toString()).toBe("");
  });

  test("усе задане пишеться", () => {
    const params = mailQueryParams({ q: "acme corp", kind: "company", page: 2, perPage: 100 });

    expect(Object.fromEntries(params)).toEqual({ q: "acme corp", kind: "company", page: "2", per_page: "100" });
  });

  test("зворотний шлях: запит → адреса → запит", () => {
    const query = { q: "дзвінок", kind: "dropped" as const, page: 4, perPage: 50 as const };

    expect(parseMailQuery(mailQueryParams(query))).toEqual(query);
  });
});

describe("фільтри", () => {
  test("пошук чи вид — це фільтри; сторінка й розмір — ні", () => {
    expect(hasMailFilters({ q: "", kind: "", page: 5, perPage: 100 })).toBe(false);
    expect(hasMailFilters({ q: "x", kind: "", page: 1, perPage: 20 })).toBe(true);
    expect(hasMailFilters({ q: "", kind: "other", page: 1, perPage: 20 })).toBe(true);
  });
});

describe("назви", () => {
  test.each<[MailCategory, string]>([
    ["company", "Компанія"],
    ["linkedin_alert", "LinkedIn: вакансії"],
    ["linkedin_application", "LinkedIn: подачі"],
    ["linkedin_message", "LinkedIn: повідомлення"],
    ["forwarding_confirmation", "Підтвердження Gmail"],
    ["suspicious", "Підозрілий"],
    ["other", "Інше"],
  ])("категорія %s — «%s»", (category, label) => {
    expect(itemLabel(item({ category }))).toBe(label);
  });

  test("відкинутий лист — «Відхилено», хоч би що було в категорії", () => {
    expect(itemLabel(item({ dropped: true, category: null, senderAuth: null, reason: "daily_limit" }))).toBe("Відхилено");
  });

  test("збережений лист без категорії — «Інше»", () => {
    expect(itemLabel(item({ category: null }))).toBe("Інше");
  });

  test("види фільтра мають назви, відхилені — «Відхилені»", () => {
    expect(MAIL_KINDS.map((kind) => KIND_LABELS[kind])).toEqual([
      "Компанія",
      "LinkedIn: вакансії",
      "LinkedIn: повідомлення",
      "Підтвердження Gmail",
      "Інше",
      "Відхилені",
    ]);
  });

  test("причини відхилення пояснені людською мовою", () => {
    expect(DROP_REASON_TEXT.daily_limit).toBe("Понад добовий ліміт: за 24 години збережено вже 100 листів.");
    expect(DROP_REASON_TEXT.retired_tag).toBe("Лист на стару адресу: пересилання в Gmail ще не оновлено.");
  });

  test("автентичність відправника", () => {
    expect(senderLabel("verified")).toEqual({ text: "Відправника підтверджено", tone: "success" });
    expect(senderLabel("unknown")).toEqual({ text: "Відправника не підтверджено", tone: "warning" });
    expect(senderLabel("failed")).toEqual({ text: "Підроблений відправник", tone: "danger" });
  });
});

describe("час за Мадридом", () => {
  test.each([
    ["2026-07-01T10:05:00Z", "2026-07-01", "12:05"], // літній час UTC+2
    ["2026-12-01T23:30:00Z", "2026-12-02", "00:30"], // зимовий UTC+1: наступний день
    ["2026-10-24T13:45:00Z", "2026-10-24", "15:45"],
  ])("%s → %s %s", (iso, day, time) => {
    expect(madridDay(iso)).toBe(day);
    expect(madridTime(iso)).toBe(time);
  });
});

describe("діапазон сторінки", () => {
  const page = (first: number, last: number, total: number): MailPage => ({
    number: 1,
    size: 20,
    total,
    first,
    last,
    hasNewer: false,
    hasOlder: false,
  });

  test("«перший–останній з усього»", () => {
    expect(rangeText(page(1, 20, 45))).toBe("1–20 з 45");
    expect(rangeText(page(41, 45, 45))).toBe("41–45 з 45");
  });

  test("порожній список", () => {
    expect(rangeText(page(1, 0, 0))).toBe("0 листів");
  });

  test("сторінка за межею списку", () => {
    expect(rangeText(page(101, 45, 45))).toBe("0 листів на цій сторінці з 45");
  });
});

describe("тексти рядка", () => {
  test("відправник: імʼя, інакше адреса, інакше позначка", () => {
    expect(senderName(item())).toBe("María");
    expect(senderName(item({ fromName: "" }))).toBe("talent@acme.example");
    expect(senderName(item({ fromName: "", fromAddress: "" }))).toBe("(без відправника)");
  });

  test("тема: як є, а порожня чи з самих пробілів — позначка", () => {
    expect(subjectText(item())).toBe("Re: next steps");
    expect(subjectText(item({ subject: "" }))).toBe("(без теми)");
    expect(subjectText(item({ subject: "   " }))).toBe("(без теми)");
  });

  test("причина відхилення — лише в відкинутого листа", () => {
    expect(dropReasonText(item({ dropped: true, reason: "retired_tag" }))).toBe(DROP_REASON_TEXT.retired_tag);
    expect(dropReasonText(item())).toBe("");
  });

  test("лист без вердикту вважається непідтвердженим", () => {
    expect(senderLabel(null)).toEqual({ text: "Відправника не підтверджено", tone: "warning" });
  });
});
