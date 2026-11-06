import type { CropArea } from "../domain/photos";
import { ASPECT_RATIO, frameSize } from "../domain/photos";
import type { CropperEngine, CropSession } from "../ports/cropper";

/** Крок зуму кнопки чи клавіші (частка від поточного масштабу). */
const ZOOM_STEP = 0.1;
const JPEG_QUALITY = 0.92;

/**
 * Редактор кадрування на cropperjs 1.6.2 (не 2.x: інший API). Рамка стоїть, зумиться й рухається фото:
 * як у v1. cropperjs і його CSS вантажаться, коли користувач уперше обрав файл.
 */
export function createCropperjsEngine(): CropperEngine {
  // Один редактор на `<img>`: cropperjs сам не дозволяє другий (конструктор мовчки нічого не робить),
  // а React у dev-режимі монтує ефект двічі. Попередній знищується перед новим.
  const live = new WeakMap<HTMLImageElement, CropSession>();
  return {
    async mount(image, onArea) {
      const [{ default: Cropper }] = await Promise.all([import("cropperjs"), import("cropperjs/dist/cropper.css")]);
      live.get(image)?.destroy();
      // Масштаб «фото вміщається»: менше зменшувати не можна, інакше рамка вилізе за фото.
      let fit = 1;
      const cropper = new Cropper(image, {
        aspectRatio: ASPECT_RATIO,
        viewMode: 1,
        dragMode: "move",
        // Як у редакторах аватарок: рамку не тягають, тягають фото.
        cropBoxMovable: false,
        cropBoxResizable: false,
        autoCropArea: 0.9,
        background: false,
        toggleDragModeOnDblclick: false,
        ready() {
          const data = cropper.getImageData();
          fit = data.width / data.naturalWidth;
        },
        crop(event) {
          onArea({ width: Math.round(event.detail.width), height: Math.round(event.detail.height) });
        },
        zoom(event) {
          if (event.detail.ratio < fit) {
            event.preventDefault();
            cropper.zoomTo(fit);
          }
        },
      });
      let destroyed = false;
      const session: CropSession = {
        zoom: (direction) => cropper.zoom(direction * ZOOM_STEP),
        move: (dx, dy) => cropper.move(dx, dy),
        frame() {
          const data = cropper.getData(true);
          const size: CropArea = frameSize({ width: data.width, height: data.height });
          const canvas = cropper.getCroppedCanvas({
            width: size.width,
            height: size.height,
            fillColor: "#fff",
            imageSmoothingQuality: "high",
          });
          return new Promise((resolve, reject) => {
            canvas.toBlob(
              (blob) => (blob === null ? reject(new Error("Кадр не вдалося підготувати")) : resolve(blob)),
              "image/jpeg",
              JPEG_QUALITY,
            );
          });
        },
        destroy() {
          if (destroyed) {
            return;
          }
          destroyed = true;
          if (live.get(image) === session) {
            live.delete(image);
          }
          cropper.destroy();
        },
      };
      live.set(image, session);
      return session;
    },
  };
}
