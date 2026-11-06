import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { FULL_PROFILE, profileBackend, validationError } from "./profileBackend";
import { renderClient } from "./testClient";

async function setup(path: string, heading: string, overrides: Parameters<typeof profileBackend>[1] = {}) {
  const backend = profileBackend(FULL_PROFILE, overrides);
  renderClient(path, backend.fetchFn);
  await screen.findByRole("heading", { level: 1, name: heading });
  return { backend, user: userEvent.setup() };
}

describe("клавіатура й фокус", () => {
  test("відкриття розділу карткою переносить фокус на перше поле", async () => {
    const backend = profileBackend();
    renderClient("/profile", backend.fetchFn);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("link", { name: /Кар’єрна ціль/ }));
    await screen.findByRole("heading", { level: 1, name: "Кар’єрна ціль" });
    expect(document.activeElement).toBe(screen.getByLabelText("Цільові ролі"));
  });

  test("повернення до огляду повертає фокус на картку, з якої розділ відкрито", async () => {
    const { user } = await setup("/profile/contacts", "Контакти для CV");
    await user.click(screen.getByRole("link", { name: /Огляд профілю/ }));
    await screen.findByRole("heading", { level: 1, name: "Профіль" });
    expect(document.activeElement).toBe(
      within(screen.getByRole("heading", { level: 2, name: "Контакти для CV" }).closest("li") as HTMLElement).getByRole("link"),
    );
  });

  test("Tab у «Цілі» йде за візуальним порядком: ролі, рівні, зарплата, галузі, кнопки", async () => {
    const { user } = await setup("/profile/target", "Кар’єрна ціль");
    await user.type(screen.getByLabelText("Цільові ролі"), " ");
    const expected = [
      ...["Junior", "Middle", "Senior", "Lead", "Principal"].map((level) => screen.getByRole("checkbox", { name: level })),
      screen.getByLabelText("Мінімальна зарплата"),
      screen.getByLabelText("Цільові галузі"),
      screen.getByRole("button", { name: "Скасувати" }),
      screen.getByRole("button", { name: "Зберегти зміни" }),
    ];
    for (const element of expected) {
      await user.tab();
      expect(document.activeElement).toBe(element);
    }
  });

  test("рівень перемикається пробілом", async () => {
    const { user } = await setup("/profile/target", "Кар’єрна ціль");
    const junior = screen.getByRole("checkbox", { name: "Junior" });
    junior.focus();
    await user.keyboard(" ");
    expect(junior.getAttribute("aria-checked")).toBe("true");
  });

  test("неактивні кнопки не потрапляють у Tab", async () => {
    const { user } = await setup("/profile/contacts", "Контакти для CV");
    screen.getByLabelText("Дозвіл на роботу").focus();
    await user.tab();
    expect(document.activeElement?.tagName).not.toBe("BUTTON");
  });
});

describe("підписи, aria і статуси", () => {
  test("кожне поле має видиму підпис-мітку", async () => {
    await setup("/profile/target", "Кар’єрна ціль");
    for (const label of ["Цільові ролі", "Мінімальна зарплата", "Цільові галузі"]) {
      const control = screen.getByLabelText(label);
      const labelElement = document.querySelector(`label[for="${control.id}"]`);
      expect(labelElement?.textContent).toContain(label);
    }
    expect(screen.getByRole("group", { name: "Рівень" })).toBeDefined();
  });

  test("підказки полів прив’язані через aria-describedby", async () => {
    await setup("/profile/target", "Кар’єрна ціль");
    const roles = screen.getByLabelText("Цільові ролі");
    const hint = (roles.getAttribute("aria-describedby") ?? "")
      .split(" ")
      .map((id) => document.getElementById(id)?.textContent);
    expect(hint).toContain("Одна роль на рядок.");
  });

  test("локальне меню має назву, а поточний розділ — aria-current", async () => {
    await setup("/profile/target", "Кар’єрна ціль");
    const nav = screen.getByRole("navigation", { name: "Розділи профілю" });
    const current = within(nav)
      .getAllByRole("link")
      .filter((link) => link.getAttribute("aria-current") === "page");
    expect(current.map((link) => link.textContent)).toEqual(["Кар’єрна ціль"]);
  });

  test("статус збереження — role=status, помилка — role=alert", async () => {
    const { user } = await setup("/profile/contacts", "Контакти для CV", {
      "PUT /api/profile/contacts": () => validationError(["email", "Email виглядає некоректно, напр. name@example.com."]),
    });
    expect(screen.getByRole("status")).toBeDefined();
    await user.type(screen.getByLabelText("Email"), "x");
    await user.click(screen.getByRole("button", { name: "Зберегти зміни" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Перевір поля з помилками");
  });

  test("мобільний вибір розділу — select з назвою, перемикає розділ", async () => {
    const { user } = await setup("/profile/target", "Кар’єрна ціль");
    const select = screen.getByRole("combobox", { name: "Розділ профілю" });
    await user.selectOptions(select, "Контакти для CV");
    expect(await screen.findByRole("heading", { level: 1, name: "Контакти для CV" })).toBeDefined();
    expect(screen.getByTestId("location").textContent).toBe("/profile/contacts");
  });
});
