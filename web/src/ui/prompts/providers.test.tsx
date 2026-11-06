/** Тексти запитів вантажаться один раз на всі кнопки сторінки; хук без провайдера кидає зрозумілу помилку. */
import { act, render, renderHook, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import type { PromptsServices } from "../../application/prompts";
import { PROMPT_KEYS, type Prompts } from "../../domain/prompts";
import { usePromptText, PromptsServicesProvider, useRefreshPrompts } from "./PromptsServices";

const PROMPTS = Object.fromEntries(PROMPT_KEYS.map((key) => [key, `{job_id}/${key}`])) as Prompts;

afterEach(() => {
  vi.restoreAllMocks();
});

function Probe({ id }: { id: number }) {
  const text = usePromptText({ key: "requests/analysis", values: { job_id: id } });
  return <p data-testid={`probe-${id}`}>{text.status === "ready" ? text.text : text.status}</p>;
}

function servicesOf(...outcomes: Array<Awaited<ReturnType<PromptsServices["load"]>> | Promise<Awaited<ReturnType<PromptsServices["load"]>>>>) {
  const load = vi.fn<PromptsServices["load"]>();
  for (const outcome of outcomes) {
    load.mockReturnValueOnce(Promise.resolve(outcome));
  }
  return { load };
}

describe("PromptsServicesProvider", () => {
  test("кілька споживачів на сторінці вантажать тексти один раз і бачать свої номери", async () => {
    const services = servicesOf({ ok: true, prompts: PROMPTS });

    render(
      <PromptsServicesProvider services={services}>
        <Probe id={1} />
        <Probe id={2} />
      </PromptsServicesProvider>,
    );

    expect((await screen.findByTestId("probe-1")).textContent).toBe("1/requests/analysis");
    expect(screen.getByTestId("probe-2").textContent).toBe("2/requests/analysis");
    expect(services.load).toHaveBeenCalledTimes(1);
  });

  test("сторінка з кнопками відкривається знову — тексти вже є, повторного запиту нема", async () => {
    const services = servicesOf({ ok: true, prompts: PROMPTS });
    function Page({ shown }: { shown: boolean }) {
      return <PromptsServicesProvider services={services}>{shown ? <Probe id={1} /> : null}</PromptsServicesProvider>;
    }
    const view = render(<Page shown />);
    await screen.findByText("1/requests/analysis");

    view.rerender(<Page shown={false} />);
    view.rerender(<Page shown />);

    expect(screen.getByTestId("probe-1").textContent).toBe("1/requests/analysis");
    expect(services.load).toHaveBeenCalledTimes(1);
  });

  test("поки тексти вантажаться — loading", () => {
    const services = { load: vi.fn<PromptsServices["load"]>(() => new Promise(() => undefined)) };

    render(
      <PromptsServicesProvider services={services}>
        <Probe id={1} />
      </PromptsServicesProvider>,
    );

    expect(screen.getByTestId("probe-1").textContent).toBe("loading");
  });

  test("збій завантаження — unavailable, а refresh пробує знову й виправляє стан", async () => {
    const services = servicesOf({ ok: false }, { ok: true, prompts: PROMPTS });
    function Refresh() {
      const refresh = useRefreshPrompts();
      return <button onClick={() => void refresh()}>refresh</button>;
    }

    render(
      <PromptsServicesProvider services={services}>
        <Probe id={1} />
        <Refresh />
      </PromptsServicesProvider>,
    );
    expect((await screen.findByTestId("probe-1")).textContent).toBe("unavailable");
    await act(async () => screen.getByRole("button", { name: "refresh" }).click());

    expect(screen.getByTestId("probe-1").textContent).toBe("1/requests/analysis");
    expect(services.load).toHaveBeenCalledTimes(2);
  });
});

describe("хуки без провайдера", () => {
  // React друкує кинуту помилку хука в console.error: тут вона очікувана.
  beforeEach(() => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
  });

  test("usePromptText", () => {
    expect(() => renderHook(() => usePromptText({ key: "requests/triage" }))).toThrow("usePromptText потребує PromptsServicesProvider");
  });
});
