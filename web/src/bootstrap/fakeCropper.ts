/** Двійник редактора кадрування на межі `CropperEngine`: cropperjs у jsdom не працює (нема canvas). */
import { act } from "@testing-library/react";

import type { CropArea } from "../domain/photos";
import type { CropperEngine, CropSession } from "../ports/cropper";

export class FakeSession implements CropSession {
  /** Що викликали: «zoom 1», «move -10 0», «frame», «destroy». */
  calls: string[] = [];
  destroyed = false;
  /** Кадр, який «редактор» віддасть; `null` — підготувати не вдасться. */
  frameBlob: Blob | null = new Blob(["frame-jpeg"], { type: "image/jpeg" });

  constructor(
    readonly image: HTMLImageElement,
    private readonly onArea: (area: CropArea) => void,
  ) {}

  /** Користувач змінив область: редактор повідомляє розмір у пікселях оригіналу. */
  area(width: number, height = Math.round((width * 960) / 858)): void {
    act(() => this.onArea({ width, height }));
  }

  zoom(direction: 1 | -1): void {
    this.calls.push(`zoom ${direction}`);
  }

  move(dx: number, dy: number): void {
    this.calls.push(`move ${dx} ${dy}`);
  }

  frame(): Promise<Blob> {
    this.calls.push("frame");
    return this.frameBlob === null ? Promise.reject(new Error("canvas порожній")) : Promise.resolve(this.frameBlob);
  }

  destroy(): void {
    this.calls.push("destroy");
    this.destroyed = true;
  }
}

export interface FakeCropper {
  engine: CropperEngine;
  /** Усі відкриті редактори в порядку відкриття. */
  sessions: FakeSession[];
  /** Останній відкритий редактор. */
  current(): FakeSession;
  /** Відкладає готовність нових редакторів (завантаження cropperjs ще триває); повертає «відпустити». */
  hold(): () => void;
}

export function fakeCropper(): FakeCropper {
  const sessions: FakeSession[] = [];
  let gate: Promise<void> = Promise.resolve();
  return {
    sessions,
    engine: {
      mount(image, onArea) {
        const session = new FakeSession(image, onArea);
        sessions.push(session);
        return gate.then(() => session);
      },
    },
    hold() {
      let release: () => void = () => {};
      gate = new Promise<void>((resolve) => {
        release = resolve;
      });
      return release;
    },
    current() {
      const session = sessions.at(-1);
      if (session === undefined) {
        throw new Error("Редактор кадрування ще не відкрито");
      }
      return session;
    },
  };
}

/** jsdom не має `URL.createObjectURL`: підставляємо лічильник адрес і запамʼятовуємо відкликані. */
export function stubObjectUrls(): { created: string[]; revoked: string[] } {
  const record = { created: [] as string[], revoked: [] as string[] };
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    writable: true,
    value: () => {
      const url = `blob:photo-${record.created.length + 1}`;
      record.created.push(url);
      return url;
    },
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    configurable: true,
    writable: true,
    value: (url: string) => {
      record.revoked.push(url);
    },
  });
  return record;
}
