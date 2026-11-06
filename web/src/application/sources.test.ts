import { afterEach, describe, expect, test, vi } from "vitest";

import type { FilteredJob, RefreshState, Source, SourcesOverview } from "../domain/sources";
import {
  SourcesFilteredChangedError,
  SourcesNotFoundError,
  SourcesRefreshLimitError,
  SourcesUnauthorizedError,
  SourcesUnavailableError,
  SourcesValidationError,
} from "../domain/sourcesErrors";
import type { SourcesApi } from "../ports/sourcesApi";
import { createSourcesServices } from "./sources";

const SOURCE: Source = { kind: "company", id: "c-1", platform: "greenhouse", name: "Northstar", key: "northstar-eng", enabled: true, lastRun: null };
const REFRESH: RefreshState = { limit: 2, remaining: 1, nextAt: null, lastRunAt: null };
const OVERVIEW: SourcesOverview = { companies: [SOURCE], feeds: [], refresh: REFRESH, filteredOutCount: 0 };
const JOBS: FilteredJob[] = [{ number: 204, title: "Junior", company: "Cedar", reason: "excluded" }];

afterEach(() => {
  vi.restoreAllMocks();
});

/** Порт, у якого кожен метод кидає `error` (або віддає значення). */
function failing(error: unknown): SourcesApi {
  const fail = () => Promise.reject(error);
  return { overview: fail, add: fail, setEnabled: fail, remove: fail, requestRefresh: fail, filtered: fail, dismiss: fail };
}

function working(): SourcesApi {
  return {
    overview: () => Promise.resolve(OVERVIEW),
    add: () => Promise.resolve(SOURCE),
    setEnabled: (_kind, _id, enabled) => Promise.resolve({ ...SOURCE, enabled }),
    remove: () => Promise.resolve(),
    requestRefresh: () => Promise.resolve(REFRESH),
    filtered: () => Promise.resolve(JOBS),
    dismiss: (numbers) => Promise.resolve(numbers.length),
  };
}

describe("успіх", () => {
  test("кожна операція віддає результат порту", async () => {
    const services = createSourcesServices(working());

    expect(await services.overview()).toEqual({ ok: true, overview: OVERVIEW });
    expect(await services.add({ kind: "feed", source: "dou", query: "category=Python" })).toEqual({ ok: true, source: SOURCE });
    expect(await services.setEnabled("company", "c-1", false)).toEqual({ ok: true, source: { ...SOURCE, enabled: false } });
    expect(await services.remove("company", "c-1")).toEqual({ ok: true });
    expect(await services.requestRefresh()).toEqual({ ok: true, refresh: REFRESH });
    expect(await services.filtered()).toEqual({ ok: true, jobs: JOBS });
    expect(await services.dismiss([204, 218])).toEqual({ ok: true, dismissed: 2 });
  });
});

describe("проблеми", () => {
  test.each([
    ["сесія завершилась", new SourcesUnauthorizedError(), "unauthorized"],
    ["сервер недоступний", new SourcesUnavailableError("x"), "unavailable"],
  ] as const)("%s → kind %s у кожній операції", async (_, error, kind) => {
    const services = createSourcesServices(failing(error));

    for (const outcome of [
      await services.overview(),
      await services.add({ kind: "feed", source: "dou", query: "q" }),
      await services.setEnabled("feed", "f", true),
      await services.remove("feed", "f"),
      await services.requestRefresh(),
      await services.filtered(),
      await services.dismiss([1]),
    ]) {
      expect(outcome).toEqual({ ok: false, kind });
    }
  });

  test("невідома помилка не ковтається", async () => {
    const services = createSourcesServices(failing(new TypeError("баг")));

    await expect(services.overview()).rejects.toThrow("баг");
    await expect(services.add({ kind: "feed", source: "dou", query: "q" })).rejects.toThrow("баг");
    await expect(services.setEnabled("feed", "f", true)).rejects.toThrow("баг");
    await expect(services.remove("feed", "f")).rejects.toThrow("баг");
    await expect(services.requestRefresh()).rejects.toThrow("баг");
    await expect(services.filtered()).rejects.toThrow("баг");
    await expect(services.dismiss([1])).rejects.toThrow("баг");
  });

  test("422 при додаванні → invalid з текстами біля полів", async () => {
    const services = createSourcesServices(failing(new SourcesValidationError("Слаг не той", { slug: "Слаг не той" })));

    expect(await services.add({ kind: "company", platform: "ashby", slug: "!", name: "" })).toEqual({
      ok: false,
      kind: "invalid",
      message: "Слаг не той",
      fieldErrors: { slug: "Слаг не той" },
    });
  });

  test("404 при вимкненні й видаленні → not-found", async () => {
    const services = createSourcesServices(failing(new SourcesNotFoundError()));

    expect(await services.setEnabled("company", "c-1", true)).toEqual({ ok: false, kind: "not-found" });
    expect(await services.remove("company", "c-1")).toEqual({ ok: false, kind: "not-found" });
  });

  test("409 при приховуванні → changed", async () => {
    const services = createSourcesServices(failing(new SourcesFilteredChangedError()));

    expect(await services.dismiss([204])).toEqual({ ok: false, kind: "changed" });
  });
});

describe("ліміт «Оновити зараз»", () => {
  test("429 → limit із текстом і моментом: зараз + Retry-After", async () => {
    vi.spyOn(Date, "now").mockReturnValue(Date.parse("2026-07-01T10:00:00Z"));
    const services = createSourcesServices(failing(new SourcesRefreshLimitError("Наступне о 12:25 (Мадрид).", 1500)));

    expect(await services.requestRefresh()).toEqual({ ok: false, kind: "limit", message: "Наступне о 12:25 (Мадрид).", nextAt: "2026-07-01T10:25:00.000Z" });
  });

  test("429 без Retry-After → nextAt = null", async () => {
    const services = createSourcesServices(failing(new SourcesRefreshLimitError("Забагато", null)));

    expect(await services.requestRefresh()).toEqual({ ok: false, kind: "limit", message: "Забагато", nextAt: null });
  });
});
