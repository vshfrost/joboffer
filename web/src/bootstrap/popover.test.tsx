/** Popover дизайн-системи: підказка біля елемента, яка відкривається за запитом і не губить фокус. */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { setViewport } from "./viewport";
import { Popover, PopoverClose, PopoverContent, PopoverTrigger } from "../ui/components/popover";

function Demo() {
  return (
    <>
      <button type="button">Поза поповером</button>
      <Popover>
        <PopoverTrigger>Що це?</PopoverTrigger>
        <PopoverContent aria-label="Про крок">
          <p>Текст підказки</p>
          <PopoverClose>Закрити підказку</PopoverClose>
        </PopoverContent>
      </Popover>
    </>
  );
}

async function openPopover() {
  const user = userEvent.setup();
  render(<Demo />);
  const trigger = screen.getByRole("button", { name: "Що це?" });
  await user.click(trigger);
  const dialog = await screen.findByRole("dialog", { name: "Про крок" });
  return { user, trigger, dialog };
}

describe("відкриття й закриття", () => {
  test("клік по тригеру показує вміст, повторний клік ховає", async () => {
    const { user, trigger, dialog } = await openPopover();
    expect(within(dialog).getByText("Текст підказки")).toBeDefined();

    await user.click(trigger);

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  test("кнопка закриття всередині ховає вміст, фокус повертається на тригер", async () => {
    const { user, trigger, dialog } = await openPopover();

    await user.click(within(dialog).getByRole("button", { name: "Закрити підказку" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(document.activeElement).toBe(trigger);
  });

  test("Escape закриває вміст, фокус повертається на тригер", async () => {
    const { user, trigger } = await openPopover();

    await user.keyboard("{Escape}");

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(document.activeElement).toBe(trigger);
  });

  test("клік поза поповером закриває його", async () => {
    const { user } = await openPopover();

    await user.click(screen.getByRole("button", { name: "Поза поповером" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  test("клік усередині вмісту його не закриває", async () => {
    const { user, dialog } = await openPopover();

    await user.click(within(dialog).getByText("Текст підказки"));

    expect(screen.getByRole("dialog", { name: "Про крок" })).toBeDefined();
  });
});

describe("атрибути доступності", () => {
  test("тригер: aria-haspopup=dialog, aria-expanded міняється, aria-controls вказує на вміст", async () => {
    const user = userEvent.setup();
    render(<Demo />);
    const trigger = screen.getByRole("button", { name: "Що це?" });
    expect(trigger.getAttribute("aria-haspopup")).toBe("dialog");
    expect(trigger.getAttribute("aria-expanded")).toBe("false");

    await user.click(trigger);

    const dialog = await screen.findByRole("dialog", { name: "Про крок" });
    expect(trigger.getAttribute("aria-expanded")).toBe("true");
    expect(trigger.getAttribute("aria-controls")).toBe(dialog.id);
  });
});

describe("розкладка", () => {
  test("на широкому екрані вміст прикріплений до тригера", async () => {
    setViewport("desktop");
    const { dialog } = await openPopover();
    expect(dialog.getAttribute("data-layout")).toBe("anchored");
  });

  test("на вузькому (375 px) вміст — картка внизу екрана", async () => {
    setViewport("mobile");
    const { dialog } = await openPopover();
    expect(dialog.getAttribute("data-layout")).toBe("bottom-card");
  });
});
