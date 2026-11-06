/** Захисні перевірки провайдерів фото: хуки без провайдера кидають зрозумілу помилку. */
import { act, render, renderHook, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import type { LoadPhotosOutcome, PhotosServices } from "../../application/photos";
import type { PhotoLibrary } from "../../domain/photos";
import type { CropperEngine } from "../../ports/cropper";
import { PhotosProvider, usePhotos } from "./PhotosProvider";
import { PhotosServicesProvider, useCropper, usePhotosServices } from "./PhotosServices";

// React друкує кинуту помилку хука в console.error: тут вона очікувана.
beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => undefined);
});
afterEach(() => {
  vi.restoreAllMocks();
});

test("usePhotosServices без провайдера", () => {
  expect(() => renderHook(() => usePhotosServices())).toThrow("Фото потребують PhotosServicesProvider");
});

test("useCropper без провайдера", () => {
  expect(() => renderHook(() => useCropper())).toThrow("Фото потребують PhotosServicesProvider");
});

test("usePhotos без провайдера", () => {
  expect(() => renderHook(() => usePhotos())).toThrow("usePhotos потребує PhotosProvider");
});

test("відповідь на застарілий запит не затирає свіжішу", async () => {
  const library = (id: number): PhotoLibrary => ({
    photos: [{ id, label: "", width: 858, height: 960, createdAt: "2026-10-21T09:00:00Z", lastUsedAt: null }],
    suggestedId: id,
  });
  const releases: ((outcome: LoadPhotosOutcome) => void)[] = [];
  const services: PhotosServices = {
    load: () =>
      new Promise((resolve) => {
        releases.push(resolve);
      }),
    upload: () => new Promise(() => undefined),
    remove: () => new Promise(() => undefined),
    imageUrl: (id) => `/api/photos/${id}.jpg`,
  };
  const cropper: CropperEngine = { mount: () => new Promise(() => undefined) };
  function Probe() {
    const { state, refresh } = usePhotos();
    return (
      <>
        <button onClick={() => void refresh()}>оновити</button>
        <output>{state.status === "ready" ? state.library.photos.map((photo) => photo.id).join(",") : state.status}</output>
      </>
    );
  }
  render(
    <PhotosServicesProvider services={services} cropper={cropper}>
      <PhotosProvider>
        <Probe />
      </PhotosProvider>
    </PhotosServicesProvider>,
  );
  await userEvent.click(screen.getByRole("button", { name: "оновити" }));
  // Перший запит (ensure) і другий (refresh) у польоті: відповідь другого приходить першою.
  await waitFor(() => expect(releases).toHaveLength(2));

  await act(async () => releases[1]?.({ ok: true, library: library(2) }));
  await act(async () => releases[0]?.({ ok: true, library: library(1) }));

  expect(screen.getByRole("status").textContent).toBe("2");
});
