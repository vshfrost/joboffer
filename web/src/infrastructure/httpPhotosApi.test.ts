import { describe, expect, test, vi } from "vitest";

import {
  PhotosNotFoundError,
  PhotosRejectedError,
  PhotosUnauthorizedError,
  PhotosUnavailableError,
} from "../domain/photosErrors";
import { createApiClient } from "./apiClient";
import { createHttpPhotosApi } from "./httpPhotosApi";

const ITEM = { photo_id: 3, label: "Ділове", width: 858, height: 960, created_at: "2026-10-21T09:00:00Z", last_used_at: null };

/** Межа — fetch: відповідь або збій мережі. */
function apiWith(respond: (input: string, init: RequestInit | undefined) => Response | Promise<Response>) {
  const fetchFn = vi.fn<typeof fetch>((input, init) => Promise.resolve(respond(String(input), init)));
  const client = createApiClient(fetchFn, "/api");
  client.setCsrfToken("csrf-1");
  return { api: createHttpPhotosApi(client, "/api"), fetchFn };
}

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

describe("список", () => {
  test("GET /photos: фото й те, що пропонувати, у моделі клієнта", async () => {
    const { api, fetchFn } = apiWith(() => json(200, { photos: [ITEM], suggested_photo_id: 3 }));

    const library = await api.list();

    expect(fetchFn.mock.calls[0]?.[0]).toBe("/api/photos");
    expect(fetchFn.mock.calls[0]?.[1]?.method).toBe("GET");
    expect(library).toEqual({
      photos: [{ id: 3, label: "Ділове", width: 858, height: 960, createdAt: "2026-10-21T09:00:00Z", lastUsedAt: null }],
      suggestedId: 3,
    });
  });

  test("порядок сервера зберігається; використане фото має дату", async () => {
    const { api } = apiWith(() =>
      json(200, { photos: [{ ...ITEM, photo_id: 5, last_used_at: "2026-10-22T08:00:00Z" }, ITEM], suggested_photo_id: 5 }),
    );

    const library = await api.list();

    expect(library.photos.map((item) => item.id)).toEqual([5, 3]);
    expect(library.photos[0]?.lastUsedAt).toBe("2026-10-22T08:00:00Z");
  });

  test("порожня галерея: нема що пропонувати", async () => {
    const { api } = apiWith(() => json(200, { photos: [], suggested_photo_id: null }));

    expect(await api.list()).toEqual({ photos: [], suggestedId: null });
  });

  test.each([
    [401, PhotosUnauthorizedError],
    [403, PhotosUnavailableError],
    [500, PhotosUnavailableError],
    [502, PhotosUnavailableError],
  ])("відповідь %i → %o", async (status, error) => {
    const { api } = apiWith(() => json(status, { code: "x", message: "y", field_errors: [] }));

    await expect(api.list()).rejects.toBeInstanceOf(error);
  });

  test("мережа недоступна", async () => {
    const fetchFn = vi.fn<typeof fetch>(() => Promise.reject(new TypeError("offline")));
    const api = createHttpPhotosApi(createApiClient(fetchFn, "/api"), "/api");

    await expect(api.list()).rejects.toBeInstanceOf(PhotosUnavailableError);
  });

  test("збій не з Error — теж «недоступно»", async () => {
    const client = { request: () => Promise.reject("boom"), setCsrfToken: () => {} };
    const api = createHttpPhotosApi(client, "/api");

    await expect(api.list()).rejects.toThrow("Мережа недоступна");
  });

  test.each([
    ["нема photos", { suggested_photo_id: null }],
    ["photos не масив", { photos: "x", suggested_photo_id: null }],
    ["елемент не обʼєкт", { photos: [1], suggested_photo_id: null }],
    ["photo_id не ціле", { photos: [{ ...ITEM, photo_id: "3" }], suggested_photo_id: null }],
    ["label не рядок", { photos: [{ ...ITEM, label: 5 }], suggested_photo_id: null }],
    ["width не ціле", { photos: [{ ...ITEM, width: 1.5 }], suggested_photo_id: null }],
    ["created_at не рядок", { photos: [{ ...ITEM, created_at: 5 }], suggested_photo_id: null }],
    ["last_used_at не рядок і не null", { photos: [{ ...ITEM, last_used_at: 5 }], suggested_photo_id: null }],
    ["suggested_photo_id відсутній", { photos: [] }],
    ["suggested_photo_id не ціле", { photos: [], suggested_photo_id: "3" }],
  ])("не за контрактом: %s → недоступно", async (_, body) => {
    const { api } = apiWith(() => json(200, body));

    await expect(api.list()).rejects.toBeInstanceOf(PhotosUnavailableError);
  });

  test("тіло не JSON", async () => {
    const { api } = apiWith(() => new Response("<html>", { status: 200 }));

    await expect(api.list()).rejects.toBeInstanceOf(PhotosUnavailableError);
  });
});

describe("завантаження кадру", () => {
  const frame = new Blob(["jpeg-bytes"], { type: "image/jpeg" });

  test("POST /photos: multipart з файлом photo.jpg і підписом, без ручного Content-Type", async () => {
    const { api, fetchFn } = apiWith(() => json(201, ITEM));

    const photo = await api.upload(frame, "Ділове");

    const [url, init] = fetchFn.mock.calls[0] ?? [];
    expect(url).toBe("/api/photos");
    expect(init?.method).toBe("POST");
    const body = init?.body;
    expect(body).toBeInstanceOf(FormData);
    const file = (body as FormData).get("file");
    expect(file).toBeInstanceOf(File);
    expect((file as File).name).toBe("photo.jpg");
    expect((file as File).type).toBe("image/jpeg");
    expect(await (file as File).text()).toBe("jpeg-bytes");
    expect((body as FormData).get("label")).toBe("Ділове");
    const headers = new Headers(init?.headers);
    expect(headers.has("Content-Type")).toBe(false);
    expect(headers.get("X-CSRF-Token")).toBe("csrf-1");
    expect(photo).toEqual({ id: 3, label: "Ділове", width: 858, height: 960, createdAt: "2026-10-21T09:00:00Z", lastUsedAt: null });
  });

  test("422: текст сервера дослівно", async () => {
    const message = "Обрана область вужча за 300 px — візьми більшу або фото кращої якості.";
    const { api } = apiWith(() => json(422, { code: "invalid_value", message, field_errors: [{ field: "file", message }], correlation_id: "c" }));

    await expect(api.upload(frame, "")).rejects.toEqual(new PhotosRejectedError(message));
  });

  test("422 без field_errors: загальне повідомлення", async () => {
    const { api } = apiWith(() => json(422, { code: "invalid_request", message: "Запит не пройшов перевірку" }));

    await expect(api.upload(frame, "")).rejects.toEqual(new PhotosRejectedError("Запит не пройшов перевірку"));
  });

  test("422 з порожнім елементом field_errors: береться загальне повідомлення", async () => {
    const { api } = apiWith(() => json(422, { message: "Загальна відмова", field_errors: [{ field: "file" }] }));

    await expect(api.upload(frame, "")).rejects.toEqual(new PhotosRejectedError("Загальна відмова"));
  });

  test("422 не JSON — недоступно", async () => {
    const { api } = apiWith(() => new Response("не JSON", { status: 422 }));

    await expect(api.upload(frame, "")).rejects.toBeInstanceOf(PhotosUnavailableError);
  });

  test("422 без жодного тексту — недоступно, а не порожня помилка", async () => {
    const { api } = apiWith(() => json(422, {}));

    await expect(api.upload(frame, "")).rejects.toBeInstanceOf(PhotosUnavailableError);
  });

  test.each([
    [401, PhotosUnauthorizedError],
    [403, PhotosUnavailableError],
    [500, PhotosUnavailableError],
  ])("відповідь %i → %o", async (status, error) => {
    const { api } = apiWith(() => json(status, { code: "x", message: "y", field_errors: [] }));

    await expect(api.upload(frame, "")).rejects.toBeInstanceOf(error);
  });

  test("201 не за контрактом → недоступно", async () => {
    const { api } = apiWith(() => json(201, { photo_id: "3" }));

    await expect(api.upload(frame, "")).rejects.toBeInstanceOf(PhotosUnavailableError);
  });
});

describe("видалення", () => {
  test("DELETE /photos/{id}: 204", async () => {
    const { api, fetchFn } = apiWith(() => new Response(null, { status: 204 }));

    await api.remove(3);

    expect(fetchFn.mock.calls[0]?.[0]).toBe("/api/photos/3");
    expect(fetchFn.mock.calls[0]?.[1]?.method).toBe("DELETE");
  });

  test.each([
    [404, PhotosNotFoundError],
    [401, PhotosUnauthorizedError],
    [403, PhotosUnavailableError],
    [500, PhotosUnavailableError],
  ])("відповідь %i → %o", async (status, error) => {
    const { api } = apiWith(() => json(status, { code: "x", message: "y", field_errors: [] }));

    await expect(api.remove(3)).rejects.toBeInstanceOf(error);
  });
});

test("адреса зображення: той самий origin, JPEG", () => {
  const { api } = apiWith(() => json(200, {}));

  expect(api.imageUrl(7)).toBe("/api/photos/7.jpg");
});
