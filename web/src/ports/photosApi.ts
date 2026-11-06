import type { Photo, PhotoLibrary } from "../domain/photos";

/** API фото для шапки CV. Помилки — з `domain/photosErrors`. */
export interface PhotosApi {
  /** Фото користувача, новіші першими, і те, що пропонувати. Кидає PhotosUnauthorizedError або PhotosUnavailableError. */
  list(): Promise<PhotoLibrary>;
  /** Зберігає кадр. Кидає PhotosRejectedError (422), PhotosUnauthorizedError або PhotosUnavailableError. */
  upload(frame: Blob, label: string): Promise<Photo>;
  /** Видаляє фото; збережені CV не змінюються. Кидає PhotosNotFoundError, PhotosUnauthorizedError або PhotosUnavailableError. */
  remove(id: number): Promise<void>;
  /** Адреса JPEG фото: нативний `<img>` з тією ж сесією. */
  imageUrl(id: number): string;
}
