/** Спільне для тестів фото: відкрити редактор на двійниках, обрати файл, дійти до кадрування. */
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect } from "vitest";

import { fakeCropper, stubObjectUrls, type FakeSession } from "./fakeCropper";
import { photosBackend, type ApiPhoto, type PhotosOverrides } from "./photosBackend";
import { renderClient } from "./testClient";

export function imageFile(name = "me.jpg", type = "image/jpeg", size = 2048): File {
  return new File([new Uint8Array(size)], name, { type });
}

/** `settle: false` — не чекати, поки список фото завантажиться (щоб бачити стан завантаження). */
export async function openEditor(initial: ApiPhoto[] = [], overrides: PhotosOverrides = {}, settle = true) {
  const urls = stubObjectUrls();
  const crop = fakeCropper();
  const backend = photosBackend(initial, overrides);
  const view = renderClient("/profile/photos", backend.fetchFn, crop.engine);
  await screen.findByRole("heading", { level: 1, name: "Фото для CV" });
  if (settle) {
    await waitFor(() => expect(screen.queryByRole("status", { name: "Завантажуємо фото…" })).toBeNull());
  }
  // applyAccept: false — щоб перевіряти й файли, яких поле не пропустило б саме.
  return { backend, crop, urls, view, user: userEvent.setup({ applyAccept: false }) };
}

export type Editor = Awaited<ReturnType<typeof openEditor>>;

/** «Додати фото» → файл → редактор кадрування відкрито; повертає його двійник. */
export async function startCropping(editor: Editor, file: File = imageFile()): Promise<FakeSession> {
  await editor.user.click(await screen.findByRole("button", { name: "Додати фото" }));
  const before = editor.crop.sessions.length;
  await editor.user.upload(screen.getByLabelText("Файл фото"), file);
  await waitFor(() => expect(editor.crop.sessions.length).toBeGreaterThan(before));
  return editor.crop.current();
}
