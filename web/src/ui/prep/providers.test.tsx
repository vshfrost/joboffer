/** Захисні перевірки провайдера сервісів підготовки й гонки відповідей, які важко відтворити через повний клієнт. */
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { PrepServicesProvider, usePrepServices } from "./PrepServices";
import { useLoaded, type Loaded } from "./useLoaded";

// `load` має бути стабільним (у сторінках — useCallback), тож тут він завжди сталий.
// React друкує кинуту помилку хука в console.error: тут вона очікувана.
beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => undefined);
});
afterEach(() => {
  vi.restoreAllMocks();
});

/** Відкладена відповідь: тест сам вирішує, коли вона прийде. */
function deferred<T>() {
  let resolve: (value: T) => void = () => {};
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

type Result = Loaded<string, "unavailable">;

test("usePrepServices без провайдера", () => {
  expect(() => renderHook(() => usePrepServices())).toThrow("Підготовка потребує PrepServicesProvider");
});

test("usePrepServices з провайдером віддає сервіси", () => {
  const services = {} as ReturnType<typeof usePrepServices>;
  const { result } = renderHook(() => usePrepServices(), { wrapper: ({ children }) => <PrepServicesProvider services={services}>{children}</PrepServicesProvider> });

  expect(result.current).toBe(services);
});

test("спершу «вантажиться», потім дані; збій — помилка з видом проблеми", async () => {
  const loadOk = () => Promise.resolve<Result>({ ok: true, value: "теми" });
  const loadFailed = () => Promise.resolve<Result>({ ok: false, kind: "unavailable" });
  const ok = renderHook(() => useLoaded(loadOk));
  expect(ok.result.current.state).toEqual({ status: "loading" });
  await waitFor(() => expect(ok.result.current.state).toEqual({ status: "ready", data: "теми" }));

  const failed = renderHook(() => useLoaded(loadFailed));
  await waitFor(() => expect(failed.result.current.state).toEqual({ status: "error", problem: "unavailable" }));
});

test("відповідь на застарілий запит не затирає свіжіший", async () => {
  const pending = [deferred<Result>(), deferred<Result>()];
  let call = 0;
  const load = vi.fn(() => (pending[call++] as ReturnType<typeof deferred<Result>>).promise);
  const { result } = renderHook(() => useLoaded(load));

  await act(async () => {
    result.current.reload();
  });
  await act(async () => {
    pending[1]?.resolve({ ok: true, value: "свіже" });
  });
  await act(async () => {
    pending[0]?.resolve({ ok: true, value: "застаріле" });
  });

  expect(result.current.state).toEqual({ status: "ready", data: "свіже" });
});

test("відповідь після розмонтування нікуди не потрапляє", async () => {
  const gate = deferred<Result>();
  const load = () => gate.promise;
  const { result, unmount } = renderHook(() => useLoaded(load));
  unmount();

  await act(async () => {
    gate.resolve({ ok: true, value: "запізно" });
  });

  expect(result.current.state).toEqual({ status: "loading" });
});

test("set підміняє дані після дії, не вантажачи їх знову", async () => {
  const load = vi.fn(() => Promise.resolve<Result>({ ok: true, value: "до" }));
  const { result } = renderHook(() => useLoaded(load));
  await waitFor(() => expect(result.current.state.status).toBe("ready"));

  act(() => result.current.set("після"));

  expect(result.current.state).toEqual({ status: "ready", data: "після" });
  expect(load).toHaveBeenCalledTimes(1);
});
