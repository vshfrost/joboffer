/** Гонки відповідей хука подачі: застаріла відповідь не затирає свіжу. Відпускаємо `load` вручну, без таймерів. */
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { expect, test, vi } from "vitest";

import type { ApplicationsServices, LoadApplicationOutcome } from "../../application/applications";
import type { Application } from "../../domain/applications";
import { ApplicationsServicesProvider } from "./ApplicationsServices";
import { useApplication } from "./useApplication";

function applicationFor(jobId: number): Application {
  return {
    jobId,
    status: "applied",
    appliedOn: "2026-10-01",
    channel: "linkedin",
    ats: null,
    companyDomains: [],
    companyEmails: [],
    statusChangedAt: "2026-10-01T09:00:00Z",
    allowedTransitions: ["replied", "rejected", "withdrawn"],
  };
}

/** `load` лишається в очікуванні, доки тест не відпустить його відповідь. */
function gatedServices() {
  const releases: ((outcome: LoadApplicationOutcome) => void)[] = [];
  const load = vi.fn<ApplicationsServices["load"]>(
    () =>
      new Promise((resolve) => {
        releases.push(resolve);
      }),
  );
  const unused = () => Promise.reject(new Error("не очікувано"));
  const services: ApplicationsServices = { load, save: unused, move: unused };
  function release(index: number, outcome: LoadApplicationOutcome) {
    const resolve = releases[index];
    if (resolve === undefined) {
      throw new Error(`запит ${index} ще не надійшов`);
    }
    resolve(outcome);
  }
  return { services, load, release };
}

function wrapperFor(services: ApplicationsServices) {
  return ({ children }: { children: ReactNode }) => <ApplicationsServicesProvider services={services}>{children}</ApplicationsServicesProvider>;
}

test("відповідь сервера стає станом ready з подачею", async () => {
  const { services, release } = gatedServices();
  const { result } = renderHook(() => useApplication(7), { wrapper: wrapperFor(services) });
  expect(result.current.state).toEqual({ status: "loading" });

  await act(async () => {
    release(0, { ok: true, application: applicationFor(7) });
  });

  expect(result.current.state).toEqual({ status: "ready", application: applicationFor(7) });
});

test("збій завантаження стає станом error", async () => {
  const { services, release } = gatedServices();
  const { result } = renderHook(() => useApplication(7), { wrapper: wrapperFor(services) });

  await act(async () => {
    release(0, { ok: false });
  });

  expect(result.current.state).toEqual({ status: "error" });
});

test("відповідь на попередню вакансію, що прийшла після зміни вакансії, не затирає свіжу", async () => {
  const { services, load, release } = gatedServices();
  const { result, rerender } = renderHook(({ jobId }) => useApplication(jobId), { wrapper: wrapperFor(services), initialProps: { jobId: 7 } });
  rerender({ jobId: 8 });
  await waitFor(() => expect(load).toHaveBeenCalledTimes(2));

  await act(async () => {
    release(1, { ok: true, application: applicationFor(8) });
  });
  await act(async () => {
    release(0, { ok: true, application: applicationFor(7) });
  });

  expect(result.current.state).toEqual({ status: "ready", application: applicationFor(8) });
});

test("відповідь на запит до повтору не затирає відповідь на повтор", async () => {
  const { services, load, release } = gatedServices();
  const { result } = renderHook(() => useApplication(7), { wrapper: wrapperFor(services) });
  act(() => result.current.reload());
  await waitFor(() => expect(load).toHaveBeenCalledTimes(2));

  await act(async () => {
    release(1, { ok: true, application: applicationFor(7) });
  });
  await act(async () => {
    release(0, { ok: false });
  });

  expect(result.current.state).toEqual({ status: "ready", application: applicationFor(7) });
});

test("set підставляє подачу з відповіді сервера без нового запиту", async () => {
  const { services, load, release } = gatedServices();
  const { result } = renderHook(() => useApplication(7), { wrapper: wrapperFor(services) });
  await act(async () => {
    release(0, { ok: true, application: null });
  });

  act(() => result.current.set({ ...applicationFor(7), status: "replied" }));

  expect(result.current.state).toEqual({ status: "ready", application: { ...applicationFor(7), status: "replied" } });
  expect(load).toHaveBeenCalledTimes(1);
});
