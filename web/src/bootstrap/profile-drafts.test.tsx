import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { profileBackend } from "./profileBackend";
import { renderClient } from "./testClient";

const field = (label: string) => screen.getByLabelText(label) as HTMLInputElement | HTMLTextAreaElement;
const location = () => screen.getByTestId("location").textContent;
const localNav = () => screen.getByRole("navigation", { name: "Розділи профілю" });

async function openTarget() {
  const backend = profileBackend();
  const view = renderClient("/profile/target", backend.fetchFn);
  await screen.findByRole("heading", { level: 1, name: "Кар’єрна ціль" });
  return { backend, view, user: userEvent.setup() };
}

async function goTo(user: ReturnType<typeof userEvent.setup>, name: RegExp | string) {
  await user.click(within(localNav()).getByRole("link", { name }));
}

describe("чернетки", () => {
  test("чернетка «Цілі» переживає перехід у «Контакти» і назад", async () => {
    const { user } = await openTarget();
    await user.type(field("Цільові ролі"), "\nQA");
    await goTo(user, /Контакти для CV/);
    expect(await screen.findByRole("heading", { level: 1, name: "Контакти для CV" })).toBeDefined();
    await goTo(user, /Кар’єрна ціль/);
    expect(field("Цільові ролі").value).toBe("Backend Engineer\nSRE\nQA");
    expect(screen.getByRole("status").textContent).toBe("Є незбережені зміни");
  });

  test("зміни в різних розділах живуть паралельно", async () => {
    const { user } = await openTarget();
    await user.type(field("Цільові ролі"), "\nQA");
    await goTo(user, /Контакти для CV/);
    await user.clear(field("Місто"));
    await user.type(field("Місто"), "Madrid");
    await goTo(user, /Кар’єрна ціль/);
    expect(field("Цільові ролі").value).toContain("QA");
    await goTo(user, /Контакти для CV/);
    expect(field("Місто").value).toBe("Madrid");
  });

  test("змінений розділ позначено в локальному меню текстом, а не лише кольором", async () => {
    const { user } = await openTarget();
    expect(within(localNav()).queryByRole("link", { name: /є незбережені зміни/ })).toBeNull();
    await user.type(field("Цільові ролі"), "\nQA");
    await goTo(user, /Контакти для CV/);
    expect(within(localNav()).getByRole("link", { name: "Кар’єрна ціль, є незбережені зміни" })).toBeDefined();
    expect(within(localNav()).getByRole("link", { name: "Контакти для CV" })).toBeDefined();
  });

  test("огляд показує, які розділи змінено, а картки — позначку", async () => {
    const { user } = await openTarget();
    await user.type(field("Цільові ролі"), "\nQA");
    await goTo(user, /Контакти для CV/);
    await user.clear(field("Email"));
    await goTo(user, /Огляд профілю/);
    const banner = await screen.findByText(/Незбережені зміни:/);
    expect(banner.textContent).toContain("Кар’єрна ціль");
    expect(banner.textContent).toContain("Контакти для CV");
    expect(banner.textContent).not.toContain("Правила відбору");
    const cardOf = (title: string) => screen.getByRole("heading", { level: 2, name: title }).closest("li") as HTMLElement;
    expect(within(cardOf("Кар’єрна ціль")).getByText("Є зміни")).toBeDefined();
    expect(within(cardOf("Контакти для CV")).getByText("Є зміни")).toBeDefined();
    expect(within(cardOf("Правила відбору")).queryByText("Є зміни")).toBeNull();
  });

  test("огляд показує збережене, а не чернетку", async () => {
    const { user } = await openTarget();
    await user.clear(field("Цільові ролі"));
    await user.type(field("Цільові ролі"), "Draft Role");
    await goTo(user, /Огляд профілю/);
    const heading = await screen.findByRole("heading", { level: 2, name: "Кар’єрна ціль" });
    expect(heading.closest("li")?.textContent).toContain("Backend Engineer · SRE");
    expect(heading.closest("li")?.textContent).not.toContain("Draft Role");
  });

  test("після збереження позначка розділу зникає, чернетка стає збереженим", async () => {
    const { user } = await openTarget();
    await user.type(field("Цільові ролі"), "\nQA");
    await user.click(screen.getByRole("button", { name: "Зберегти зміни" }));
    await screen.findByText("Збережено");
    expect(within(localNav()).queryByRole("link", { name: /є незбережені зміни/ })).toBeNull();
    await goTo(user, /Огляд профілю/);
    expect(screen.queryByText(/Незбережені зміни:/)).toBeNull();
    expect((await screen.findByRole("heading", { level: 2, name: "Кар’єрна ціль" })).closest("li")?.textContent).toContain(
      "Backend Engineer · SRE · ще 1",
    );
  });

  test("Назад і Вперед у браузері зберігають чернетку", async () => {
    const { user, view } = await openTarget();
    await user.type(field("Цільові ролі"), "\nQA");
    await goTo(user, /Контакти для CV/);
    await screen.findByRole("heading", { level: 1, name: "Контакти для CV" });
    await view.router.navigate(-1);
    await screen.findByRole("heading", { level: 1, name: "Кар’єрна ціль" });
    expect(field("Цільові ролі").value).toContain("QA");
    await view.router.navigate(1);
    expect(await screen.findByRole("heading", { level: 1, name: "Контакти для CV" })).toBeDefined();
    expect(location()).toBe("/profile/contacts");
  });

  test("чернетки не потрапляють у localStorage чи sessionStorage", async () => {
    const { user } = await openTarget();
    await user.type(field("Цільові ролі"), "\nsecret-role");
    await goTo(user, /Контакти для CV/);
    await user.clear(field("Email"));
    await user.type(field("Email"), "private@example.com");
    expect(window.localStorage.length).toBe(0);
    expect(window.sessionStorage.length).toBe(0);
  });
});

describe("вихід зі сторінки з незбереженим", () => {
  test("перехід в інший розділ застосунку питає підтвердження й лишає на місці", async () => {
    const { user } = await openTarget();
    await user.type(field("Цільові ролі"), "\nQA");
    await user.click(screen.getByRole("link", { name: "Вакансії" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Є незбережені зміни" });
    expect(dialog.textContent).toContain("Кар’єрна ціль");
    expect(location()).toBe("/profile/target");
    await user.click(within(dialog).getByRole("button", { name: "Залишитись" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect(location()).toBe("/profile/target");
    expect(field("Цільові ролі").value).toContain("QA");
  });

  test("«Піти без збереження» веде далі й відкидає чернетку", async () => {
    const { user } = await openTarget();
    await user.type(field("Цільові ролі"), "\nQA");
    await user.click(screen.getByRole("link", { name: "Вакансії" }));
    await user.click(await screen.findByRole("button", { name: "Піти без збереження" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Вакансії" })).toBeDefined();
    expect(location()).toBe("/vacancies");
    await user.click(screen.getByRole("link", { name: "Профіль" }));
    await user.click(await screen.findByRole("link", { name: /Кар’єрна ціль/ }));
    expect(field("Цільові ролі").value).toBe("Backend Engineer\nSRE");
  });

  test("без незбереженого перехід нічого не питає", async () => {
    const { user } = await openTarget();
    await user.click(screen.getByRole("link", { name: "Вакансії" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Вакансії" })).toBeDefined();
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  test("після «Скасувати» або збереження питати нема чого", async () => {
    const { user } = await openTarget();
    await user.type(field("Цільові ролі"), "\nQA");
    await user.click(screen.getByRole("button", { name: "Скасувати" }));
    await user.click(screen.getByRole("link", { name: "Вакансії" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Вакансії" })).toBeDefined();
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  test("переходи між розділами профілю не блокуються", async () => {
    const { user } = await openTarget();
    await user.type(field("Цільові ролі"), "\nQA");
    await goTo(user, /Контакти для CV/);
    expect(await screen.findByRole("heading", { level: 1, name: "Контакти для CV" })).toBeDefined();
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  test("beforeunload застерігає лише поки є незбережене", async () => {
    const { user } = await openTarget();
    const clean = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(clean);
    expect(clean.defaultPrevented).toBe(false);
    await user.type(field("Цільові ролі"), "\nQA");
    const dirty = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(dirty);
    expect(dirty.defaultPrevented).toBe(true);
    await user.click(screen.getByRole("button", { name: "Скасувати" }));
    const afterCancel = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(afterCancel);
    expect(afterCancel.defaultPrevented).toBe(false);
  });

  test("beforeunload знімається, коли користувач покидає профіль", async () => {
    const { user } = await openTarget();
    await user.click(screen.getByRole("link", { name: "Вакансії" }));
    await screen.findByRole("heading", { level: 1, name: "Вакансії" });
    const event = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(false);
  });
});

describe("профіль завантажується один раз за візит", () => {
  test("перехід між розділами не повторює GET /api/profile", async () => {
    const { backend, user } = await openTarget();
    await goTo(user, /Контакти для CV/);
    await goTo(user, /Огляд профілю/);
    await screen.findByRole("heading", { level: 2, name: "Кар’єрна ціль" });
    const calls = (backend.fetchFn as unknown as { mock: { calls: [unknown, RequestInit?][] } }).mock.calls;
    const loads = calls.filter(([url, init]) => String(url) === "/api/profile" && (init?.method ?? "GET") === "GET");
    expect(loads).toHaveLength(1);
  });
});
