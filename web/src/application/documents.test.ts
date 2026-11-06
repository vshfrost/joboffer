import { describe, expect, test, vi } from "vitest";

import {
  DocumentsForbiddenError,
  DocumentsNotFoundError,
  DocumentsUnauthorizedError,
  DocumentsUnavailableError,
} from "../domain/documentsErrors";
import type { DocumentsApi } from "../ports/documentsApi";
import { createDocumentsServices } from "./documents";

function servicesOver(list: DocumentsApi["list"]) {
  return createDocumentsServices({ list, pdfUrl: (id) => `/api/documents/${id}/pdf` });
}

describe("завантаження документів вакансії", () => {
  test("успіх: версії як є", async () => {
    const services = servicesOver(() => Promise.resolve([]));

    expect(await services.load(7)).toEqual({ ok: true, documents: [] });
  });

  test("запитує саме цю вакансію", async () => {
    const list = vi.fn<DocumentsApi["list"]>(() => Promise.resolve([]));

    await servicesOver(list).load(7);

    expect(list).toHaveBeenCalledWith(7);
  });

  test.each([
    [new DocumentsUnauthorizedError(), "unauthorized"],
    [new DocumentsForbiddenError(), "forbidden"],
    [new DocumentsNotFoundError(), "not-found"],
    [new DocumentsUnavailableError("збій"), "unavailable"],
  ])("%o → %s", async (error, kind) => {
    const services = servicesOver(() => Promise.reject(error));

    expect(await services.load(7)).toEqual({ ok: false, kind });
  });

  test("несподівана помилка не ковтається", async () => {
    const services = servicesOver(() => Promise.reject(new RangeError("баг")));

    await expect(services.load(7)).rejects.toThrow("баг");
  });
});

test("адреса PDF береться з порту", () => {
  expect(servicesOver(() => Promise.resolve([])).pdfUrl(3)).toBe("/api/documents/3/pdf");
});
