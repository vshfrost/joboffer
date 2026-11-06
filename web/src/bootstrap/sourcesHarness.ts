/** Спільне для тестів «Джерел»: відкрити сторінку на підробленому бекенді й знайти рядки списку. */
import { screen, waitFor, within } from "@testing-library/react";
import { expect } from "vitest";

import type { SourcesBackend } from "./sourcesBackend";
import { renderClient } from "./testClient";
import { setViewport } from "./viewport";

/** `settled` (за замовчуванням) чекає, поки список перестане вантажитись; `false` — повертає одразу після заголовка (для перевірки скелетона). */
export async function openSources(backend: SourcesBackend, path = "/sources", viewport: "desktop" | "mobile" = "desktop", settled = true) {
  setViewport(viewport);
  renderClient(path, backend.fetchFn);
  await screen.findByRole("heading", { level: 1, name: "Джерела вакансій" });
  if (settled) {
    await waitFor(() => expect(screen.queryByRole("status", { name: "Завантажуємо джерела" })).toBeNull());
  }
}

/** Список джерел: таблиця на широкому екрані, список карток на вузькому. */
export async function sourceList(): Promise<HTMLElement> {
  return screen.findByLabelText("Список джерел");
}

/** Кнопки розгортання (назви джерел) у порядку списку. */
export async function sourceButtons(): Promise<HTMLElement[]> {
  const list = await sourceList();
  return Array.from(list.querySelectorAll<HTMLElement>("button[aria-expanded]"));
}

export async function sourceNames(): Promise<string[]> {
  return (await sourceButtons()).map((button) => button.textContent ?? "");
}

/** Рядок таблиці чи картка джерела за назвою. */
export async function rowOf(name: string): Promise<HTMLElement> {
  const button = within(await sourceList()).getByRole("button", { name });
  const row = button.closest<HTMLElement>("tr, li");
  if (row === null) {
    throw new Error(`Рядка джерела «${name}» нема`);
  }
  return row;
}

/** Розгорнуті деталі джерела (область, на яку вказує `aria-controls` кнопки). */
export async function detailsOf(name: string): Promise<HTMLElement> {
  const button = within(await sourceList()).getByRole("button", { name });
  const id = button.getAttribute("aria-controls");
  const details = id === null ? null : document.getElementById(id);
  if (details === null) {
    throw new Error(`Деталей джерела «${name}» нема`);
  }
  return details;
}
