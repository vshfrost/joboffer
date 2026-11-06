/** Додавання фото: вибір файлу → кадрування → підпис → збереження. Редактор кадру — двійник на межі. */
import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { json } from "./testClient";
import { apiPhoto, rejected } from "./photosBackend";
import { imageFile, openEditor, startCropping } from "./photosHarness";

const MB = 1024 * 1024;
const SHORT = "Обрана область вужча за 300 px (зараз 250) — зменш зум або візьми фото кращої якості.";

function save() {
  return screen.getByRole("button", { name: "Зберегти фото" }) as HTMLButtonElement;
}

describe("вибір файлу", () => {
  test("«Додати фото» відкриває форму з полем файлу й переносить на нього фокус", async () => {
    const { user } = await openEditor([]);

    await user.click(await screen.findByRole("button", { name: "Додати фото" }));

    const input = screen.getByLabelText("Файл фото") as HTMLInputElement;
    expect(document.activeElement).toBe(input);
    expect(input.type).toBe("file");
    expect(input.accept).toBe("image/jpeg,image/png,image/webp");
  });

  test("обраний файл відкриває редактор: фото під рамкою, підпис, кнопки; фокус на кадруванні", async () => {
    const editor = await openEditor([]);

    const session = await startCropping(editor);

    const stage = screen.getByRole("group", { name: "Кадрування фото" });
    expect(document.activeElement).toBe(stage);
    expect(session.image.getAttribute("src")).toBe("blob:photo-1");
    expect(stage.contains(session.image)).toBe(true);
    expect(screen.getByLabelText("Підпис фото")).toBeDefined();
    expect(screen.getByRole("button", { name: "Скасувати" })).toBeDefined();
    expect(editor.crop.sessions).toHaveLength(1);
  });

  test("рамка має пропорції шапки CV 858 × 960", async () => {
    const editor = await openEditor([]);
    await startCropping(editor);

    const frame = screen.getByTestId("crop-frame");
    expect(frame.style.aspectRatio.replaceAll(" ", "")).toBe("858/960");
  });

  test("файл завеликий: повідомлення, редактор не відкрито", async () => {
    const editor = await openEditor([]);
    await editor.user.click(await screen.findByRole("button", { name: "Додати фото" }));

    await editor.user.upload(screen.getByLabelText("Файл фото"), imageFile("huge.jpg", "image/jpeg", 15 * MB + 1));

    expect((await screen.findByRole("alert")).textContent).toBe("Фото — до 15 МБ.");
    expect(editor.crop.sessions).toHaveLength(0);
    expect(screen.queryByRole("group", { name: "Кадрування фото" })).toBeNull();
  });

  test("не картинка (і підроблене розширення): повідомлення, редактор не відкрито", async () => {
    const editor = await openEditor([]);
    await editor.user.click(await screen.findByRole("button", { name: "Додати фото" }));

    await editor.user.upload(screen.getByLabelText("Файл фото"), imageFile("me.jpg", "text/plain"));

    expect((await screen.findByRole("alert")).textContent).toBe("Фото — JPEG, PNG або WebP.");
    expect(editor.crop.sessions).toHaveLength(0);
  });

  test("порожній файл", async () => {
    const editor = await openEditor([]);
    await editor.user.click(await screen.findByRole("button", { name: "Додати фото" }));

    await editor.user.upload(screen.getByLabelText("Файл фото"), imageFile("empty.jpg", "image/jpeg", 0));

    expect((await screen.findByRole("alert")).textContent).toBe("Файл порожній — вибери фото.");
  });

  test("поганий файл після вдалого: обраний кадр лишається, повідомлення поряд", async () => {
    const editor = await openEditor([]);
    const session = await startCropping(editor);
    session.area(400);

    await editor.user.upload(screen.getByLabelText("Файл фото"), imageFile("notes.txt", "text/plain"));

    expect((await screen.findByRole("alert")).textContent).toBe("Фото — JPEG, PNG або WebP.");
    expect(session.destroyed).toBe(false);
    expect(editor.crop.sessions).toHaveLength(1);
    expect(screen.getByRole("group", { name: "Кадрування фото" })).toBeDefined();
    expect(save().disabled).toBe(false);
  });

  test("інший хороший файл замінює кадрування: старий редактор закрито, адресу відкликано", async () => {
    const editor = await openEditor([]);
    const first = await startCropping(editor);

    await editor.user.upload(screen.getByLabelText("Файл фото"), imageFile("second.png", "image/png"));

    await waitFor(() => expect(editor.crop.sessions).toHaveLength(2));
    expect(first.destroyed).toBe(true);
    expect(editor.urls.revoked).toEqual(["blob:photo-1"]);
    expect(editor.crop.current().image.getAttribute("src")).toBe("blob:photo-2");
  });
});

describe("межові випадки", () => {
  test("діалог вибору файлу закрили без файлу: нічого не змінюється", async () => {
    const editor = await openEditor([]);
    await editor.user.click(await screen.findByRole("button", { name: "Додати фото" }));

    fireEvent.change(screen.getByLabelText("Файл фото"), { target: { files: [] } });

    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByRole("group", { name: "Кадрування фото" })).toBeNull();
  });

  test("поки редактор ще вантажиться, клавіші нічого не роблять і не блокуються", async () => {
    const editor = await openEditor([]);
    const release = editor.crop.hold();
    await editor.user.click(await screen.findByRole("button", { name: "Додати фото" }));
    await editor.user.upload(screen.getByLabelText("Файл фото"), imageFile());
    const stage = await screen.findByRole("group", { name: "Кадрування фото" });

    const notCancelled = fireEvent.keyDown(stage, { key: "+" });

    expect(notCancelled).toBe(true);
    expect(save().disabled).toBe(true);
    await act(async () => release());
    expect(editor.crop.current().calls).toEqual([]);
  });

  test("скасували, поки редактор вантажився: щойно готовий — його одразу знищено", async () => {
    const editor = await openEditor([]);
    const release = editor.crop.hold();
    await editor.user.click(await screen.findByRole("button", { name: "Додати фото" }));
    await editor.user.upload(screen.getByLabelText("Файл фото"), imageFile());
    await screen.findByRole("group", { name: "Кадрування фото" });

    await editor.user.click(screen.getByRole("button", { name: "Скасувати" }));
    await act(async () => release());

    expect(editor.crop.current().destroyed).toBe(true);
    expect(screen.queryByRole("group", { name: "Кадрування фото" })).toBeNull();
  });

  test("форму надіслано двічі в одному кадрі: один запит", async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const editor = await openEditor([], { upload: () => gate.then(() => json(201, apiPhoto(1))) });
    const session = await startCropping(editor);
    session.area(500);
    const form = screen.getByRole("form", { name: "Нове фото" });

    fireEvent.submit(form);
    fireEvent.submit(form);

    await act(async () => release());
    await waitFor(() => expect(screen.queryByRole("group", { name: "Кадрування фото" })).toBeNull());
    expect(editor.backend.uploads).toHaveLength(1);
  });

  test("форму надіслано, коли зберегти не можна (область вузька): запиту нема", async () => {
    const editor = await openEditor([]);
    const session = await startCropping(editor);
    session.area(250);

    fireEvent.submit(screen.getByRole("form", { name: "Нове фото" }));

    expect(editor.backend.uploads).toHaveLength(0);
    expect(session.calls).toEqual([]);
  });
});

describe("розмір області", () => {
  test("поки область невідома, «Зберегти» неактивна", async () => {
    const editor = await openEditor([]);
    await startCropping(editor);

    expect(save().disabled).toBe(true);
  });

  test("вужча за 300 px: «Зберегти» неактивна з поясненням, яке описує кнопку", async () => {
    const editor = await openEditor([]);
    const session = await startCropping(editor);

    session.area(250);

    expect(save().disabled).toBe(true);
    const hint = screen.getByText(SHORT);
    expect(hint.id).not.toBe("");
    expect(save().getAttribute("aria-describedby")).toContain(hint.id);
    expect(hint.closest("[role=alert]")).toBeNull();
  });

  test("рівно 300 px і ширше — можна зберегти, пояснення зникає", async () => {
    const editor = await openEditor([]);
    const session = await startCropping(editor);

    session.area(250);
    session.area(300);

    expect(save().disabled).toBe(false);
    expect(screen.queryByText(SHORT)).toBeNull();
    session.area(299);
    expect(save().disabled).toBe(true);
  });
});

describe("збереження", () => {
  test("на сервер іде лише кадр з редактора й підпис; галерея оновлюється, редактор закрито", async () => {
    const editor = await openEditor([apiPhoto(1, { label: "Старе" })]);
    const session = await startCropping(editor);
    session.area(500);
    await editor.user.type(screen.getByLabelText("Підпис фото"), "Ділове");

    await editor.user.click(save());

    await waitFor(() => expect(editor.backend.uploads).toHaveLength(1));
    const [upload] = editor.backend.uploads;
    expect(upload?.label).toBe("Ділове");
    expect(upload?.file.name).toBe("photo.jpg");
    expect(upload?.file.type).toBe("image/jpeg");
    expect(await upload?.file.text()).toBe("frame-jpeg");
    expect(session.calls).toContain("frame");
    // Редактор закрито й очищено; нове фото в галереї.
    await waitFor(() => expect(screen.queryByRole("group", { name: "Кадрування фото" })).toBeNull());
    expect(session.destroyed).toBe(true);
    expect(editor.urls.revoked).toEqual(["blob:photo-1"]);
    const list = within(await screen.findByRole("list", { name: "Збережені фото" }));
    expect(list.getAllByRole("listitem")).toHaveLength(2);
    expect(list.getByText("Ділове")).toBeDefined();
    expect(screen.getByRole("status", { name: "Результат" }).textContent).toBe("Фото додано.");
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Додати фото" }));
  });

  test("підпис необов'язковий і обмежений 100 символами", async () => {
    const editor = await openEditor([]);
    const session = await startCropping(editor);
    session.area(500);

    expect((screen.getByLabelText("Підпис фото") as HTMLInputElement).maxLength).toBe(100);
    await editor.user.click(save());

    await waitFor(() => expect(editor.backend.uploads[0]?.label).toBe(""));
  });

  test("поки йде збереження, кнопка неактивна: один запит", async () => {
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const editor = await openEditor([], { upload: () => gate.then(() => json(201, apiPhoto(1))) });
    const session = await startCropping(editor);
    session.area(500);

    await editor.user.click(save());
    await editor.user.click(save());

    expect(save().disabled).toBe(true);
    expect(screen.getByRole("status", { name: "Результат" }).textContent).toBe("Зберігаємо…");
    release();
    await waitFor(() => expect(screen.queryByRole("group", { name: "Кадрування фото" })).toBeNull());
    expect(editor.backend.uploads).toHaveLength(1);
  });

  test("422 з текстом v1: повідомлення, а кадр, підпис і редактор лишились; повтор проходить", async () => {
    const message = "Фото має бути в пропорціях рамки CV (858 × 960): обери область у редакторі на сторінці профілю.";
    let refuse = true;
    const editor = await openEditor([], { upload: () => (refuse ? rejected(message) : undefined) });
    const session = await startCropping(editor);
    session.area(500);
    await editor.user.type(screen.getByLabelText("Підпис фото"), "Ділове");

    await editor.user.click(save());

    expect((await screen.findByRole("alert")).textContent).toBe(message);
    expect(session.destroyed).toBe(false);
    expect(editor.crop.sessions).toHaveLength(1);
    expect((screen.getByLabelText("Підпис фото") as HTMLInputElement).value).toBe("Ділове");
    expect(save().disabled).toBe(false);
    expect(editor.backend.photos).toHaveLength(0);

    refuse = false;
    await editor.user.click(save());

    await waitFor(() => expect(editor.backend.photos).toHaveLength(1));
    expect(editor.backend.uploads.map((upload) => upload.label)).toEqual(["Ділове", "Ділове"]);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  test("збій сервера: повідомлення, чернетка лишилась", async () => {
    const editor = await openEditor([], { upload: () => new Response("{}", { status: 500 }) });
    const session = await startCropping(editor);
    session.area(500);

    await editor.user.click(save());

    expect((await screen.findByRole("alert")).textContent).toBe("Не вдалося зберегти фото. Спробуй ще раз.");
    expect(session.destroyed).toBe(false);
    expect(save().disabled).toBe(false);
  });

  test("сесія завершилась: окреме повідомлення, чернетка лишилась", async () => {
    const editor = await openEditor([], { upload: () => new Response("{}", { status: 401 }) });
    const session = await startCropping(editor);
    session.area(500);

    await editor.user.click(save());

    expect((await screen.findByRole("alert")).textContent).toBe("Сесія завершилась. Увійди знову, щоб зберегти фото.");
    expect(session.destroyed).toBe(false);
  });

  test("редактор не зміг віддати кадр: повідомлення, на сервер нічого не йде", async () => {
    const editor = await openEditor([]);
    const session = await startCropping(editor);
    session.area(500);
    session.frameBlob = null;

    await editor.user.click(save());

    expect((await screen.findByRole("alert")).textContent).toBe("Не вдалося підготувати кадр. Спробуй ще раз.");
    expect(editor.backend.uploads).toHaveLength(0);
    expect(save().disabled).toBe(false);
  });

  test("нове повідомлення замінює старе: після успіху помилки нема", async () => {
    const editor = await openEditor([], { upload: () => undefined });
    await editor.user.click(await screen.findByRole("button", { name: "Додати фото" }));
    await editor.user.upload(screen.getByLabelText("Файл фото"), imageFile("a.txt", "text/plain"));
    await screen.findByRole("alert");

    await editor.user.upload(screen.getByLabelText("Файл фото"), imageFile());

    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  });
});

describe("скасування", () => {
  test("«Скасувати» закриває редактор, відкликає адресу, нічого не шле; фокус на «Додати фото»", async () => {
    const editor = await openEditor([]);
    const session = await startCropping(editor);
    session.area(500);

    await editor.user.click(screen.getByRole("button", { name: "Скасувати" }));

    expect(session.destroyed).toBe(true);
    expect(editor.urls.revoked).toEqual(["blob:photo-1"]);
    expect(screen.queryByRole("group", { name: "Кадрування фото" })).toBeNull();
    expect(editor.backend.uploads).toHaveLength(0);
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Додати фото" }));
  });

  test("вихід з розділу закриває редактор і відкликає адресу", async () => {
    const editor = await openEditor([]);
    const session = await startCropping(editor);

    await editor.user.click(screen.getByRole("link", { name: /Огляд профілю/ }));

    await screen.findByRole("heading", { level: 1, name: "Профіль" });
    expect(session.destroyed).toBe(true);
    expect(editor.urls.revoked).toEqual(["blob:photo-1"]);
  });

  test("чернетку кадру не кладуть у localStorage", async () => {
    const editor = await openEditor([]);
    const session = await startCropping(editor);
    session.area(500);

    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });
});
