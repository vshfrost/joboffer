/** Спільне для тестів клієнта: підроблений бекенд на межі fetch і рендер через публічний `Client`. */
import { render } from "@testing-library/react";
import { createMemoryRouter, Link, RouterProvider, useLocation } from "react-router";
import { vi } from "vitest";

import type { CropperEngine } from "../ports/cropper";
import { Client } from "./Client";

export const ME = { id: "6f1c0a52", email: "taras@example.com", display_name: "Богдан Прикладенко" };

export function sessionBody(csrfToken: string) {
  return { user: ME, csrf_token: csrfToken };
}

export function json(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

export function noContent(): Response {
  return new Response(null, { status: 204 });
}

export type Handler = (init: RequestInit | undefined) => Response | Promise<Response>;

/** Бекенд за маршрутами «МЕТОД /шлях»; запит поза списком — помилка тесту, а не тиха відповідь. */
export function fakeBackend(routes: Record<string, Handler>) {
  return vi.fn<typeof fetch>((input, init) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.pathname : input.url;
    const key = `${init?.method ?? "GET"} ${url}`;
    const handler = routes[key];
    if (handler === undefined) {
      return Promise.reject(new Error(`Непередбачений запит: ${key}`));
    }
    return Promise.resolve(handler(init));
  });
}

export const MEANS_LOGGED_IN = { "GET /api/auth/me": () => json(200, sessionBody("csrf-me")) };

function LocationProbe() {
  const { pathname, search } = useLocation();
  return (
    <>
      <span data-testid="location">{`${pathname}${search}`}</span>
      {/* Перехід «з адресного рядка»: у MemoryRouter адреси нема, тож це посилання поза Client. */}
      <Link to="/facts">probe: факти</Link>
    </>
  );
}

export function renderClient(path: string, fetchFn: typeof fetch, cropper?: CropperEngine) {
  // Data router, як у `main.tsx`: інакше `useBlocker` недоступний.
  const router = createMemoryRouter(
    [
      {
        path: "*",
        element: (
          <>
            <Client fetchFn={fetchFn} {...(cropper === undefined ? {} : { cropper })} />
            <LocationProbe />
          </>
        ),
      },
    ],
    { initialEntries: [path] },
  );
  // `router` — щоб тести ходили історією (назад/вперед), як браузер.
  return Object.assign(render(<RouterProvider router={router} />), { router });
}
