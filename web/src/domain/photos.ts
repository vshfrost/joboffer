/** Фото для шапки CV: галерея, правила кадру й тексти. Значення збігаються з API (`/api/photos`) і з правилами сервера. */
import { madridDay } from "./jobs";
import type { Summary } from "./profileSummary";

/** Рамка фото в шапці CV (пікселі зразка): пропорції 858 × 960. */
export const FRAME = { width: 858, height: 960 } as const;
export const ASPECT_RATIO = FRAME.width / FRAME.height;
/** Не вужча за це область фото, яку зберігаємо (≈ 214 dpi в рамці 101 pt). */
export const MIN_CROP_WIDTH = 300;
/** Сторона збереженого кадру не більша за це: так само зменшує сервер. */
export const MAX_PHOTO_SIDE = 900;
export const MAX_UPLOAD_BYTES = 15 * 1024 * 1024;
export const MAX_LABEL_LENGTH = 100;
export const ACCEPTED_TYPES = ["image/jpeg", "image/png", "image/webp"] as const;

export interface Photo {
  /** Номер фото в межах користувача. */
  id: number;
  /** Підпис; порожній, якщо не вказано. */
  label: string;
  width: number;
  height: number;
  /** Коли додано, ISO 8601. */
  createdAt: string;
  /** Коли востаннє пішло в CV, ISO 8601; `null` — ще не використовувалось. */
  lastUsedAt: string | null;
}

export interface PhotoLibrary {
  /** Новіші першими. */
  photos: Photo[];
  /** Що пропонувати для CV: останнє використане, інакше найновіше; `null` — фото нема. */
  suggestedId: number | null;
}

/** Область фото в рамці, у пікселях оригіналу. */
export interface CropArea {
  width: number;
  height: number;
}

/** Чому обраний файл не годиться для кадрування; `null` — годиться. Тексти й порядок перевірок — як на сервері. */
export function fileProblem(file: { type: string; size: number }): string | null {
  if (file.size === 0) {
    return "Файл порожній — вибери фото.";
  }
  if (!(ACCEPTED_TYPES as readonly string[]).includes(file.type)) {
    return "Фото — JPEG, PNG або WebP.";
  }
  return file.size > MAX_UPLOAD_BYTES ? `Фото — до ${MAX_UPLOAD_BYTES / (1024 * 1024)} МБ.` : null;
}

/** Чому область не можна зберегти; `null` — можна. */
export function cropProblem(width: number): string | null {
  return width < MIN_CROP_WIDTH
    ? `Обрана область вужча за ${MIN_CROP_WIDTH} px (зараз ${width}) — зменш зум або візьми фото кращої якості.`
    : null;
}

/** Розмір кадру, який піде на сервер: область у натуральних пікселях, але не вища за `MAX_PHOTO_SIDE`. */
export function frameSize(area: CropArea): CropArea {
  const scale = Math.min(1, MAX_PHOTO_SIDE / area.height);
  return { width: Math.round(area.width * scale), height: Math.round(area.height * scale) };
}

export function photoName(photo: Photo): string {
  return photo.label === "" ? `Фото #${photo.id}` : photo.label;
}

export function addedText(photo: Photo): string {
  return `Додано ${madridDay(photo.createdAt)}`;
}

export function usedText(photo: Photo): string {
  return photo.lastUsedAt === null ? "Ще не використовувалось" : `У CV: ${madridDay(photo.lastUsedAt)}`;
}

/** Картка огляду профілю: кількість і день, коли додано останнє (галерея приходить новішими першими). */
export function summarizePhotos(library: PhotoLibrary): Summary {
  const newest = library.photos[0];
  if (newest === undefined) {
    return { empty: true, lines: ["Фото ще не додано"] };
  }
  return { empty: false, lines: [`${library.photos.length} фото`, `Останнє додано ${madridDay(newest.createdAt)}`] };
}
