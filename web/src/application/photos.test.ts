import { describe, expect, test } from "vitest";

import type { Photo, PhotoLibrary } from "../domain/photos";
import {
  PhotosNotFoundError,
  PhotosRejectedError,
  PhotosUnauthorizedError,
  PhotosUnavailableError,
} from "../domain/photosErrors";
import type { PhotosApi } from "../ports/photosApi";
import { createPhotosServices } from "./photos";

const PHOTO: Photo = { id: 3, label: "Ділове", width: 858, height: 960, createdAt: "2026-10-21T09:00:00Z", lastUsedAt: null };
const LIBRARY: PhotoLibrary = { photos: [PHOTO], suggestedId: 3 };
const FRAME = new Blob(["jpeg"], { type: "image/jpeg" });

/** Порт, який відповідає заданим результатом чи кидає задану помилку. */
function failing(error: unknown): PhotosApi {
  const fail = () => Promise.reject(error);
  return { list: fail, upload: fail, remove: fail, imageUrl: (id) => `/api/photos/${id}.jpg` };
}

function succeeding(): PhotosApi {
  return {
    list: () => Promise.resolve(LIBRARY),
    upload: () => Promise.resolve(PHOTO),
    remove: () => Promise.resolve(),
    imageUrl: (id) => `/api/photos/${id}.jpg`,
  };
}

describe("завантаження галереї", () => {
  test("успіх: галерея", async () => {
    expect(await createPhotosServices(succeeding()).load()).toEqual({ ok: true, library: LIBRARY });
  });

  test("сесія завершилась і збій — окремо", async () => {
    expect(await createPhotosServices(failing(new PhotosUnauthorizedError())).load()).toEqual({ ok: false, kind: "unauthorized" });
    expect(await createPhotosServices(failing(new PhotosUnavailableError())).load()).toEqual({ ok: false, kind: "unavailable" });
  });

  test("несподівана помилка не ховається", async () => {
    await expect(createPhotosServices(failing(new TypeError("баг"))).load()).rejects.toThrow("баг");
  });
});

describe("збереження кадру", () => {
  test("успіх: нове фото", async () => {
    expect(await createPhotosServices(succeeding()).upload(FRAME, "Ділове")).toEqual({ ok: true, photo: PHOTO });
  });

  test("сервер не прийняв кадр: його текст", async () => {
    const services = createPhotosServices(failing(new PhotosRejectedError("Фото — до 15 МБ.")));
    expect(await services.upload(FRAME, "")).toEqual({ ok: false, kind: "rejected", message: "Фото — до 15 МБ." });
  });

  test("сесія завершилась і збій — окремо", async () => {
    expect(await createPhotosServices(failing(new PhotosUnauthorizedError())).upload(FRAME, "")).toEqual({ ok: false, kind: "unauthorized" });
    expect(await createPhotosServices(failing(new PhotosUnavailableError())).upload(FRAME, "")).toEqual({ ok: false, kind: "unavailable" });
  });

  test("несподівана помилка не ховається", async () => {
    await expect(createPhotosServices(failing(new TypeError("баг"))).upload(FRAME, "")).rejects.toThrow("баг");
  });
});

describe("видалення", () => {
  test("успіх", async () => {
    expect(await createPhotosServices(succeeding()).remove(3)).toEqual({ ok: true });
  });

  test("фото вже нема — теж успіх", async () => {
    expect(await createPhotosServices(failing(new PhotosNotFoundError())).remove(3)).toEqual({ ok: true });
  });

  test("сесія завершилась і збій — окремо", async () => {
    expect(await createPhotosServices(failing(new PhotosUnauthorizedError())).remove(3)).toEqual({ ok: false, kind: "unauthorized" });
    expect(await createPhotosServices(failing(new PhotosUnavailableError())).remove(3)).toEqual({ ok: false, kind: "unavailable" });
  });

  test("несподівана помилка не ховається", async () => {
    await expect(createPhotosServices(failing(new TypeError("баг"))).remove(3)).rejects.toThrow("баг");
  });
});

test("адреса зображення віддається з порту", () => {
  expect(createPhotosServices(succeeding()).imageUrl(7)).toBe("/api/photos/7.jpg");
});
