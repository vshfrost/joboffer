/** Підроблений бекенд фото для тестів: `/api/photos` над станом у памʼяті, решта запитів — профіль (хаб його вантажить). */
import { vi } from "vitest";

import { FULL_PROFILE, profileBackend, type ApiProfile } from "./profileBackend";
import { json, noContent } from "./testClient";

export interface ApiPhoto {
  photo_id: number;
  label: string;
  width: number;
  height: number;
  created_at: string;
  last_used_at: string | null;
}

export function apiPhoto(photo_id: number, overrides: Partial<ApiPhoto> = {}): ApiPhoto {
  return {
    photo_id,
    label: "",
    width: 858,
    height: 960,
    created_at: "2026-10-21T09:00:00Z",
    last_used_at: null,
    ...overrides,
  };
}

export interface PhotosOverrides {
  /** Відповідь на `GET /api/photos`; `undefined` — звичайна. */
  list?: () => Response | Promise<Response> | undefined;
  /** Відповідь на `POST /api/photos`; `undefined` — звичайна (фото додається). */
  upload?: (form: FormData) => Response | Promise<Response> | undefined;
  /** Відповідь на `DELETE /api/photos/<номер>`; `undefined` — звичайна (фото зникає). */
  remove?: (id: number) => Response | Promise<Response> | undefined;
}

export interface PhotosBackend {
  fetchFn: typeof fetch;
  /** Фото на «сервері». */
  photos: ApiPhoto[];
  /** Усі прийняті й відхилені завантаження: підпис і кадр. */
  uploads: { label: string; file: File }[];
  /** Номери, які просили видалити. */
  removeRequests: number[];
  listRequests: number;
}

const NEW_PHOTO_TIME = "2026-10-22T10:00:00Z";

/** Що сервер пропонує для CV: останнє використане, інакше найновіше. */
function suggested(photos: ApiPhoto[]): number | null {
  const used = photos.filter((photo) => photo.last_used_at !== null);
  const pool = used.length > 0 ? used : photos;
  const best = [...pool].sort((a, b) => (b.last_used_at ?? b.created_at).localeCompare(a.last_used_at ?? a.created_at) || b.photo_id - a.photo_id)[0];
  return best?.photo_id ?? null;
}

export function photosBackend(
  initial: ApiPhoto[] = [],
  overrides: PhotosOverrides = {},
  profile: ApiProfile = FULL_PROFILE,
): PhotosBackend {
  const rest = profileBackend(profile);
  const backend: PhotosBackend = { fetchFn: fetch, photos: structuredClone(initial), uploads: [], removeRequests: [], listRequests: 0 };
  backend.fetchFn = vi.fn<typeof fetch>((input, init) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.pathname : input.url;
    const method = init?.method ?? "GET";
    if (url === "/api/photos" && method === "GET") {
      backend.listRequests += 1;
      const custom = overrides.list?.();
      const ordered = [...backend.photos].sort((a, b) => b.created_at.localeCompare(a.created_at) || b.photo_id - a.photo_id);
      return Promise.resolve(custom ?? json(200, { photos: ordered, suggested_photo_id: suggested(backend.photos) }));
    }
    if (url === "/api/photos" && method === "POST") {
      const form = init?.body;
      if (!(form instanceof FormData)) {
        return Promise.reject(new Error("Завантаження фото має бути multipart-формою"));
      }
      const file = form.get("file");
      const label = form.get("label");
      if (!(file instanceof File) || typeof label !== "string") {
        return Promise.reject(new Error("У формі нема file чи label"));
      }
      backend.uploads.push({ label, file });
      const custom = overrides.upload?.(form);
      if (custom !== undefined) {
        return Promise.resolve(custom);
      }
      const photo = apiPhoto(Math.max(0, ...backend.photos.map((item) => item.photo_id)) + 1, { label, created_at: NEW_PHOTO_TIME });
      backend.photos.push(photo);
      return Promise.resolve(json(201, photo));
    }
    const removal = /^\/api\/photos\/(\d+)$/.exec(url);
    if (removal !== null && method === "DELETE") {
      const id = Number(removal[1]);
      backend.removeRequests.push(id);
      const custom = overrides.remove?.(id);
      if (custom !== undefined) {
        return Promise.resolve(custom);
      }
      backend.photos = backend.photos.filter((photo) => photo.photo_id !== id);
      return Promise.resolve(noContent());
    }
    return rest.fetchFn(input, init);
  });
  return backend;
}

/** 422 сервера на кадр, який той не прийняв: текст — як у v1. */
export function rejected(message: string): Response {
  return json(422, { code: "invalid_value", message, field_errors: [{ field: "file", message }], correlation_id: "test" });
}
