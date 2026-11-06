import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { apiJob, jobsBackend, type ApiJob } from "./jobsBackend";
import { renderClient } from "./testClient";
import { setViewport } from "./viewport";

const JOBS: ApiJob[] = [
  apiJob(1, { title: "Senior Backend Engineer", company: "Northline Pay", created_at: "2026-10-19T09:00:00Z" }),
  apiJob(2, { title: "Rust Developer", company: "Cedar Ledger", created_at: "2026-10-18T09:00:00Z" }),
  apiJob(3, { title: "Hidden Role", company: "Forma Cloud", dismissed_at: "2026-10-20T09:00:00Z", dismiss_reason: "не цікаво" }),
];

async function openList(path = "/vacancies") {
  const backend = jobsBackend(JOBS);
  renderClient(path, backend.fetchFn);
  await screen.findByRole("heading", { level: 1, name: "Вакансії" });
  await screen.findByRole("status", { name: "Результат" });
  return { backend, user: userEvent.setup() };
}

const hideButton = (title: string) => screen.getByRole("button", { name: `Не цікаво: ${title}` });
const dialog = () => screen.getByRole("alertdialog");
const reason = () => within(dialog()).getByRole("textbox", { name: "Причина" }) as HTMLInputElement;
const location = () => screen.getByTestId("location").textContent;

describe("«Не цікаво» у списку", () => {
  test("кнопка в рядку відкриває діалог із причиною за замовчуванням «не цікаво»", async () => {
    const { user } = await openList();
    await user.click(hideButton("Senior Backend Engineer"));
    expect(within(dialog()).getByText("Сховати вакансію?")).toBeDefined();
    expect(within(dialog()).getByText(/Senior Backend Engineer/)).toBeDefined();
    expect(reason().value).toBe("не цікаво");
  });

  test("«Сховати» шле номер і причину, вакансія зникає зі списку, статус оголошує про це", async () => {
    const { user, backend } = await openList();
    await user.click(hideButton("Senior Backend Engineer"));
    await user.click(within(dialog()).getByRole("button", { name: "Сховати" }));
    await waitFor(() => expect(screen.queryByRole("link", { name: "Senior Backend Engineer" })).toBeNull());
    expect(backend.bodies).toEqual([{ job_ids: [1], reason: "не цікаво" }]);
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(screen.getByRole("status", { name: "Результат" }).textContent).toContain("Вакансію «Senior Backend Engineer» сховано.");
    expect(screen.getByRole("link", { name: "Rust Developer" })).toBeDefined();
  });

  test("власна причина іде на сервер", async () => {
    const { user, backend } = await openList();
    await user.click(hideButton("Rust Developer"));
    await user.clear(reason());
    await user.type(reason(), "  далеко від дому ");
    await user.click(within(dialog()).getByRole("button", { name: "Сховати" }));
    await waitFor(() => expect(backend.bodies).toEqual([{ job_ids: [2], reason: "  далеко від дому " }]));
  });

  test("схована вакансія з'являється в табі «Сховані»", async () => {
    const { user } = await openList();
    await user.click(hideButton("Senior Backend Engineer"));
    await user.click(within(dialog()).getByRole("button", { name: "Сховати" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    await user.click(screen.getByRole("tab", { name: "Сховані" }));
    expect(await screen.findByRole("link", { name: "Senior Backend Engineer" })).toBeDefined();
    expect(screen.getByRole("link", { name: "Hidden Role" })).toBeDefined();
  });

  test("«Скасувати» нічого не шле, закриває діалог і повертає фокус на кнопку", async () => {
    const { user, backend } = await openList();
    const trigger = hideButton("Senior Backend Engineer");
    await user.click(trigger);
    await user.click(within(dialog()).getByRole("button", { name: "Скасувати" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect(backend.bodies).toEqual([]);
    expect(screen.getByRole("link", { name: "Senior Backend Engineer" })).toBeDefined();
    expect(document.activeElement).toBe(trigger);
  });

  test("помилка сервера не губить причину: діалог лишається з тим, що ввели, повтор вдається", async () => {
    const { user, backend } = await openList();
    backend.failures.dismiss = 1;
    await user.click(hideButton("Senior Backend Engineer"));
    await user.clear(reason());
    await user.type(reason(), "довга важлива причина");
    await user.click(within(dialog()).getByRole("button", { name: "Сховати" }));
    const alert = await within(dialog()).findByRole("alert");
    expect(alert.textContent).toContain("Не вдалося сховати вакансію. Причину збережено — спробуй ще раз.");
    expect(reason().value).toBe("довга важлива причина");
    // Поки діалог відкритий, сторінка під ним сховано від читачів екрана (aria-hidden).
    expect(screen.getByRole("link", { name: "Senior Backend Engineer", hidden: true })).toBeDefined();
    await user.click(within(dialog()).getByRole("button", { name: "Сховати" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect(backend.bodies.at(-1)).toEqual({ job_ids: [1], reason: "довга важлива причина" });
    expect(screen.queryByRole("link", { name: "Senior Backend Engineer" })).toBeNull();
  });

  test("порожня причина — текст сервера біля поля, діалог лишається", async () => {
    const { user } = await openList();
    await user.click(hideButton("Senior Backend Engineer"));
    await user.clear(reason());
    await user.click(within(dialog()).getByRole("button", { name: "Сховати" }));
    expect(await within(dialog()).findByText("Вкажи причину приховування.")).toBeDefined();
    expect(reason().getAttribute("aria-invalid")).toBe("true");
    expect(reason().getAttribute("aria-describedby")).not.toBeNull();
    expect(screen.getByRole("link", { name: "Senior Backend Engineer", hidden: true })).toBeDefined();
  });

  test("поки йде запит, кнопка вимкнена й подвійне натискання шле один запит", async () => {
    const { user, backend } = await openList();
    await user.click(hideButton("Senior Backend Engineer"));
    const submit = within(dialog()).getByRole("button", { name: "Сховати" });
    await user.dblClick(submit);
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull());
    expect(backend.bodies).toHaveLength(1);
  });

  test("діалог відкривається з клавіатури: Tab до кнопки, Enter", async () => {
    const { user } = await openList();
    hideButton("Senior Backend Engineer").focus();
    await user.keyboard("{Enter}");
    expect(await screen.findByRole("alertdialog")).toBeDefined();
  });

  test("на mobile кнопка в картці працює так само", async () => {
    setViewport("mobile");
    const { user, backend } = await openList();
    await user.click(hideButton("Rust Developer"));
    await user.click(within(dialog()).getByRole("button", { name: "Сховати" }));
    await waitFor(() => expect(backend.bodies).toEqual([{ job_ids: [2], reason: "не цікаво" }]));
    await waitFor(() => expect(screen.queryByRole("link", { name: "Rust Developer" })).toBeNull());
  });

  test("у табі «Сховані» замість «Не цікаво» — «Повернути»", async () => {
    await openList("/vacancies?tab=dismissed");
    expect(await screen.findByRole("button", { name: "Повернути: Hidden Role" })).toBeDefined();
    expect(screen.queryByRole("button", { name: /^Не цікаво/ })).toBeNull();
  });
});

describe("«Повернути»", () => {
  test("повертає вакансію з «Сховані» назад у «Відкриті вакансії»", async () => {
    const { user, backend } = await openList("/vacancies?tab=dismissed");
    await user.click(await screen.findByRole("button", { name: "Повернути: Hidden Role" }));
    await waitFor(() => expect(screen.queryByRole("link", { name: "Hidden Role" })).toBeNull());
    expect(backend.requests).toContain("POST /api/jobs/3/restore");
    expect(screen.getByRole("status", { name: "Результат" }).textContent).toContain("Вакансію «Hidden Role» повернуто.");
    expect(await screen.findByText("Схованих вакансій немає")).toBeDefined();
    await user.click(screen.getByRole("tab", { name: "Відкриті вакансії" }));
    expect(await screen.findByRole("link", { name: "Hidden Role" })).toBeDefined();
  });

  test("помилка сервера лишає вакансію схованою й каже про це", async () => {
    const { user, backend } = await openList("/vacancies?tab=dismissed");
    backend.failures.restore = 1;
    await user.click(await screen.findByRole("button", { name: "Повернути: Hidden Role" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Не вдалося повернути вакансію. Спробуй ще раз.");
    expect(screen.getByRole("link", { name: "Hidden Role" })).toBeDefined();
  });
});

describe("«Не цікаво» і «Повернути» у деталях", () => {
  async function openDetails(id: number, name: string) {
    const backend = jobsBackend(JOBS);
    renderClient(`/vacancies/${id}`, backend.fetchFn);
    await screen.findByRole("heading", { level: 1, name });
    return { backend, user: userEvent.setup() };
  }

  test("«Не цікаво» ховає вакансію, а деталі показують, що її сховано, з причиною", async () => {
    const { user, backend } = await openDetails(1, "Senior Backend Engineer");
    await user.click(screen.getByRole("button", { name: "Не цікаво" }));
    await user.clear(reason());
    await user.type(reason(), "не моє");
    await user.click(within(dialog()).getByRole("button", { name: "Сховати" }));
    expect(await screen.findByText("Сховано: не моє")).toBeDefined();
    expect(backend.bodies).toEqual([{ job_ids: [1], reason: "не моє" }]);
    expect(screen.getByRole("button", { name: "Повернути" })).toBeDefined();
    expect(screen.queryByRole("button", { name: "Не цікаво" })).toBeNull();
  });

  test("помилка сервера в деталях теж не губить причину", async () => {
    const { user, backend } = await openDetails(1, "Senior Backend Engineer");
    backend.failures.dismiss = 1;
    await user.click(screen.getByRole("button", { name: "Не цікаво" }));
    await user.clear(reason());
    await user.type(reason(), "моя причина");
    await user.click(within(dialog()).getByRole("button", { name: "Сховати" }));
    expect((await within(dialog()).findByRole("alert")).textContent).toContain("Не вдалося сховати вакансію.");
    expect(reason().value).toBe("моя причина");
    expect(location()).toBe("/vacancies/1");
  });

  test("«Повернути» знімає приховування в деталях", async () => {
    const { user, backend } = await openDetails(3, "Hidden Role");
    await user.click(screen.getByRole("button", { name: "Повернути" }));
    await waitFor(() => expect(screen.queryByText(/^Сховано:/)).toBeNull());
    expect(backend.requests).toContain("POST /api/jobs/3/restore");
    expect(screen.getByRole("button", { name: "Не цікаво" })).toBeDefined();
  });

  test("помилка повернення в деталях — тривога, вакансія лишається схованою", async () => {
    const { user, backend } = await openDetails(3, "Hidden Role");
    backend.failures.restore = 1;
    await user.click(screen.getByRole("button", { name: "Повернути" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Не вдалося повернути вакансію. Спробуй ще раз.");
    expect(screen.getByText("Сховано: не цікаво")).toBeDefined();
  });
});
