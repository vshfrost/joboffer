import { describe, expect, test, vi } from "vitest";

import {
  MailNotConfiguredError,
  MailNotFoundError,
  MailSyncLimitError,
  MailUnauthorizedError,
  MailUnavailableError,
} from "../domain/mailErrors";
import { createApiClient } from "./apiClient";
import { createHttpMailApi } from "./httpMailApi";

const ROW = {
  id: 7,
  dropped: false,
  untrusted_from_address: "talent@acme.example",
  untrusted_from_name: "María",
  untrusted_subject: "Re: next steps",
  received_at: "2026-10-24T13:45:00Z",
  category: "company",
  sender_auth: "verified",
  reason: null,
};
const DROPPED_ROW = { ...ROW, id: 3, dropped: true, untrusted_from_name: "", category: null, sender_auth: null, reason: "daily_limit" };
const PAGE = { number: 2, size: 50, total: 120, first: 51, last: 100, has_newer: true, has_older: true };
const SETTINGS = {
  address: "mailroom+abc@example.com",
  rotated_at: "2026-10-20T08:00:00Z",
  synced_at: "2026-10-24T13:45:00Z",
  sync_failed: true,
  sync_error: "Gmail відповів 500 на profile.",
  manual: { limit: 2, remaining: 1, next_at: "2026-10-24T14:30:00Z" },
};

/** Межа — fetch: відповідь або збій мережі. */
function apiWith(respond: (input: string, init: RequestInit | undefined) => Response | Promise<Response>) {
  const fetchFn = vi.fn<typeof fetch>((input, init) => Promise.resolve(respond(String(input), init)));
  const client = createApiClient(fetchFn, "/api");
  client.setCsrfToken("csrf-1");
  return { api: createHttpMailApi(client), fetchFn };
}

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

describe("«Вхідні»", () => {
  test("GET /mail з параметрами лише там, де вони не за замовчуванням", async () => {
    const { api, fetchFn } = apiWith(() => json(200, { items: [], page: PAGE }));

    await api.list({ q: "acme corp", kind: "dropped", page: 2, perPage: 50 });
    await api.list({ q: "", kind: "", page: 1, perPage: 20 });

    expect(fetchFn.mock.calls[0]?.[0]).toBe("/api/mail?q=acme+corp&kind=dropped&page=2&per_page=50");
    expect(fetchFn.mock.calls[1]?.[0]).toBe("/api/mail");
    expect(fetchFn.mock.calls[0]?.[1]?.method).toBe("GET");
  });

  test("рядки й сторінка — у моделі клієнта; недовірені поля віддаються як є", async () => {
    const { api } = apiWith(() => json(200, { items: [ROW, DROPPED_ROW], page: PAGE }));

    const list = await api.list({ q: "", kind: "", page: 2, perPage: 50 });

    expect(list.page).toEqual({ number: 2, size: 50, total: 120, first: 51, last: 100, hasNewer: true, hasOlder: true });
    expect(list.items[0]).toEqual({
      id: 7,
      dropped: false,
      fromAddress: "talent@acme.example",
      fromName: "María",
      subject: "Re: next steps",
      receivedAt: "2026-10-24T13:45:00Z",
      category: "company",
      senderAuth: "verified",
      reason: null,
    });
    expect(list.items[1]).toMatchObject({ id: 3, dropped: true, category: null, senderAuth: null, reason: "daily_limit" });
  });

  test.each([
    [401, MailUnauthorizedError],
    [503, MailNotConfiguredError],
    [403, MailUnavailableError],
    [500, MailUnavailableError],
  ])("відповідь %i — окрема помилка", async (status, error) => {
    const { api } = apiWith(() => json(status, { code: "x", message: "m" }));

    await expect(api.list({ q: "", kind: "", page: 1, perPage: 20 })).rejects.toBeInstanceOf(error);
  });

  test.each([
    ["не об'єкт", []],
    ["без items", { page: PAGE }],
    ["items не список", { items: {}, page: PAGE }],
    ["без page", { items: [] }],
    ["сторінка без числа", { items: [], page: { ...PAGE, total: "120" } }],
    ["сторінка без прапорця", { items: [], page: { ...PAGE, has_older: "yes" } }],
    ["рядок не об'єкт", { items: [1], page: PAGE }],
    ["рядок без id", { items: [{ ...ROW, id: "7" }], page: PAGE }],
    ["рядок без теми", { items: [{ ...ROW, untrusted_subject: 5 }], page: PAGE }],
    ["невідома категорія", { items: [{ ...ROW, category: "newsletter" }], page: PAGE }],
    ["невідомий вердикт", { items: [{ ...ROW, sender_auth: "maybe" }], page: PAGE }],
    ["невідома причина", { items: [{ ...ROW, reason: "spam" }], page: PAGE }],
    ["відкинутий лист без причини", { items: [{ ...ROW, dropped: true, reason: null }], page: PAGE }],
    ["прапорець dropped не булевий", { items: [{ ...ROW, dropped: "no" }], page: PAGE }],
    ["без часу", { items: [{ ...ROW, received_at: null }], page: PAGE }],
  ])("відповідь не за контрактом (%s) — збій", async (_name, body) => {
    const { api } = apiWith(() => json(200, body));

    await expect(api.list({ q: "", kind: "", page: 1, perPage: 20 })).rejects.toBeInstanceOf(MailUnavailableError);
  });

  test("збій мережі — недоступно, з текстом збою", async () => {
    const { api } = apiWith(() => Promise.reject(new Error("offline")));

    await expect(api.list({ q: "", kind: "", page: 1, perPage: 20 })).rejects.toMatchObject({ message: expect.stringContaining("Мережа") });
  });
});

describe("лист", () => {
  const DETAIL = { ...ROW, untrusted_text: "Hi\n\nBest", forwarding: null };

  test("GET /mail/<id>: рядок, текст і код пересилання", async () => {
    const forwarding = {
      code: "418306552",
      link_only: false,
      untrusted_requested_by: "a@b.c",
      received_at: "2026-10-23T09:00:00Z",
      current: true,
    };
    const { api, fetchFn } = apiWith(() => json(200, { ...DETAIL, forwarding }));

    const detail = await api.get(7);

    expect(fetchFn.mock.calls[0]?.[0]).toBe("/api/mail/7");
    expect(detail.text).toBe("Hi\n\nBest");
    expect(detail.item.subject).toBe("Re: next steps");
    expect(detail.forwarding).toEqual({
      code: "418306552",
      linkOnly: false,
      requestedBy: "a@b.c",
      receivedAt: "2026-10-23T09:00:00Z",
      current: true,
    });
  });

  test("звичайний лист — без пересилання", async () => {
    const { api } = apiWith(() => json(200, DETAIL));

    expect((await api.get(7)).forwarding).toBeNull();
  });

  test.each([
    [404, MailNotFoundError],
    [401, MailUnauthorizedError],
    [503, MailNotConfiguredError],
    [500, MailUnavailableError],
  ])("відповідь %i — окрема помилка", async (status, error) => {
    const { api } = apiWith(() => json(status, {}));

    await expect(api.get(7)).rejects.toBeInstanceOf(error);
  });

  test.each([
    ["без тексту", { ...DETAIL, untrusted_text: 1 }],
    ["пересилання не об'єкт", { ...DETAIL, forwarding: 5 }],
    ["пересилання без коду", { ...DETAIL, forwarding: { code: 1, link_only: true, untrusted_requested_by: "", received_at: "t", current: true } }],
    ["пересилання без прапорців", { ...DETAIL, forwarding: { code: "", link_only: "x", untrusted_requested_by: "", received_at: "t", current: true } }],
    ["пересилання без адреси", { ...DETAIL, forwarding: { code: "", link_only: true, untrusted_requested_by: 1, received_at: "t", current: true } }],
    ["пересилання без часу", { ...DETAIL, forwarding: { code: "", link_only: true, untrusted_requested_by: "", received_at: 1, current: true } }],
    ["пересилання без current", { ...DETAIL, forwarding: { code: "", link_only: true, untrusted_requested_by: "", received_at: "t", current: 1 } }],
    ["не об'єкт", "x"],
  ])("відповідь не за контрактом (%s) — збій", async (_name, body) => {
    const { api } = apiWith(() => json(200, body));

    await expect(api.get(7)).rejects.toBeInstanceOf(MailUnavailableError);
  });
});

describe("налаштування", () => {
  test("GET /mail/settings: адреса, синк, ліміт синку вручну", async () => {
    const { api, fetchFn } = apiWith(() => json(200, SETTINGS));

    const settings = await api.settings();

    expect(fetchFn.mock.calls[0]?.[0]).toBe("/api/mail/settings");
    expect(settings).toEqual({
      address: "mailroom+abc@example.com",
      rotatedAt: "2026-10-20T08:00:00Z",
      syncedAt: "2026-10-24T13:45:00Z",
      syncFailed: true,
      syncError: "Gmail відповів 500 на profile.",
      manual: { limit: 2, remaining: 1, nextAt: "2026-10-24T14:30:00Z" },
    });
  });

  test("нічого ще не було: дати порожні", async () => {
    const { api } = apiWith(() =>
      json(200, { ...SETTINGS, rotated_at: null, synced_at: null, sync_failed: false, sync_error: "", manual: { limit: 2, remaining: 2, next_at: null } }),
    );

    const settings = await api.settings();

    expect([settings.rotatedAt, settings.syncedAt, settings.manual.nextAt]).toEqual([null, null, null]);
  });

  test.each([
    [401, MailUnauthorizedError],
    [503, MailNotConfiguredError],
    [500, MailUnavailableError],
  ])("відповідь %i — окрема помилка", async (status, error) => {
    const { api } = apiWith(() => json(status, {}));

    await expect(api.settings()).rejects.toBeInstanceOf(error);
  });

  test.each([
    ["не об'єкт", 1],
    ["адреса не рядок", { ...SETTINGS, address: 1 }],
    ["дата не рядок", { ...SETTINGS, synced_at: 5 }],
    ["rotated_at не рядок", { ...SETTINGS, rotated_at: 5 }],
    ["sync_failed не булевий", { ...SETTINGS, sync_failed: "no" }],
    ["sync_error не рядок", { ...SETTINGS, sync_error: 1 }],
    ["без ліміту", { ...SETTINGS, manual: null }],
    ["ліміт не число", { ...SETTINGS, manual: { limit: "2", remaining: 1, next_at: null } }],
    ["next_at не рядок", { ...SETTINGS, manual: { limit: 2, remaining: 1, next_at: 3 } }],
  ])("відповідь не за контрактом (%s) — збій", async (_name, body) => {
    const { api } = apiWith(() => json(200, body));

    await expect(api.settings()).rejects.toBeInstanceOf(MailUnavailableError);
  });
});

describe("синк вручну й нова адреса", () => {
  test("POST /mail/sync: ліміт у моделі клієнта, з CSRF", async () => {
    const { api, fetchFn } = apiWith(() => json(200, { limit: 2, remaining: 1, next_at: null }));

    const manual = await api.requestSync();

    expect(manual).toEqual({ limit: 2, remaining: 1, nextAt: null });
    expect(fetchFn.mock.calls[0]?.[0]).toBe("/api/mail/sync");
    expect(fetchFn.mock.calls[0]?.[1]?.method).toBe("POST");
    expect(new Headers(fetchFn.mock.calls[0]?.[1]?.headers).get("X-CSRF-Token")).toBe("csrf-1");
  });

  test("429: текст ліміту від сервера", async () => {
    const text = "Синк уже запитано 2 рази за 30 хв — наступний о 14:30 (Мадрид).";
    const { api } = apiWith(() => json(429, { code: "manual_sync_limit", message: text, field_errors: [] }));

    await expect(api.requestSync()).rejects.toMatchObject({ message: text });
    await expect(api.requestSync()).rejects.toBeInstanceOf(MailSyncLimitError);
  });

  test("429 без тексту — загальний текст", async () => {
    const { api } = apiWith(() => json(429, {}));

    await expect(api.requestSync()).rejects.toMatchObject({ message: "Синк уже запитано забагато разів. Спробуй пізніше." });
  });

  test.each([
    [401, MailUnauthorizedError],
    [503, MailNotConfiguredError],
    [500, MailUnavailableError],
  ])("синк: відповідь %i — окрема помилка", async (status, error) => {
    const { api } = apiWith(() => json(status, {}));

    await expect(api.requestSync()).rejects.toBeInstanceOf(error);
  });

  test("синк: відповідь не за контрактом — збій", async () => {
    const { api } = apiWith(() => json(200, { limit: 2 }));

    await expect(api.requestSync()).rejects.toBeInstanceOf(MailUnavailableError);
  });

  test("POST /mail/address/rotate: нові налаштування", async () => {
    const { api, fetchFn } = apiWith(() => json(200, SETTINGS));

    const settings = await api.rotate();

    expect(settings.address).toBe("mailroom+abc@example.com");
    expect(fetchFn.mock.calls[0]?.[0]).toBe("/api/mail/address/rotate");
    expect(fetchFn.mock.calls[0]?.[1]?.method).toBe("POST");
  });

  test.each([
    [401, MailUnauthorizedError],
    [503, MailNotConfiguredError],
    [500, MailUnavailableError],
  ])("ротація: відповідь %i — окрема помилка", async (status, error) => {
    const { api } = apiWith(() => json(status, {}));

    await expect(api.rotate()).rejects.toBeInstanceOf(error);
  });
});

describe("збій транспорту", () => {
  test("не-помилка від клієнта теж стає «недоступно» із загальним текстом", async () => {
    const client = { request: () => Promise.reject("boom"), setCsrfToken: () => undefined };

    await expect(createHttpMailApi(client).settings()).rejects.toMatchObject({ message: "Мережа недоступна" });
  });
});
