import type { Photo, PhotoLibrary } from "../domain/photos";
import {
  PhotosNotFoundError,
  PhotosRejectedError,
  PhotosUnauthorizedError,
  PhotosUnavailableError,
} from "../domain/photosErrors";
import type { PhotosApi } from "../ports/photosApi";
import type { ApiClient, ApiResponse } from "./apiClient";

const CONTRACT = "Відповідь сервера не за контрактом";

export function createHttpPhotosApi(client: ApiClient, apiBase: string): PhotosApi {
  return {
    async list() {
      const response = await requestOrUnavailable(() => client.request("GET", "/photos"));
      throwForStatus(response, 200);
      return readLibrary(response.body);
    },

    async upload(frame, label) {
      const form = new FormData();
      form.set("file", new File([frame], "photo.jpg", { type: "image/jpeg" }));
      form.set("label", label);
      const response = await requestOrUnavailable(() => client.request("POST", "/photos", form));
      if (response.status === 422) {
        throw new PhotosRejectedError(rejection(response.body));
      }
      throwForStatus(response, 201);
      return readPhoto(response.body);
    },

    async remove(id) {
      const response = await requestOrUnavailable(() => client.request("DELETE", `/photos/${id}`));
      if (response.status === 404) {
        throw new PhotosNotFoundError();
      }
      throwForStatus(response, 204);
    },

    imageUrl: (id) => `${apiBase}/photos/${id}.jpg`,
  };
}

function throwForStatus(response: ApiResponse, success: number): void {
  if (response.status === success) {
    return;
  }
  if (response.status === 401) {
    throw new PhotosUnauthorizedError();
  }
  throw new PhotosUnavailableError(`Фото: відповідь ${response.status}`);
}

async function requestOrUnavailable<T>(call: () => Promise<T>): Promise<T> {
  try {
    return await call();
  } catch (error) {
    throw new PhotosUnavailableError(error instanceof Error ? error.message : "Мережа недоступна");
  }
}

/** Текст відмови 422: перша помилка поля або загальне повідомлення; без тексту відповідь вважаємо збоєм. */
function rejection(body: unknown): string {
  if (isRecord(body)) {
    const fieldErrors = body["field_errors"];
    const first: unknown = Array.isArray(fieldErrors) ? fieldErrors[0] : undefined;
    if (isRecord(first) && typeof first["message"] === "string" && first["message"] !== "") {
      return first["message"];
    }
    if (typeof body["message"] === "string" && body["message"] !== "") {
      return body["message"];
    }
  }
  throw new PhotosUnavailableError(CONTRACT);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function record(value: unknown): Record<string, unknown> {
  if (!isRecord(value)) {
    throw new PhotosUnavailableError(CONTRACT);
  }
  return value;
}

function text(value: unknown): string {
  if (typeof value !== "string") {
    throw new PhotosUnavailableError(CONTRACT);
  }
  return value;
}

function integer(value: unknown): number {
  if (typeof value !== "number" || !Number.isInteger(value)) {
    throw new PhotosUnavailableError(CONTRACT);
  }
  return value;
}

function readLibrary(body: unknown): PhotoLibrary {
  const value = record(body);
  const photos = value["photos"];
  if (!Array.isArray(photos)) {
    throw new PhotosUnavailableError(CONTRACT);
  }
  return {
    photos: photos.map(readPhoto),
    suggestedId: value["suggested_photo_id"] === null ? null : integer(value["suggested_photo_id"]),
  };
}

function readPhoto(item: unknown): Photo {
  const value = record(item);
  return {
    id: integer(value["photo_id"]),
    label: text(value["label"]),
    width: integer(value["width"]),
    height: integer(value["height"]),
    createdAt: text(value["created_at"]),
    lastUsedAt: value["last_used_at"] === null ? null : text(value["last_used_at"]),
  };
}
