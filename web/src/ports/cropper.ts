import type { CropArea } from "../domain/photos";

/** Відкритий редактор кадру над одним фото. */
export interface CropSession {
  /** Збільшити (`1`) чи зменшити (`-1`) фото під рамкою; менше за «фото вміщається» не зменшується. */
  zoom(direction: 1 | -1): void;
  /** Зсунути фото під рамкою на `dx`, `dy` екранних пікселів. */
  move(dx: number, dy: number): void;
  /** Кадр у рамці як JPEG: область у натуральних пікселях, не вища за `MAX_PHOTO_SIDE`, прозорість на білому. */
  frame(): Promise<Blob>;
  destroy(): void;
}

/** Редактор кадрування (у проді — cropperjs): рамка стоїть, фото зумиться й рухається під нею. */
export interface CropperEngine {
  /** `onArea` викликається, коли змінилась область у рамці (розмір у пікселях оригіналу). */
  mount(image: HTMLImageElement, onArea: (area: CropArea) => void): Promise<CropSession>;
}
