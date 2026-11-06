import { createContext, use, type ReactNode } from "react";

import type { PhotosServices } from "../../application/photos";
import type { CropperEngine } from "../../ports/cropper";

interface PhotosContextValue {
  services: PhotosServices;
  cropper: CropperEngine;
}

const PhotosContext = createContext<PhotosContextValue | null>(null);

/** Сервіси фото й редактор кадрування: тест підставляє двійник редактора на межі. */
export function PhotosServicesProvider({ services, cropper, children }: PhotosContextValue & { children: ReactNode }) {
  return <PhotosContext value={{ services, cropper }}>{children}</PhotosContext>;
}

function usePhotosContext(): PhotosContextValue {
  const value = use(PhotosContext);
  if (value === null) {
    throw new Error("Фото потребують PhotosServicesProvider");
  }
  return value;
}

export function usePhotosServices(): PhotosServices {
  return usePhotosContext().services;
}

export function useCropper(): CropperEngine {
  return usePhotosContext().cropper;
}
