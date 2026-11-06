import { describe, expect, test } from "vitest";

import { defaultJobId, effectText, NO_JOB_EFFECT, type Reply, type ReplyDetail } from "./replies";

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

describe("форма розбору", () => {
  function detail(job: Reply["job"]): ReplyDetail {
    return {
      reply: reply({ job }),
      text: "",
      applications: [
        { jobId: 104, title: "Senior Backend Engineer", company: "Northstar", status: "applied" },
        { jobId: 108, title: "Platform", company: "LumaPay", status: "replied" },
      ],
    };
  }

  test("вакансія наперед — збіг листа, якщо він є серед подач", () => {
    expect(defaultJobId(detail({ jobId: 108, title: null, company: null, status: "replied" }))).toBe(108);
  });

  test("збіг поза подачами власника чи його відсутність — «Не про подачу»", () => {
    expect(defaultJobId(detail({ jobId: 999, title: null, company: null, status: null }))).toBeNull();
    expect(defaultJobId(detail(null))).toBeNull();
  });

  test("ефект без вакансії: статуси не змінюються", () => {
    expect(effectText(NO_JOB_EFFECT)).toBe("Лист буде позначено розібраним без привʼязки до подачі. Статуси подач не зміняться.");
  });

  test("ефект зі зміною статусу", () => {
    expect(effectText({ current: "applied", after: "interview", changes: true })).toBe("Статус подачі: Подано → Співбесіда.");
  });

  test("ефект без зміни статусу", () => {
    expect(effectText({ current: "replied", after: "replied", changes: false })).toBe("Статус подачі не зміниться: Є відповідь.");
  });
});
