/** Подачі у списку вакансій: таби «Подано» і «У процесі», відмови сховані з веб-списку, фільтр статусу, бейджі, «Не цікаво» для поданих. */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { apiApplication, apiJob, jobsBackend, type ApiApplication, type ApiJob } from "./jobsBackend";
import { renderClient } from "./testClient";
import { setViewport } from "./viewport";
import { applyFilters, chips, openFilters } from "./vacancyFilters";

const JOBS: ApiJob[] = [
  apiJob(1, { title: "Backend Подано", company: "Acme", created_at: "2026-10-20T10:00:00Z" }),
  apiJob(2, { title: "Backend Відповідь", company: "Beta", created_at: "2026-10-19T10:00:00Z" }),
  apiJob(3, { title: "Backend Співбесіда", company: "Cedar", created_at: "2026-10-18T10:00:00Z" }),
  apiJob(4, { title: "Backend Оффер", company: "Delta", created_at: "2026-10-17T10:00:00Z" }),
  apiJob(5, { title: "Backend Відмова", company: "Echo", created_at: "2026-10-16T10:00:00Z" }),
  apiJob(6, { title: "Backend Відкликано", company: "Foxtrot", created_at: "2026-10-15T10:00:00Z" }),
  apiJob(7, { title: "Backend Без подачі", company: "Golf", created_at: "2026-10-14T10:00:00Z" }),
];
const APPLICATIONS: ApiApplication[] = [
  apiApplication(1, { status: "applied" }),
  apiApplication(2, { status: "replied" }),
  apiApplication(3, { status: "interview" }),
  apiApplication(4, { status: "offer" }),
  apiApplication(5, { status: "rejected" }),
  apiApplication(6, { status: "withdrawn" }),
];

const location = () => screen.getByTestId("location").textContent;
const table = () => screen.getByRole("table", { name: "Вакансії" });
const titles = () => within(table()).queryAllByRole("link").map((link) => link.textContent);

async function openList(path = "/vacancies", jobs: ApiJob[] = JOBS, applications: ApiApplication[] = APPLICATIONS) {
  const backend = jobsBackend(jobs, [], [], applications);
  renderClient(path, backend.fetchFn);
  await screen.findByRole("heading", { level: 1, name: "Вакансії" });
  await screen.findByRole("status", { name: "Результат" });
  return { backend, user: userEvent.setup() };
}

describe("таб «Подано»", () => {
  test("показує рівно чотири активні статуси: подано, відповідь, співбесіда, оффер", async () => {
    const { backend } = await openList("/vacancies?tab=applied");
    await waitFor(() => expect(titles()).toEqual(["Backend Подано", "Backend Відповідь", "Backend Співбесіда", "Backend Оффер"]));
    expect(backend.requests.at(-1)).toBe("GET /api/jobs?stage=applied&limit=200");
  });

  test("таб відкривається кліком і лишає параметр у адресі", async () => {
    const { user } = await openList();
    await user.click(screen.getByRole("tab", { name: "Подано" }));
    await waitFor(() => expect(location()).toBe("/vacancies?tab=applied"));
    expect(screen.getByRole("tab", { name: "Подано" }).getAttribute("aria-selected")).toBe("true");
  });

  test("статус у рядку — текстовий бейдж", async () => {
    await openList("/vacancies?tab=applied");
    const rows = within(table()).getAllByRole("row").slice(1);
    expect(rows.map((row) => within(row).getByText(/^(Подано|Є відповідь|Співбесіда|Оффер)$/).textContent)).toEqual(["Подано", "Є відповідь", "Співбесіда", "Оффер"]);
  });

  test("порожній таб — підказка, а не порожня таблиця", async () => {
    await openList("/vacancies?tab=applied", [apiJob(1)], []);
    expect(await screen.findByText("Поданих вакансій немає")).toBeDefined();
    expect(screen.queryByRole("table")).toBeNull();
  });
});

describe("«Відкриті», «У процесі» і відмови", () => {
  test("«Відкриті» — лише вакансії без подачі, без бейджів статусу", async () => {
    await openList();
    await waitFor(() => expect(titles()).toEqual(["Backend Без подачі"]));
    const row = within(table()).getByRole("link", { name: "Backend Без подачі" }).closest("tr") as HTMLElement;
    for (const label of ["Подано", "Є відповідь", "Співбесіда", "Оффер", "Відмова", "Відкликано"]) {
      expect(within(row).queryByText(label)).toBeNull();
    }
  });

  test("відкликана подача — у «У процесі» з бейджем «Відкликано», а не в «Подано»", async () => {
    const { backend } = await openList("/vacancies?tab=in-progress");
    await waitFor(() => expect(titles()).toEqual(["Backend Відкликано"]));
    expect(backend.requests.at(-1)).toBe("GET /api/jobs?stage=in_progress&limit=200");
    expect(within(table()).getByText("Відкликано")).toBeDefined();
  });

  test("відмова не показується в жодному табі веб-списку", async () => {
    const { user } = await openList("/vacancies?tab=applied");
    for (const name of ["Відкриті вакансії", "У процесі", "Подано", "Потрібен текст", "Сховані"]) {
      await user.click(screen.getByRole("tab", { name: new RegExp(`^${name}`) }));
      await screen.findByRole("status", { name: "Результат" });
      expect(screen.queryByRole("link", { name: "Backend Відмова" })).toBeNull();
    }
  });

  test("відмова не знаходиться й пошуком", async () => {
    await openList("/vacancies?tab=applied&q=%D0%92%D1%96%D0%B4%D0%BC%D0%BE%D0%B2%D0%B0");
    expect(await screen.findByText("Нічого не знайдено")).toBeDefined();
  });

  test("відмову можна відкрити за прямим посиланням", async () => {
    const backend = jobsBackend(JOBS, [], [], APPLICATIONS);
    renderClient("/vacancies/5", backend.fetchFn);
    expect(await screen.findByRole("heading", { level: 1, name: "Backend Відмова" })).toBeDefined();
  });
});

describe("фільтр статусу", () => {
  const select = () => screen.getByRole("combobox", { name: "Статус подачі" });
  const options = () => within(select()).getAllByRole("option").map((option) => option.textContent);

  test("на «Подано» — лише активні статуси, без «Відмова» і «Відкликано»", async () => {
    const { user } = await openList("/vacancies?tab=applied");
    await openFilters(user);
    expect(options()).toEqual(["Усі статуси", "Подано", "Є відповідь", "Співбесіда", "Оффер"]);
  });

  test("вибраний статус фільтрує список, живе в адресі й показаний чипом", async () => {
    const { user, backend } = await openList("/vacancies?tab=applied");
    await applyFilters(user, { "Статус подачі": "interview" });
    await waitFor(() => expect(location()).toBe("/vacancies?tab=applied&status=interview"));
    await waitFor(() => expect(titles()).toEqual(["Backend Співбесіда"]));
    expect(backend.requests.at(-1)).toContain("status=interview");
    expect(chips()).toEqual(["Статус подачі: Співбесіда"]);
  });

  test("невідомий і закритий статуси в адресі ігноруються", async () => {
    await openList("/vacancies?tab=applied&status=hired");
    expect(titles()).toHaveLength(4);
    expect(chips()).toEqual([]);
  });

  test("«Скинути» в панелі прибирає статус, лишаючи таб", async () => {
    const { user } = await openList("/vacancies?tab=applied&status=offer");
    await waitFor(() => expect(titles()).toEqual(["Backend Оффер"]));
    const panel = await openFilters(user);
    await user.click(within(panel).getByRole("button", { name: "Скинути" }));
    await waitFor(() => expect(location()).toBe("/vacancies?tab=applied"));
    await waitFor(() => expect(titles()).toHaveLength(4));
  });
});

describe("повернення з деталей", () => {
  test("пошук і статус зберігаються в адресі та після повернення", async () => {
    const { user } = await openList("/vacancies?tab=applied&status=interview&q=backend");
    await user.click(await screen.findByRole("link", { name: "Backend Співбесіда" }));
    await screen.findByRole("heading", { level: 1, name: "Backend Співбесіда" });
    expect(location()).toContain("/vacancies/3?tab=applied&status=interview&q=backend");
    await user.click(screen.getByRole("link", { name: "Усі вакансії" }));
    await waitFor(() => expect(location()).toBe("/vacancies?tab=applied&status=interview&q=backend"));
    expect(await screen.findByRole("link", { name: "Backend Співбесіда" })).toBeDefined();
    expect(chips()).toEqual(["Статус подачі: Співбесіда"]);
  });
});

describe("«Не цікаво» для поданих", () => {
  test("у таблиці «Подано» недоступне й пояснено", async () => {
    await openList("/vacancies?tab=applied");
    const applied = (await screen.findByRole("button", { name: "Не цікаво: Backend Подано" })) as HTMLButtonElement;
    expect(applied.disabled).toBe(true);
    const row = applied.closest("tr") as HTMLElement;
    expect(within(row).getByText("Є подача — не ховається")).toBeDefined();
  });

  test("для вакансії без подачі у «Відкритих» — активне", async () => {
    await openList();
    expect(((await screen.findByRole("button", { name: "Не цікаво: Backend Без подачі" })) as HTMLButtonElement).disabled).toBe(false);
  });

  test("відкликана подача теж не ховається", async () => {
    await openList("/vacancies?tab=in-progress");
    expect(((await screen.findByRole("button", { name: "Не цікаво: Backend Відкликано" })) as HTMLButtonElement).disabled).toBe(true);
  });

  test("на вузькому екрані картка має той самий бейдж і ту саму заборону", async () => {
    setViewport("mobile");
    await openList("/vacancies?tab=applied");
    const card = (await screen.findByRole("link", { name: "Backend Співбесіда" })).closest("li") as HTMLElement;
    expect(within(card).getByText("Співбесіда")).toBeDefined();
    expect((within(card).getByRole("button", { name: "Не цікаво: Backend Співбесіда" }) as HTMLButtonElement).disabled).toBe(true);
    expect(within(card).getByText("Є подача — не ховається")).toBeDefined();
  });

  test("схована вакансія у «Сховані» не має заборони", async () => {
    await openList("/vacancies?tab=dismissed", [apiJob(9, { title: "Hidden", dismissed_at: "2026-10-20T09:00:00Z", dismiss_reason: "не цікаво" })], []);
    expect(await screen.findByRole("button", { name: "Повернути: Hidden" })).toBeDefined();
  });
});
