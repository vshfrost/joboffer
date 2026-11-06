import { createContext, use, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import type { PhotoLibrary } from "../../domain/photos";
import { usePhotosServices } from "./PhotosServices";

export type PhotosProblem = "unauthorized" | "unavailable";

export type PhotosState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; problem: PhotosProblem }
  | { status: "ready"; library: PhotoLibrary };

interface PhotosContextValue {
  state: PhotosState;
  /** Завантажує список, якщо його ще не просили: огляд і розділ ділять один стан. */
  ensure(): void;
  /** Повтор після помилки: знову «завантаження». */
  retry(): void;
  /** Тихо оновлює список після змін (додавання, видалення): старий лишається, доки не прийде новий. */
  refresh(): Promise<void>;
}

const PhotosContext = createContext<PhotosContextValue | null>(null);

/** Список фото на час візиту в профіль; сам не вантажиться, доки його не попросять `usePhotos`. */
export function PhotosProvider({ children }: { children: ReactNode }) {
  const services = usePhotosServices();
  const [state, setState] = useState<PhotosState>({ status: "idle" });
  const started = useRef(false);
  const latest = useRef(0);

  const load = useCallback(
    async (showLoading: boolean) => {
      latest.current += 1;
      const request = latest.current;
      if (showLoading) {
        setState({ status: "loading" });
      }
      const outcome = await services.load();
      // Відповідь на застарілий запит не затирає свіжішу.
      if (request === latest.current) {
        setState(outcome.ok ? { status: "ready", library: outcome.library } : { status: "error", problem: outcome.kind });
      }
    },
    [services],
  );

  const ensure = useCallback(() => {
    if (!started.current) {
      started.current = true;
      void load(true);
    }
  }, [load]);
  const retry = useCallback(() => void load(true), [load]);
  const refresh = useCallback(() => load(false), [load]);

  const value = useMemo(() => ({ state, ensure, retry, refresh }), [state, ensure, retry, refresh]);
  return <PhotosContext value={value}>{children}</PhotosContext>;
}

/** Стан списку фото; перший виклик запускає завантаження. */
export function usePhotos(): PhotosContextValue {
  const value = use(PhotosContext);
  if (value === null) {
    throw new Error("usePhotos потребує PhotosProvider");
  }
  const { ensure } = value;
  useEffect(() => ensure(), [ensure]);
  return value;
}
