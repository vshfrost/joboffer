import { describe, expect, test } from "vitest";

import type { MailDetail, MailList, MailQuery, MailSettings, ManualSync } from "../domain/mail";
import {
  MailNotConfiguredError,
  MailNotFoundError,
  MailSyncLimitError,
  MailUnauthorizedError,
  MailUnavailableError,
} from "../domain/mailErrors";
import type { MailApi } from "../ports/mailApi";
import { createMailServices } from "./mail";

const QUERY: MailQuery = { q: "", kind: "", page: 1, perPage: 20 };
const LIST: MailList = { items: [], page: { number: 1, size: 20, total: 0, first: 1, last: 0, hasNewer: false, hasOlder: false } };
const MANUAL: ManualSync = { limit: 2, remaining: 1, nextAt: null };
const SETTINGS: MailSettings = {
  address: "mailroom+abc@example.com",
  rotatedAt: null,
  syncedAt: null,
  syncFailed: false,
  syncError: "",
  manual: { limit: 2, remaining: 2, nextAt: null },
};
const DETAIL: MailDetail = {
  item: {
    id: 1,
    dropped: false,
    fromAddress: "a@b.c",
    fromName: "",
    subject: "s",
    receivedAt: "2026-10-24T13:45:00Z",
    category: "company",
    senderAuth: "verified",
    reason: null,
  },
  text: "hi",
  forwarding: null,
};

function succeeding(): MailApi {
  return {
    list: () => Promise.resolve(LIST),
    get: () => Promise.resolve(DETAIL),
    settings: () => Promise.resolve(SETTINGS),
    requestSync: () => Promise.resolve(MANUAL),
    rotate: () => Promise.resolve(SETTINGS),
  };
}

function failing(error: unknown): MailApi {
  const fail = () => Promise.reject(error);
  return { list: fail, get: fail, settings: fail, requestSync: fail, rotate: fail };
}

describe("успіх", () => {
  test("кожна операція віддає результат порту", async () => {
    const services = createMailServices(succeeding());

    expect(await services.list(QUERY)).toEqual({ ok: true, list: LIST });
    expect(await services.get(1)).toEqual({ ok: true, detail: DETAIL });
    expect(await services.settings()).toEqual({ ok: true, settings: SETTINGS });
    expect(await services.requestSync()).toEqual({ ok: true, manual: MANUAL });
    expect(await services.rotate()).toEqual({ ok: true, settings: SETTINGS });
  });
});

describe("проблеми, спільні для всіх операцій", () => {
  test.each([
    [new MailUnauthorizedError(), "unauthorized"],
    [new MailUnavailableError(), "unavailable"],
    [new MailNotConfiguredError(), "not-configured"],
  ] as const)("%s → %s", async (error, kind) => {
    const services = createMailServices(failing(error));

    expect(await services.list(QUERY)).toEqual({ ok: false, kind });
    expect(await services.get(1)).toEqual({ ok: false, kind });
    expect(await services.settings()).toEqual({ ok: false, kind });
    expect(await services.requestSync()).toEqual({ ok: false, kind });
    expect(await services.rotate()).toEqual({ ok: false, kind });
  });

  test("несподівана помилка не ковтається", async () => {
    await expect(createMailServices(failing(new TypeError("баг"))).list(QUERY)).rejects.toThrow("баг");
  });
});

describe("окремі випадки", () => {
  test("листа нема — окремий результат читалки", async () => {
    expect(await createMailServices(failing(new MailNotFoundError())).get(9)).toEqual({ ok: false, kind: "not-found" });
  });

  test("ліміт синку вручну несе текст для користувача", async () => {
    const services = createMailServices(failing(new MailSyncLimitError("Синк уже запитано 2 рази за 30 хв — наступний о 14:30 (Мадрид).")));

    expect(await services.requestSync()).toEqual({
      ok: false,
      kind: "limit",
      message: "Синк уже запитано 2 рази за 30 хв — наступний о 14:30 (Мадрид).",
    });
  });
});
