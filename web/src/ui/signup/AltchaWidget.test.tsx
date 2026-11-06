import { act, render } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import { AltchaWidget } from "./AltchaWidget";

const CHALLENGE_URL = "/api/auth/challenge";

function setup() {
  const onSolved = vi.fn<(payload: string) => void>();
  const onReset = vi.fn<() => void>();
  const { container } = render(<AltchaWidget challengeUrl={CHALLENGE_URL} onSolved={onSolved} onReset={onReset} />);
  const widget = container.querySelector("altcha-widget");
  if (widget === null) {
    throw new Error("altcha-widget не відрендерено");
  }
  const state = (value: string, payload?: string) => {
    act(() => {
      widget.dispatchEvent(new CustomEvent("statechange", { detail: { state: value, payload } }));
    });
  };
  return { widget, state, onSolved, onReset };
}

describe("віджет ALTCHA", () => {
  test("задачу бере з адреси, яку йому дали, на тому ж origin", () => {
    const { widget } = setup();

    expect(widget.getAttribute("challengeurl")).toBe(CHALLENGE_URL);
  });

  test("скрипт воркера лежить на нашому origin, а не на CDN", () => {
    const { widget } = setup();

    const workerUrl = widget.getAttribute("workerurl") ?? "";
    expect(workerUrl).not.toBe("");
    expect(new URL(workerUrl, "http://app.test").origin).toBe("http://app.test");
  });

  test("віджет не підтягує жодних зовнішніх скриптів і стилів", () => {
    setup();

    const external = [...document.querySelectorAll("script[src], link[href], iframe[src]")]
      .map((element) => element.getAttribute("src") ?? element.getAttribute("href") ?? "")
      .filter((url) => new URL(url, "http://app.test").origin !== "http://app.test");
    expect(external).toEqual([]);
  });

  test("перевірено — розв'язок віддається нагору", () => {
    const { state, onSolved, onReset } = setup();

    state("verified", "eyJhbGdvcml0aG0iOiJTSEEtMjU2In0=");

    expect(onSolved).toHaveBeenCalledWith("eyJhbGdvcml0aG0iOiJTSEEtMjU2In0=");
    expect(onReset).not.toHaveBeenCalled();
  });

  test.each(["expired", "error", "unverified", "verifying"])("стан «%s» скидає розв'язок", (value) => {
    const { state, onSolved, onReset } = setup();

    state(value);

    expect(onReset).toHaveBeenCalledTimes(1);
    expect(onSolved).not.toHaveBeenCalled();
  });
});
