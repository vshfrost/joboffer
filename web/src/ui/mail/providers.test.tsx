/** Захисні перевірки провайдерів пошти й гонки відповідей, які важко відтворити через повний клієнт. */
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { ReactNode } from "react";

import type { MailServices, RequestSyncOutcome } from "../../application/mail";
import type { MailSettings } from "../../domain/mail";
import { MailProvider, useMail } from "./MailProvider";
import { MailServicesProvider, useMailServices } from "./MailServices";

// React друкує кинуту помилку хука в console.error: тут вона очікувана.
beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => undefined);
});
afterEach(() => {
  vi.restoreAllMocks();
});

const SETTINGS: MailSettings = {
  address: "mailroom+abc@example.com",
  rotatedAt: null,
  syncedAt: null,
  syncFailed: false,
  syncError: "",
  manual: { limit: 2, remaining: 2, nextAt: null },
};

function servicesWith(overrides: Partial<MailServices>): MailServices {
  const unused = () => Promise.reject(new Error("не очікувано"));
  return { list: unused, get: unused, settings: () => Promise.resolve({ ok: true, settings: SETTINGS }), requestSync: unused, rotate: unused, ...overrides };
}

function wrapper(services: MailServices) {
  return ({ children }: { children: ReactNode }) => (
    <MailServicesProvider services={services}>
      <MailProvider>{children}</MailProvider>
    </MailServicesProvider>
  );
}

test("useMailServices без провайдера", () => {
  expect(() => renderHook(() => useMailServices())).toThrow("Пошта потребує MailServicesProvider");
});

test("useMail без провайдера", () => {
  const services = servicesWith({});

  expect(() =>
    renderHook(() => useMail(), { wrapper: ({ children }) => <MailServicesProvider services={services}>{children}</MailServicesProvider> }),
  ).toThrow("Пошта потребує MailProvider");
});

test("два запити синку в одному кадрі йдуть на сервер один раз", async () => {
  let release: (outcome: RequestSyncOutcome) => void = () => {};
  const requestSync = vi.fn<MailServices["requestSync"]>(
    () =>
      new Promise((resolve) => {
        release = resolve;
      }),
  );
  const { result } = renderHook(() => useMail(), { wrapper: wrapper(servicesWith({ requestSync })) });
  await waitFor(() => expect(result.current.state.status).toBe("ready"));

  await act(async () => {
    void result.current.requestSync();
    void result.current.requestSync();
  });
  await act(async () => {
    release({ ok: true, manual: { limit: 2, remaining: 1, nextAt: null } });
  });

  expect(requestSync).toHaveBeenCalledTimes(1);
  expect(result.current.queued).toBe(true);
  expect(result.current.manualAfterSync).toEqual({ limit: 2, remaining: 1, nextAt: null });
});

test("відповідь на застарілі налаштування не затирає свіжіші", async () => {
  const releases: ((outcome: { ok: true; settings: MailSettings }) => void)[] = [];
  const settings = vi.fn<MailServices["settings"]>(
    () =>
      new Promise((resolve) => {
        releases.push(resolve);
      }),
  );
  const { result } = renderHook(() => useMail(), { wrapper: wrapper(servicesWith({ settings })) });

  await act(async () => {
    result.current.reload();
  });
  await act(async () => {
    releases[1]?.({ ok: true, settings: { ...SETTINGS, address: "fresh@example.com" } });
  });
  await act(async () => {
    releases[0]?.({ ok: true, settings: { ...SETTINGS, address: "stale@example.com" } });
  });

  expect(result.current.state).toEqual({ status: "ready", settings: { ...SETTINGS, address: "fresh@example.com" } });
});
