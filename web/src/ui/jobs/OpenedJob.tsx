import { createContext, use } from "react";

/**
 * Остання відкрита вакансія: деталі її записують, список після повернення фокусує її назву.
 * Живе вище за маршрути області, тож працює однаково для кнопки, Escape і «Назад» браузера.
 */
export interface OpenedJob {
  remember(id: number): void;
  /** Віддає запамʼятований номер і забуває його: фокус повертається один раз. */
  take(): number | null;
}

export const OpenedJobContext = createContext<OpenedJob | null>(null);

export function useOpenedJob(): OpenedJob {
  const opened = use(OpenedJobContext);
  if (opened === null) {
    throw new Error("useOpenedJob потребує JobsArea");
  }
  return opened;
}
