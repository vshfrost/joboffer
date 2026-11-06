import { describe, expect, test } from "vitest";

import {
  addedText,
  cropProblem,
  fileProblem,
  frameSize,
  MAX_UPLOAD_BYTES,
  photoName,
  summarizePhotos,
  usedText,
  type Photo,
} from "./photos";

function photo(id: number, overrides: Partial<Photo> = {}): Photo {
  return { id, label: "", width: 858, height: 960, createdAt: "2026-10-21T09:00:00Z", lastUsedAt: null, ...overrides };
}

describe("файл для кадрування", () => {
  test.each(["image/jpeg", "image/png", "image/webp"])("%s годиться", (type) => {
    expect(fileProblem({ type, size: 1000 })).toBeNull();
  });

  test("порожній файл", () => {
    expect(fileProblem({ type: "image/jpeg", size: 0 })).toBe("Файл порожній — вибери фото.");
  });

  test.each(["image/gif", "image/bmp", "text/plain", "application/pdf", ""])("«%s» — не фото", (type) => {
    expect(fileProblem({ type, size: 1000 })).toBe("Фото — JPEG, PNG або WebP.");
  });

  test("рівно 15 МБ годиться, на байт більше — ні", () => {
    expect(fileProblem({ type: "image/png", size: MAX_UPLOAD_BYTES })).toBeNull();
    expect(fileProblem({ type: "image/png", size: MAX_UPLOAD_BYTES + 1 })).toBe("Фото — до 15 МБ.");
  });
});

describe("область у рамці", () => {
  test("300 px і ширше годиться", () => {
    expect(cropProblem(300)).toBeNull();
    expect(cropProblem(1200)).toBeNull();
  });

  test("вужча за 300 px: пояснення з поточною шириною", () => {
    expect(cropProblem(299)).toBe("Обрана область вужча за 300 px (зараз 299) — зменш зум або візьми фото кращої якості.");
    expect(cropProblem(1)).toBe("Обрана область вужча за 300 px (зараз 1) — зменш зум або візьми фото кращої якості.");
  });
});

describe("розмір кадру, що йде на сервер", () => {
  test("кадр у межах 900 px лишається як є", () => {
    expect(frameSize({ width: 429, height: 480 })).toEqual({ width: 429, height: 480 });
    expect(frameSize({ width: 804, height: 900 })).toEqual({ width: 804, height: 900 });
  });

  test("вищий за 900 px зменшується пропорційно, як на сервері", () => {
    expect(frameSize({ width: 858, height: 960 })).toEqual({ width: 804, height: 900 });
    expect(frameSize({ width: 1716, height: 1920 })).toEqual({ width: 804, height: 900 });
  });
});

describe("підписи й дати", () => {
  test("назва: підпис або номер", () => {
    expect(photoName(photo(3, { label: "Ділове" }))).toBe("Ділове");
    expect(photoName(photo(3))).toBe("Фото #3");
  });

  test("«додано» — день за Мадридом, а не за UTC", () => {
    expect(addedText(photo(1, { createdAt: "2026-10-21T22:30:00Z" }))).toBe("Додано 2026-10-22");
    expect(addedText(photo(1, { createdAt: "2026-10-21T09:00:00Z" }))).toBe("Додано 2026-10-21");
  });

  test("«востаннє в CV» — день за Мадридом або «ще не використовувалось»", () => {
    expect(usedText(photo(1, { lastUsedAt: "2026-10-21T22:30:00Z" }))).toBe("У CV: 2026-10-22");
    expect(usedText(photo(1))).toBe("Ще не використовувалось");
  });
});

describe("картка огляду профілю", () => {
  test("без фото — окремий стан, а не «0»", () => {
    expect(summarizePhotos({ photos: [], suggestedId: null })).toEqual({ empty: true, lines: ["Фото ще не додано"] });
  });

  test("кількість і день, коли додано найновіше", () => {
    const newest = photo(2, { createdAt: "2026-10-22T10:00:00Z" });
    expect(summarizePhotos({ photos: [newest, photo(1)], suggestedId: 2 })).toEqual({
      empty: false,
      lines: ["2 фото", "Останнє додано 2026-10-22"],
    });
  });

  test("одне й п'ять фото — «фото» не змінюється", () => {
    expect(summarizePhotos({ photos: [photo(1)], suggestedId: 1 }).lines[0]).toBe("1 фото");
    const five = [5, 4, 3, 2, 1].map((id) => photo(id));
    expect(summarizePhotos({ photos: five, suggestedId: 5 }).lines[0]).toBe("5 фото");
  });
});
