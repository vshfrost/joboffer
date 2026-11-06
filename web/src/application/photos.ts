import type { Photo, PhotoLibrary } from "../domain/photos";
import {
  PhotosNotFoundError,
  PhotosRejectedError,
  PhotosUnauthorizedError,
  PhotosUnavailableError,
} from "../domain/photosErrors";
import type { PhotosApi } from "../ports/photosApi";

export type LoadPhotosOutcome = { ok: true; library: PhotoLibrary } | { ok: false; kind: "unauthorized" | "unavailable" };

/** `rejected` — сервер не прийняв кадр (текст для користувача); решта — сесія й збої. */
export type UploadPhotoOutcome =
  | { ok: true; photo: Photo }
  | { ok: false; kind: "rejected"; message: string }
  | { ok: false; kind: "unauthorized" | "unavailable" };

export type RemovePhotoOutcome = { ok: true } | { ok: false; kind: "unauthorized" | "unavailable" };

export interface PhotosServices {
  load(): Promise<LoadPhotosOutcome>;
  upload(frame: Blob, label: string): Promise<UploadPhotoOutcome>;
  /** Фото, якого вже нема, — теж успіх: користувач хотів, щоб його не було. */
  remove(id: number): Promise<RemovePhotoOutcome>;
  imageUrl(id: number): string;
}

export function createPhotosServices(api: PhotosApi): PhotosServices {
  return {
    async load() {
      try {
        return { ok: true, library: await api.list() };
      } catch (error) {
        return failure(error);
      }
    },

    async upload(frame, label) {
      try {
        return { ok: true, photo: await api.upload(frame, label) };
      } catch (error) {
        if (error instanceof PhotosRejectedError) {
          return { ok: false, kind: "rejected", message: error.message };
        }
        return failure(error);
      }
    },

    async remove(id) {
      try {
        await api.remove(id);
        return { ok: true };
      } catch (error) {
        if (error instanceof PhotosNotFoundError) {
          return { ok: true };
        }
        return failure(error);
      }
    },

    imageUrl: (id) => api.imageUrl(id),
  };
}

function failure(error: unknown): { ok: false; kind: "unauthorized" | "unavailable" } {
  if (error instanceof PhotosUnauthorizedError) {
    return { ok: false, kind: "unauthorized" };
  }
  if (error instanceof PhotosUnavailableError) {
    return { ok: false, kind: "unavailable" };
  }
  throw error;
}
