/** Спільне для тестів «Підготовки»: відкрити сторінку на підробленому бекенді й знайти рядки реєстру. */
import { screen, waitFor, within } from "@testing-library/react";
import { expect } from "vitest";

import type { PrepBackend } from "./prepBackend";
import { connectPrompts } from "./promptsBackend";
import { renderClient } from "./testClient";
import { setViewport } from "./viewport";

/** `settled` (за замовчуванням) чекає, поки реєстр перестане вантажитись; `false` — повертає одразу після заголовка (для перевірки скелетона). */
export async function openPrep(backend: PrepBackend, path = "/prep", viewport: "desktop" | "mobile" = "desktop", settled = true) {
  setViewport(viewport);
  connectPrompts(backend);
  const view = renderClient(path, backend.fetchFn);
  await screen.findByRole("heading", { level: 1, name: "Підготовка" });
  if (settled) {
    await waitFor(() => expect(screen.queryByRole("status", { name: "Завантажуємо теми" })).toBeNull());
  }
  return view;
}

/** Сторінка теми: чекає оболонку, а потім кінця завантаження теми. */
export async function openTopic(backend: PrepBackend, path: string, viewport: "desktop" | "mobile" = "desktop", settled = true) {
  setViewport(viewport);
  connectPrompts(backend);
  const view = renderClient(path, backend.fetchFn);
  await screen.findByRole("navigation", { name: "Головна навігація" });
  if (settled) {
    await waitFor(() => expect(screen.queryByRole("status", { name: "Завантажуємо тему" })).toBeNull());
  }
  return view;
}

/** Реєстр тем: таблиця на широкому екрані, список карток на вузькому. */
export async function topicList(): Promise<HTMLElement> {
  return screen.findByLabelText("Список тем");
}

/** Посилання на теми (їхні назви) у порядку реєстру. */
export async function topicLinks(): Promise<HTMLElement[]> {
  const list = await topicList();
  return within(list)
    .getAllByRole("link")
    .filter((link) => /^\/prep\/\d+$/.test(link.getAttribute("href") ?? ""));
}

export async function topicTitles(): Promise<string[]> {
  return (await topicLinks()).map((link) => link.textContent ?? "");
}

/** Рядок таблиці чи картка теми за назвою. */
export async function rowOf(title: string): Promise<HTMLElement> {
  const link = within(await topicList()).getByRole("link", { name: title });
  const row = link.closest<HTMLElement>("tr, li");
  if (row === null) {
    throw new Error(`Рядка теми «${title}» нема`);
  }
  return row;
}

/** Розкривний крок теми (`<details>`) за назвою кроку. */
export function stepOf(title: string): HTMLDetailsElement {
  const details = screen.getByText(title, { selector: "strong" }).closest("details");
  if (details === null) {
    throw new Error(`Кроку «${title}» нема`);
  }
  return details;
}
