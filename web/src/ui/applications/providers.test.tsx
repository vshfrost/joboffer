import { render } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { useApplicationsServices } from "./ApplicationsServices";

afterEach(() => {
  vi.restoreAllMocks();
});

function Probe() {
  useApplicationsServices();
  return null;
}

test("подачі без провайдера сервісів — помилка збирання, а не тихий збій", () => {
  vi.spyOn(console, "error").mockImplementation(() => {});

  expect(() => render(<Probe />)).toThrow("useApplicationsServices потребує ApplicationsServicesProvider");
});
