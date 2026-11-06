import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { CodeField } from "./CodeField";

function setup(props: { error?: string; disabled?: boolean } = {}) {
  const onComplete = vi.fn<(code: string) => void>();
  const user = userEvent.setup();
  render(<CodeField onComplete={onComplete} {...props} />);
  const input = screen.getByLabelText("Код з листа") as HTMLInputElement;
  return { user, input, onComplete };
}

describe("поле коду з листа", () => {
  test("це одне поле з автозаповненням одноразового коду й цифровою клавіатурою", () => {
    const { input } = setup();

    expect(input.getAttribute("autocomplete")).toBe("one-time-code");
    expect(input.getAttribute("inputmode")).toBe("numeric");
  });

  test("код, вставлений одним рухом, заповнює поле й одразу завершує введення", async () => {
    const { user, input, onComplete } = setup();

    await user.click(input);
    await user.paste("123456");

    expect(input.value).toBe("123456");
    expect(onComplete).toHaveBeenCalledTimes(1);
    expect(onComplete).toHaveBeenCalledWith("123456");
  });

  test("пробіли й дефіси у вставленому коді відкидаються", async () => {
    const { user, input, onComplete } = setup();

    await user.click(input);
    await user.paste("123 456");

    expect(input.value).toBe("123456");
    expect(onComplete).toHaveBeenCalledWith("123456");
  });

  test("зайві цифри після шостої відкидаються", async () => {
    const { user, input, onComplete } = setup();

    await user.click(input);
    await user.paste("1234567890");

    expect(input.value).toBe("123456");
    expect(onComplete).toHaveBeenCalledTimes(1);
    expect(onComplete).toHaveBeenCalledWith("123456");
  });

  test("набраний по одній цифрі код завершується на шостій, не раніше", async () => {
    const { user, input, onComplete } = setup();

    await user.type(input, "12345");
    expect(onComplete).not.toHaveBeenCalled();

    await user.type(input, "6");
    expect(onComplete).toHaveBeenCalledTimes(1);
    expect(onComplete).toHaveBeenCalledWith("123456");
  });

  test("літери не потрапляють у поле", async () => {
    const { user, input, onComplete } = setup();

    await user.type(input, "ab1c2");

    expect(input.value).toBe("12");
    expect(onComplete).not.toHaveBeenCalled();
  });

  test("повідомлення про помилку стоїть під полем і повʼязане з ним", () => {
    const { input } = setup({ error: "Невірний код. Залишилось спроб: 3" });

    const message = screen.getByText("Невірний код. Залишилось спроб: 3");
    expect(input.getAttribute("aria-invalid")).toBe("true");
    expect(input.getAttribute("aria-describedby")).toBe(message.id);
  });

  test("поки запит іде, поле вимкнено", () => {
    const { input } = setup({ disabled: true });

    expect(input.disabled).toBe(true);
  });
});
