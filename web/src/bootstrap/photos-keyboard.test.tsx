/** Клавіатура й фокус у розділі фото: кадрування (+ − стрілки), підпис, збереження, видалення. */
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { apiPhoto } from "./photosBackend";
import { openEditor, startCropping } from "./photosHarness";

describe("кадрування з клавіатури", () => {
  test("+ та = збільшують, − зменшує: на кадруванні, без прокрутки сторінки", async () => {
    const editor = await openEditor([]);
    const session = await startCropping(editor);
    const stage = screen.getByRole("group", { name: "Кадрування фото" });

    for (const key of ["+", "=", "-"]) {
      const notCancelled = fireEvent.keyDown(stage, { key });
      expect(notCancelled).toBe(false);
    }

    expect(session.calls).toEqual(["zoom 1", "zoom 1", "zoom -1"]);
  });

  test("стрілки зсувають фото під рамкою в бік стрілки на крок, Shift — на більший", async () => {
    const editor = await openEditor([]);
    const session = await startCropping(editor);
    const stage = screen.getByRole("group", { name: "Кадрування фото" });

    fireEvent.keyDown(stage, { key: "ArrowLeft" });
    fireEvent.keyDown(stage, { key: "ArrowRight" });
    fireEvent.keyDown(stage, { key: "ArrowUp" });
    fireEvent.keyDown(stage, { key: "ArrowDown" });
    fireEvent.keyDown(stage, { key: "ArrowLeft", shiftKey: true });

    expect(session.calls).toEqual(["move -10 0", "move 10 0", "move 0 -10", "move 0 10", "move -50 0"]);
  });

  test("інші клавіші не чіпають кадрування й не блокуються", async () => {
    const editor = await openEditor([]);
    const session = await startCropping(editor);
    const stage = screen.getByRole("group", { name: "Кадрування фото" });

    const notCancelled = fireEvent.keyDown(stage, { key: "a" });

    expect(notCancelled).toBe(true);
    expect(session.calls).toEqual([]);
  });

  test("клавіші в полі підпису не керують кадром: «-» і «+» там просто символи", async () => {
    const editor = await openEditor([]);
    const session = await startCropping(editor);

    await editor.user.type(screen.getByLabelText("Підпис фото"), "Фото-1+");

    expect(session.calls).toEqual([]);
    expect((screen.getByLabelText("Підпис фото") as HTMLInputElement).value).toBe("Фото-1+");
  });

  test("кнопки роблять те саме: збільшити, зменшити, зсув у чотирьох напрямках", async () => {
    const editor = await openEditor([]);
    const session = await startCropping(editor);

    for (const name of ["Збільшити", "Зменшити", "Зсунути фото ліворуч", "Зсунути фото праворуч", "Зсунути фото вгору", "Зсунути фото вниз"]) {
      await editor.user.click(screen.getByRole("button", { name }));
    }

    expect(session.calls).toEqual(["zoom 1", "zoom -1", "move -10 0", "move 10 0", "move 0 -10", "move 0 10"]);
  });

  test("кнопки кадрування мають видимі підписи й не відправляють форму", async () => {
    const editor = await openEditor([]);
    await startCropping(editor);
    const zoomIn = screen.getByRole("button", { name: "Збільшити" });

    expect(zoomIn.getAttribute("type")).toBe("button");
    expect(zoomIn.textContent).toBe("+");
    expect(screen.getByRole("button", { name: "Зменшити" }).textContent).toBe("−");
    expect(editor.backend.uploads).toHaveLength(0);
  });

  test("Tab: файл → кадрування → кнопки кадру → підпис → Скасувати → Зберегти", async () => {
    const editor = await openEditor([]);
    const session = await startCropping(editor);
    session.area(500);
    const stage = screen.getByRole("group", { name: "Кадрування фото" });
    expect(document.activeElement).toBe(stage);

    const expected = [
      "Збільшити",
      "Зменшити",
      "Зсунути фото ліворуч",
      "Зсунути фото праворуч",
      "Зсунути фото вгору",
      "Зсунути фото вниз",
    ].map((name) => screen.getByRole("button", { name }));
    for (const element of [...expected, screen.getByLabelText("Підпис фото"), screen.getByRole("button", { name: "Скасувати" }), screen.getByRole("button", { name: "Зберегти фото" })]) {
      await editor.user.tab();
      expect(document.activeElement).toBe(element);
    }
  });

  test("кадрування фокусоване — це видно: тема малює контур focus-visible", async () => {
    const editor = await openEditor([]);
    await startCropping(editor);

    expect(screen.getByRole("group", { name: "Кадрування фото" }).getAttribute("tabindex")).toBe("0");
    const theme = (await import("../ui/theme.css?raw")).default;
    expect(theme).toMatch(/:focus-visible\s*\{[^}]*outline: 2px solid var\(--ring\)/);
  });
});

describe("підпис і збереження з клавіатури", () => {
  test("Enter у полі підпису зберігає, якщо область достатня", async () => {
    const editor = await openEditor([]);
    const session = await startCropping(editor);
    session.area(500);

    await editor.user.type(screen.getByLabelText("Підпис фото"), "Ділове{Enter}");

    await waitFor(() => expect(editor.backend.uploads).toHaveLength(1));
    expect(editor.backend.uploads[0]?.label).toBe("Ділове");
  });

  test("Enter у полі підпису не зберігає, поки область вужча за 300 px", async () => {
    const editor = await openEditor([]);
    const session = await startCropping(editor);
    session.area(250);

    await editor.user.type(screen.getByLabelText("Підпис фото"), "Ділове{Enter}");

    expect(editor.backend.uploads).toHaveLength(0);
  });

  test("Escape в редакторі скасовує кадрування", async () => {
    const editor = await openEditor([]);
    const session = await startCropping(editor);

    await editor.user.keyboard("{Escape}");

    expect(session.destroyed).toBe(true);
    expect(screen.queryByRole("group", { name: "Кадрування фото" })).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Додати фото" }));
  });
});

describe("видалення з клавіатури", () => {
  const photo = apiPhoto(1, { label: "Ділове" });

  async function focusDelete(editor: Awaited<ReturnType<typeof openEditor>>) {
    const button = within(screen.getByRole("list", { name: "Збережені фото" })).getByRole("button", { name: "Видалити фото «Ділове»" });
    button.focus();
    await editor.user.keyboard("{Enter}");
    return button;
  }

  test("Enter відкриває діалог: фокус на безпечній «Скасувати»; Escape закриває й повертає фокус", async () => {
    const editor = await openEditor([photo]);
    const opener = await focusDelete(editor);

    const dialog = await screen.findByRole("alertdialog");
    expect(document.activeElement).toBe(within(dialog).getByRole("button", { name: "Скасувати" }));
    await editor.user.keyboard("{Escape}");

    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect(document.activeElement).toBe(opener);
    expect(editor.backend.removeRequests).toEqual([]);
  });

  test("Tab до «Видалити» й Enter видаляють; фокус іде на «Додати фото»", async () => {
    const editor = await openEditor([photo]);
    await focusDelete(editor);
    await screen.findByRole("alertdialog");

    await editor.user.tab();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Видалити" }));
    await editor.user.keyboard("{Enter}");

    await waitFor(() => expect(editor.backend.removeRequests).toEqual([1]));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Додати фото" }));
  });
});
