/** Картка «Фото для CV» в огляді хабу профілю: справжні дані замість «З’явиться пізніше». */
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { apiPhoto, photosBackend } from "./photosBackend";
import { renderClient } from "./testClient";

async function openOverview(photos = [apiPhoto(1, { label: "Ділове" }), apiPhoto(2, { created_at: "2026-10-22T08:00:00Z" })], overrides = {}) {
  const backend = photosBackend(photos, overrides);
  renderClient("/profile", backend.fetchFn);
  await screen.findByRole("link", { name: /Кар’єрна ціль/ });
  return backend;
}

function photoCard() {
  const element = screen.getByRole("heading", { level: 2, name: "Фото для CV" }).closest("li");
  if (element === null) {
    throw new Error("Картки «Фото для CV» нема в списку");
  }
  return within(element);
}

describe("картка фото", () => {
  test("кількість і день, коли додано останнє (за Мадридом), підказка й дія", async () => {
    await openOverview();

    expect(await photoCard().findByText("2 фото")).toBeDefined();
    expect(photoCard().getByText("Останнє додано 2026-10-22")).toBeDefined();
    expect(photoCard().getByText("Галерея, підписи та кадрування фото")).toBeDefined();
    expect(photoCard().getByText("Відкрити галерею")).toBeDefined();
    expect(photoCard().queryByText("З’явиться пізніше")).toBeNull();
  });

  test("веде в розділ фото", async () => {
    await openOverview();

    expect(photoCard().getByRole("link").getAttribute("href")).toBe("/profile/photos");
  });

  test("без фото — окремий стан, а не «0 фото»", async () => {
    await openOverview([]);

    expect(await photoCard().findByText("Фото ще не додано")).toBeDefined();
    expect(photoCard().queryByText(/0 фото/)).toBeNull();
    expect(photoCard().getByRole("link").getAttribute("href")).toBe("/profile/photos");
  });

  test("поки фото вантажаться — статус у картці", async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    await openOverview(undefined, { list: () => gate.then(() => new Response(JSON.stringify({ photos: [], suggested_photo_id: null }), { status: 200 })) });

    expect(photoCard().getByRole("status", { name: "Завантажуємо фото…" })).toBeDefined();
    release();
    expect(await photoCard().findByText("Фото ще не додано")).toBeDefined();
  });

  test("збій завантаження: повідомлення в картці, інші картки живі", async () => {
    await openOverview(undefined, { list: () => new Response("{}", { status: 500 }) });

    expect(await photoCard().findByText("Не вдалося завантажити фото.")).toBeDefined();
    expect(screen.getByRole("link", { name: /Кар’єрна ціль/ })).toBeDefined();
    expect(photoCard().getByRole("link").getAttribute("href")).toBe("/profile/photos");
  });

  test("сесія завершилась: окреме повідомлення в картці", async () => {
    await openOverview(undefined, { list: () => new Response("{}", { status: 401 }) });

    expect(await photoCard().findByText("Сесія завершилась. Увійди знову.")).toBeDefined();
  });

  test("профіль не вантажить фото, поки не відкрито огляд чи розділ фото", async () => {
    const backend = photosBackend([apiPhoto(1)]);
    renderClient("/profile/target", backend.fetchFn);
    await screen.findByRole("heading", { level: 1, name: "Кар’єрна ціль" });

    expect(backend.listRequests).toBe(0);
  });
});

describe("перехід у розділ і назад", () => {
  test("картка відкриває розділ з фокусом на «Додати фото»", async () => {
    await openOverview();
    const user = userEvent.setup();

    await user.click(await photoCard().findByRole("link"));

    await screen.findByRole("heading", { level: 1, name: "Фото для CV" });
    expect(document.activeElement).toBe(await screen.findByRole("button", { name: "Додати фото" }));
  });

  test("повернення в огляд повертає фокус на картку фото", async () => {
    await openOverview();
    const user = userEvent.setup();
    await user.click(await photoCard().findByRole("link"));
    await screen.findByRole("heading", { level: 1, name: "Фото для CV" });

    await user.click(screen.getByRole("link", { name: /Огляд профілю/ }));

    await screen.findByRole("heading", { level: 1, name: "Профіль" });
    expect(document.activeElement).toBe(photoCard().getByRole("link"));
  });

  test("огляд і розділ ділять один список: фото не вантажиться вдруге", async () => {
    const backend = await openOverview();
    const user = userEvent.setup();
    await photoCard().findByText("2 фото");

    await user.click(photoCard().getByRole("link"));
    await screen.findByRole("list", { name: "Збережені фото" });

    expect(backend.listRequests).toBe(1);
  });
});
