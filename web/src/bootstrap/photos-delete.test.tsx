/** Видалення фото: діалог, що збережені CV не зміняться, помилки лишають фото. */
import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { apiPhoto } from "./photosBackend";
import { openEditor } from "./photosHarness";

const OFFICE = apiPhoto(1, { label: "Ділове" });
const CASUAL = apiPhoto(2, { label: "Неформальне", created_at: "2026-10-22T08:00:00Z" });

async function askToDelete(editor: Awaited<ReturnType<typeof openEditor>>, label: string) {
  await editor.user.click(screen.getByRole("button", { name: `Видалити фото «${label}»` }));
  return screen.findByRole("alertdialog");
}

describe("діалог", () => {
  test("називає фото й каже, що збережені CV не зміняться", async () => {
    const editor = await openEditor([OFFICE]);

    const dialog = await askToDelete(editor, "Ділове");

    expect(within(dialog).getByText("Видалити фото?")).toBeDefined();
    expect(within(dialog).getByText(/Збережені CV не зміняться/)).toBeDefined();
    expect(within(dialog).getByText("Ділове")).toBeDefined();
    expect(within(dialog).getByRole("button", { name: "Скасувати" })).toBeDefined();
    expect(within(dialog).getByRole("button", { name: "Видалити" })).toBeDefined();
    expect(editor.backend.removeRequests).toEqual([]);
  });

  test("«Скасувати» нічого не видаляє й повертає фокус на кнопку", async () => {
    const editor = await openEditor([OFFICE]);
    const opener = screen.getByRole("button", { name: "Видалити фото «Ділове»" });
    await askToDelete(editor, "Ділове");

    await editor.user.click(screen.getByRole("button", { name: "Скасувати" }));

    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect(editor.backend.removeRequests).toEqual([]);
    expect(document.activeElement).toBe(opener);
    expect(screen.getByRole("list", { name: "Збережені фото" })).toBeDefined();
  });
});

describe("видалення", () => {
  test("підтвердження прибирає фото з галереї; решта лишається", async () => {
    const editor = await openEditor([OFFICE, CASUAL]);
    await askToDelete(editor, "Ділове");

    await editor.user.click(screen.getByRole("button", { name: "Видалити" }));

    await waitFor(() => expect(editor.backend.removeRequests).toEqual([1]));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    const list = within(await screen.findByRole("list", { name: "Збережені фото" }));
    expect(list.getAllByRole("listitem")).toHaveLength(1);
    expect(list.queryByText("Ділове")).toBeNull();
    expect(list.getByText("Неформальне")).toBeDefined();
    expect(screen.getByRole("status", { name: "Результат" }).textContent).toBe("Фото видалено.");
  });

  test("останнє фото: галерея порожніє, лишається порожній стан", async () => {
    const editor = await openEditor([OFFICE]);
    await askToDelete(editor, "Ділове");

    await editor.user.click(screen.getByRole("button", { name: "Видалити" }));

    expect(await screen.findByRole("heading", { level: 3, name: "Фото ще не додано" })).toBeDefined();
  });

  test("пропонованим після видалення стає інше фото", async () => {
    const editor = await openEditor([OFFICE, CASUAL]);
    await askToDelete(editor, "Неформальне");

    await editor.user.click(screen.getByRole("button", { name: "Видалити" }));

    await waitFor(() => expect(screen.getAllByText("Пропонується для CV")).toHaveLength(1));
    const item = within(screen.getByRole("list", { name: "Збережені фото" })).getAllByRole("listitem")[0] as HTMLElement;
    expect(within(item).getByText("Ділове")).toBeDefined();
    expect(within(item).getByText("Пропонується для CV")).toBeDefined();
  });

  test("помилка сервера: діалог лишається з повідомленням, фото на місці, повтор можливий", async () => {
    let failing = true;
    const editor = await openEditor([OFFICE], { remove: () => (failing ? new Response("{}", { status: 500 }) : undefined) });
    const dialog = await askToDelete(editor, "Ділове");

    await editor.user.click(within(dialog).getByRole("button", { name: "Видалити" }));

    expect((await within(dialog).findByRole("alert")).textContent).toBe("Не вдалося видалити фото. Спробуй ще раз.");
    expect(screen.getByRole("alertdialog")).toBeDefined();
    expect(editor.backend.photos).toHaveLength(1);
    expect(within(screen.getByRole("list", { name: "Збережені фото", hidden: true })).getAllByRole("listitem", { hidden: true })).toHaveLength(1);

    failing = false;
    await editor.user.click(within(dialog).getByRole("button", { name: "Видалити" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect(editor.backend.photos).toHaveLength(0);
  });

  test("сесія завершилась: окреме повідомлення, фото на місці", async () => {
    const editor = await openEditor([OFFICE], { remove: () => new Response("{}", { status: 401 }) });
    const dialog = await askToDelete(editor, "Ділове");

    await editor.user.click(within(dialog).getByRole("button", { name: "Видалити" }));

    expect((await within(dialog).findByRole("alert")).textContent).toBe("Сесія завершилась. Увійди знову, щоб видалити фото.");
    expect(editor.backend.photos).toHaveLength(1);
  });

  test("фото вже нема (404): без помилки, діалог закривається", async () => {
    const editor = await openEditor([OFFICE, CASUAL], { remove: () => new Response("{}", { status: 404 }) });
    const dialog = await askToDelete(editor, "Ділове");

    await editor.user.click(within(dialog).getByRole("button", { name: "Видалити" }));

    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect(screen.queryByText("Не вдалося видалити фото. Спробуй ще раз.")).toBeNull();
  });

  test("два кліки в одному кадрі: один запит", async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const editor = await openEditor([OFFICE], { remove: () => gate.then(() => new Response(null, { status: 204 })) });
    const dialog = await askToDelete(editor, "Ділове");
    const confirm = within(dialog).getByRole("button", { name: "Видалити" });

    // В одному act React не встигає оновити кнопку між кліками: захищає не `disabled`, а ворота в обробнику.
    act(() => {
      fireEvent.click(confirm);
      fireEvent.click(confirm);
    });

    release();
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect(editor.backend.removeRequests).toEqual([1]);
  });

  test("поки йде видалення, кнопка неактивна: один запит", async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const editor = await openEditor([OFFICE], { remove: () => gate.then(() => new Response(null, { status: 204 })) });
    const dialog = await askToDelete(editor, "Ділове");

    await editor.user.click(within(dialog).getByRole("button", { name: "Видалити" }));
    await editor.user.click(within(dialog).getByRole("button", { name: "Видалити" }));

    release();
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect(editor.backend.removeRequests).toEqual([1]);
  });
});
