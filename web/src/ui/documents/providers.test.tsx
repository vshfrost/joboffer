import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, expect, test, vi } from "vitest";

import { DocumentsPanel } from "./DocumentsPanel";

afterEach(() => {
  vi.restoreAllMocks();
});

test("блок документів без провайдера сервісів — помилка збирання, а не тихий збій", () => {
  vi.spyOn(console, "error").mockImplementation(() => {});

  expect(() =>
    render(
      <MemoryRouter>
        <DocumentsPanel jobId={1} canRequest />
      </MemoryRouter>,
    ),
  ).toThrow("useDocumentsServices потребує DocumentsServicesProvider");
});
