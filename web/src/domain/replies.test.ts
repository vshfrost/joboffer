import { describe, expect, test } from "vitest";

import {
  hasReplyFilters,
  jobLabel,
  jobTag,
  matchText,
  openReplyId,
  parseReplyQuery,
  QUEUE_LABELS,
  replyQueryParams,
  replyStatusLabel,
  TYPE_LABELS,
  type Confidence,
  type MatchedBy,
  type Reply,
} from "./replies";

function reply(overrides: Partial<Reply> = {}): Reply {
  return {
    id: 1,
    fromAddress: "elena@northstar.example",
    fromName: "Elena",
    subject: "Let's talk",
    receivedAt: "2026-10-24T13:40:00Z",
    senderAuth: "verified",
    job: { jobId: 104, title: "Senior Backend Engineer", company: "Northstar", status: "applied" },
    confidence: "high",
    matchedBy: "email",
    suggestedType: "invitation",
    type: null,
    reviewedAt: null,
    manualForward: null,
    ...overrides,
  };
}

describe("запит із адреси сторінки", () => {
  test("порожня адреса — «До розбору», перші 20 без пошуку", () => {
    expect(parseReplyQuery(new URLSearchParams(""))).toEqual({ queue: "matched", q: "", page: 1, perPage: 20 });
  });

  test("усі параметри розпізнаються; пошук обрізається по краях", () => {
    expect(parseReplyQuery(new URLSearchParams("queue=reviewed&q=%20acme%20&page=3&per_page=50"))).toEqual({
      queue: "reviewed",
      q: "acme",
      page: 3,
      perPage: 50,
    });
  });

  test("нерозпізнане стає значенням за замовчуванням", () => {
    expect(parseReplyQuery(new URLSearchParams("queue=nope&page=0&per_page=7"))).toEqual({ queue: "matched", q: "", page: 1, perPage: 20 });
    expect(parseReplyQuery(new URLSearchParams("page=-2")).page).toBe(1);
    expect(parseReplyQuery(new URLSearchParams("page=1.5")).page).toBe(1);
    expect(parseReplyQuery(new URLSearchParams("page=abc")).page).toBe(1);
  });

  test("пошук довший за 200 символів обрізається до 200", () => {
    expect(parseReplyQuery(new URLSearchParams(`q=${"a".repeat(250)}`)).q).toBe("a".repeat(200));
  });

  test("значення за замовчуванням в адресу не пишуться", () => {
    expect(replyQueryParams({ queue: "matched", q: "", page: 1, perPage: 20 }).toString()).toBe("");
  });

  test("усе, що не за замовчуванням, пишеться в адресу в сталому порядку", () => {
    expect(replyQueryParams({ queue: "unmatched", q: "acme corp", page: 2, perPage: 100 }).toString()).toBe("queue=unmatched&q=acme+corp&page=2&per_page=100");
  });

  test("відкрита відповідь — додатне ціле з open", () => {
    expect(openReplyId(new URLSearchParams("open=12"))).toBe(12);
    expect(openReplyId(new URLSearchParams(""))).toBeNull();
    expect(openReplyId(new URLSearchParams("open=0"))).toBeNull();
    expect(openReplyId(new URLSearchParams("open=abc"))).toBeNull();
  });

  test("скидати є що лише тоді, коли є пошук", () => {
    expect(hasReplyFilters({ queue: "reviewed", q: "", page: 3, perPage: 50 })).toBe(false);
    expect(hasReplyFilters({ queue: "matched", q: "a", page: 1, perPage: 20 })).toBe(true);
  });
});

describe("підписи", () => {
  test("черги", () => {
    expect(QUEUE_LABELS).toEqual({ matched: "До розбору", unmatched: "Без вакансії", reviewed: "Розібрані" });
  });

  test("типи відповідей", () => {
    expect(TYPE_LABELS).toEqual({
      invitation: "Запрошення",
      assignment: "Тестове завдання",
      rejection: "Відмова",
      auto_confirmation: "Автопідтвердження",
      other: "Інше",
    });
  });

  test("позначка рядка: розібраний — тип; нерозібраний — черга за наявністю вакансії", () => {
    expect(replyStatusLabel(reply({ type: "rejection", reviewedAt: "2026-10-25T09:00:00Z" }))).toBe("Відмова");
    expect(replyStatusLabel(reply())).toBe("До розбору");
    expect(replyStatusLabel(reply({ job: null }))).toBe("Без вакансії");
  });

  test("вакансія: повний підпис і короткий тег", () => {
    const job = { jobId: 104, title: "Senior Backend Engineer", company: "Northstar" };
    expect(jobLabel(job)).toBe("#104 · Northstar — Senior Backend Engineer");
    expect(jobTag(job)).toBe("#104 · Northstar");
  });

  test("вакансія без назви компанії чи посади має позначку", () => {
    expect(jobLabel({ jobId: 7, title: null, company: "Acme" })).toBe("#7 · Acme");
    expect(jobLabel({ jobId: 7, title: "Dev", company: null })).toBe("#7 · Без компанії — Dev");
    expect(jobTag({ jobId: 7, title: "Dev", company: null })).toBe("#7 · Без компанії");
  });

  test.each<[Confidence, MatchedBy, string]>([
    ["high", "thread", "Надійність зіставлення: Висока · Збіг треду"],
    ["high", "email", "Надійність зіставлення: Висока · Збіг адреси відправника з контактами подачі"],
    ["medium", "domain", "Надійність зіставлення: Середня · Збіг домену компанії"],
    ["medium", "ats", "Надійність зіставлення: Середня · Збіг ATS-відправника з назвою компанії"],
    ["low", "name", "Надійність зіставлення: Низька · Збіг назви компанії в листі"],
  ])("зіставлення %s / %s", (confidence, matchedBy, expected) => {
    expect(matchText(reply({ confidence, matchedBy }))).toBe(expected);
  });

  test("без зіставлення тексту нема", () => {
    expect(matchText(reply({ job: null, confidence: null, matchedBy: null }))).toBeNull();
  });
});
