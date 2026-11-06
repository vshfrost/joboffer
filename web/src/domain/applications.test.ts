import { describe, expect, test } from "vitest";

import {
  ACTIVE_STATUSES,
  APPLICATION_STATUSES,
  applicationInput,
  CLOSED_STATUSES,
  draftOf,
  emptyDraft,
  isClosed,
  MOVE_LABELS,
  sameDraft,
  STATUS_LABELS,
  STATUS_TONES,
  type Application,
  type ApplicationDraft,
} from "./applications";

const APPLICATION: Application = {
  jobId: 7,
  status: "applied",
  appliedOn: "2026-10-22",
  channel: "ats",
  ats: "lever",
  companyDomains: ["acme.com", "jobs.acme.com"],
  companyEmails: ["hr@acme.com"],
  statusChangedAt: "2026-10-22T09:00:00Z",
  allowedTransitions: ["replied", "interview", "offer", "rejected", "withdrawn"],
};

const DRAFT: ApplicationDraft = { channel: "email", appliedOn: "2026-10-22", ats: "", domains: "", emails: "" };

describe("статуси", () => {
  test("шість статусів воронки в порядку сервера", () => {
    expect(APPLICATION_STATUSES).toEqual(["applied", "replied", "interview", "offer", "rejected", "withdrawn"]);
  });

  test("«У процесі» — рівно чотири активні статуси, закриті — два", () => {
    expect(ACTIVE_STATUSES).toEqual(["applied", "replied", "interview", "offer"]);
    expect(CLOSED_STATUSES).toEqual(["rejected", "withdrawn"]);
  });

  test("кожен статус має текстовий підпис і підпис кнопки переходу", () => {
    expect(STATUS_LABELS).toEqual({
      applied: "Подано",
      replied: "Є відповідь",
      interview: "Співбесіда",
      offer: "Оффер",
      rejected: "Відмова",
      withdrawn: "Відкликано",
    });
    expect(MOVE_LABELS.interview).toBe("Перейти до співбесіди");
    expect(MOVE_LABELS.withdrawn).toBe("Відкликати подачу");
  });

  test("кольори Pine: applied — інформація, replied і interview — увага, offer — успіх, rejected — помилка, withdrawn — нейтральний", () => {
    expect(STATUS_TONES).toEqual({
      applied: "info",
      replied: "warning",
      interview: "warning",
      offer: "success",
      rejected: "danger",
      withdrawn: "neutral",
    });
  });
});

describe("форма «Я подався»", () => {
  test("порожня форма не має каналу й ATS, а дата — сьогодні за Мадридом", () => {
    expect(emptyDraft(new Date("2026-10-22T10:00:00Z"))).toEqual({ channel: "", appliedOn: "2026-10-22", ats: "", domains: "", emails: "" });
  });

  test("біля опівночі за UTC у Мадриді вже наступний день", () => {
    expect(emptyDraft(new Date("2026-10-22T22:30:00Z")).appliedOn).toBe("2026-10-23");
  });

  test("форма зі збережених даних: домени й адреси по одному в рядку, без ATS — порожньо", () => {
    expect(draftOf(APPLICATION)).toEqual({
      channel: "ats",
      appliedOn: "2026-10-22",
      ats: "lever",
      domains: "acme.com\njobs.acme.com",
      emails: "hr@acme.com",
    });
    expect(draftOf({ ...APPLICATION, ats: null, companyDomains: [], companyEmails: [] })).toMatchObject({ ats: "", domains: "", emails: "" });
  });

  test("порівняння чернеток — за кожним полем", () => {
    expect(sameDraft(DRAFT, { ...DRAFT })).toBe(true);
    for (const patch of [{ channel: "ats" }, { appliedOn: "2026-10-21" }, { ats: "lever" }, { domains: "a.com" }, { emails: "a@a.com" }] as const) {
      expect(sameDraft(DRAFT, { ...DRAFT, ...patch })).toBe(false);
    }
  });

  test("на сервер йдуть значення як є, домени й адреси — списками без порожніх рядків", () => {
    expect(applicationInput({ channel: "ats", appliedOn: "2026-10-22", ats: "lever", domains: " acme.com \n\n jobs.acme.com\n", emails: "hr@acme.com,\ncv@acme.com" })).toEqual({
      channel: "ats",
      appliedOn: "2026-10-22",
      ats: "lever",
      companyDomains: ["acme.com", "jobs.acme.com"],
      companyEmails: ["hr@acme.com", "cv@acme.com"],
    });
  });

  test("порожні необов'язкові поля — порожні рядок і списки", () => {
    expect(applicationInput(DRAFT)).toEqual({ channel: "email", appliedOn: "2026-10-22", ats: "", companyDomains: [], companyEmails: [] });
  });
});

describe("закрита подача", () => {
  test("закрита лише та, з якої нікуди рухатись", () => {
    expect(isClosed(APPLICATION)).toBe(false);
    expect(isClosed({ ...APPLICATION, status: "offer", allowedTransitions: ["withdrawn"] })).toBe(false);
    expect(isClosed({ ...APPLICATION, status: "rejected", allowedTransitions: [] })).toBe(true);
  });
});
