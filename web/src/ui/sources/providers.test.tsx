/** Захисні перевірки провайдера сервісів джерел і гонки відповідей, які важко відтворити через повний клієнт. */
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { ReactNode } from "react";

import type { FilteredOutcome, LoadSourcesOutcome, SourcesServices } from "../../application/sources";
import type { FilteredJob, Source, SourcesOverview } from "../../domain/sources";
import { SourcesServicesProvider, useSourcesServices } from "./SourcesServices";
import { useFilteredJobs } from "./useFilteredJobs";
import { useSourcesOverview } from "./useSourcesOverview";

// React друкує кинуту помилку хука в console.error: тут вона очікувана.
beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => undefined);
});
afterEach(() => {
  vi.restoreAllMocks();
});

const SOURCE: Source = { kind: "company", id: "c-1", platform: "greenhouse", name: "Northstar", key: "northstar-eng", enabled: true, lastRun: null };
const OVERVIEW: SourcesOverview = { companies: [SOURCE], feeds: [], refresh: { limit: 2, remaining: 2, nextAt: null, lastRunAt: null }, filteredOutCount: 0 };
const JOBS: FilteredJob[] = [
  { number: 204, title: "Junior", company: "Cedar", reason: "excluded" },
  { number: 218, title: "Senior", company: "Aster", reason: "location" },
];

function servicesWith(overrides: Partial<SourcesServices>): SourcesServices {
  const unused = () => Promise.reject(new Error("не очікувано"));
  return {
    overview: () => Promise.resolve({ ok: true, overview: OVERVIEW }),
    add: unused,
    setEnabled: unused,
    remove: unused,
    requestRefresh: unused,
    filtered: () => Promise.resolve({ ok: true, jobs: JOBS }),
    dismiss: unused,
    ...overrides,
  };
}

function wrapper(services: SourcesServices) {
  return ({ children }: { children: ReactNode }) => <SourcesServicesProvider services={services}>{children}</SourcesServicesProvider>;
}

/** Відкладена відповідь: тест сам вирішує, коли вона прийде. */
function deferred<T>() {
  let resolve: (value: T) => void = () => {};
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

test("useSourcesServices без провайдера", () => {
  expect(() => renderHook(() => useSourcesServices())).toThrow("Джерела потребують SourcesServicesProvider");
});

test("відповідь на застарілий огляд не затирає свіжіший", async () => {
  const pending = [deferred<LoadSourcesOutcome>(), deferred<LoadSourcesOutcome>()];
  let call = 0;
  const overview = vi.fn<SourcesServices["overview"]>(() => (pending[call++] as ReturnType<typeof deferred<LoadSourcesOutcome>>).promise);
  const { result } = renderHook(() => useSourcesOverview(), { wrapper: wrapper(servicesWith({ overview })) });

  await act(async () => {
    result.current.reload();
  });
  await act(async () => {
    pending[1]?.resolve({ ok: true, overview: { ...OVERVIEW, filteredOutCount: 7 } });
  });
  await act(async () => {
    pending[0]?.resolve({ ok: true, overview: { ...OVERVIEW, filteredOutCount: 1 } });
  });

  expect(result.current.state).toEqual({ status: "ready", overview: { ...OVERVIEW, filteredOutCount: 7 } });
});

test("правка огляду, поки він ще вантажиться, нічого не робить", async () => {
  const gate = deferred<LoadSourcesOutcome>();
  const { result } = renderHook(() => useSourcesOverview(), { wrapper: wrapper(servicesWith({ overview: () => gate.promise })) });

  await act(async () => {
    result.current.patch((overview) => ({ ...overview, filteredOutCount: 99 }));
  });

  expect(result.current.state).toEqual({ status: "loading" });
});

test("мовчазне оновлення лишає список на екрані, а збій перетворює його на помилку", async () => {
  const outcomes: LoadSourcesOutcome[] = [{ ok: true, overview: OVERVIEW }, { ok: false, kind: "unavailable" }];
  const gate = deferred<LoadSourcesOutcome>();
  let call = 0;
  const overview = vi.fn<SourcesServices["overview"]>(() => (call++ === 0 ? Promise.resolve(outcomes[0] as LoadSourcesOutcome) : gate.promise));
  const { result } = renderHook(() => useSourcesOverview(), { wrapper: wrapper(servicesWith({ overview })) });
  await waitFor(() => expect(result.current.state.status).toBe("ready"));

  let refetching: Promise<void> = Promise.resolve();
  await act(async () => {
    refetching = result.current.refetch();
  });
  expect(result.current.state.status).toBe("ready");
  await act(async () => {
    gate.resolve(outcomes[1] as LoadSourcesOutcome);
    await refetching;
  });

  expect(result.current.state).toEqual({ status: "error", problem: "unavailable" });
});

test("відповідь на застарілий перелік «не проходять фільтр» не затирає свіжіший", async () => {
  const pending = [deferred<FilteredOutcome>(), deferred<FilteredOutcome>()];
  let call = 0;
  const filtered = vi.fn<SourcesServices["filtered"]>(() => (pending[call++] as ReturnType<typeof deferred<FilteredOutcome>>).promise);
  const { result } = renderHook(() => useFilteredJobs(), { wrapper: wrapper(servicesWith({ filtered })) });

  await act(async () => {
    result.current.reload();
  });
  await act(async () => {
    pending[1]?.resolve({ ok: true, jobs: [JOBS[1] as FilteredJob] });
  });
  await act(async () => {
    pending[0]?.resolve({ ok: true, jobs: JOBS });
  });

  expect(result.current.state).toEqual({ status: "ready", jobs: [JOBS[1]] });
});

test("прибрати сховані номери, поки перелік ще вантажиться, нічого не робить", async () => {
  const gate = deferred<FilteredOutcome>();
  const { result } = renderHook(() => useFilteredJobs(), { wrapper: wrapper(servicesWith({ filtered: () => gate.promise })) });

  await act(async () => {
    result.current.remove([204]);
  });

  expect(result.current.state).toEqual({ status: "loading" });
});

test("мовчазне оновлення переліку лишає його на екрані до відповіді", async () => {
  const gate = deferred<FilteredOutcome>();
  let call = 0;
  const filtered = vi.fn<SourcesServices["filtered"]>(() => (call++ === 0 ? Promise.resolve({ ok: true, jobs: JOBS }) : gate.promise));
  const { result } = renderHook(() => useFilteredJobs(), { wrapper: wrapper(servicesWith({ filtered })) });
  await waitFor(() => expect(result.current.state.status).toBe("ready"));

  let refetching: Promise<void> = Promise.resolve();
  await act(async () => {
    refetching = result.current.refetch();
  });
  expect(result.current.state.status).toBe("ready");
  await act(async () => {
    gate.resolve({ ok: true, jobs: [JOBS[0] as FilteredJob] });
    await refetching;
  });

  expect(result.current.state).toEqual({ status: "ready", jobs: [JOBS[0]] });
});
