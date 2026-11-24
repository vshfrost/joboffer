/** Блок «Подача» без аналізу вакансії: згорнутий до заголовка, розгорнутий — «Спершу аналіз». */
import { act, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { apiAnalysis, apiApplication, apiJob, jobsBackend, type ApiApplication, type ApiJob } from "./jobsBackend";
import { renderClient } from "./testClient";

const JOB = apiJob(1, { title: "Senior Backend Engineer", company: "Northstar Labs", text: "Розробка API на Python." });
const NO_TEXT = apiJob(1, { title: "Senior Backend Engineer", company: "Northstar Labs", text: null });

async function open(options: { job?: ApiJob; analysed?: boolean; application?: ApiApplication; failAnalysis?: boolean } = {}) {
  const backend = jobsBackend([options.job ?? JOB], options.analysed === true ? [apiAnalysis(1)] : [], [], options.application === undefined ? [] : [options.application]);
  if (options.failAnalysis === true) {
    backend.failures.analysis = 1;
  }
  renderClient("/vacancies/1", backend.fetchFn);
  await screen.findByRole("heading", { level: 1, name: "Senior Backend Engineer" });
  if (options.analysed !== true && options.failAnalysis !== true) {
    await screen.findByText("Подача", { selector: "summary strong" });
  }
  const region = await screen.findByRole("region", { name: "Подача" });
  return { user: userEvent.setup(), region: within(region) };
}

const toggle = (region: ReturnType<typeof within>) => region.getByText("Подача", { selector: "summary strong" }).closest("summary") as HTMLElement;

describe("без аналізу й подачі", () => {
  test("блок згорнутий до заголовка: без «Я подався» і делегування", async () => {
    const { region } = await open();
    expect(toggle(region).getAttribute("aria-expanded")).toBe("false");
    expect(region.queryByRole("button", { name: "Я подався" })).toBeNull();
    expect(region.queryByText("Подачу ще не зафіксовано")).toBeNull();
    expect(region.queryByRole("button", { name: "Копіювати промпт" })).toBeNull();
  });

  test.each([
    ["клік", async (user: ReturnType<typeof userEvent.setup>) => user.click(document.activeElement as HTMLElement)],
    ["Enter", async (user: ReturnType<typeof userEvent.setup>) => user.keyboard("{Enter}")],
    ["пробіл", async (user: ReturnType<typeof userEvent.setup>) => user.keyboard(" ")],
  ])("розгортання (%s) показує «Спершу аналіз» без «Я подався»", async (_name, run) => {
    const { region, user } = await open();
    await act(async () => toggle(region).focus());
    await run(user);
    expect(toggle(region).getAttribute("aria-expanded")).toBe("true");
    expect(region.getByText("Спершу аналіз")).toBeDefined();
    expect(region.queryByRole("button", { name: "Я подався" })).toBeNull();
  });

  test("повторний клік знову згортає", async () => {
    const { region, user } = await open();
    await user.click(toggle(region));
    await user.click(toggle(region));
    expect(toggle(region).getAttribute("aria-expanded")).toBe("false");
    expect(region.queryByText("Спершу аналіз")).toBeNull();
  });
});

describe("вакансія без тексту опису", () => {
  test("так само згорнутий; розгорнутий — «Спершу аналіз»", async () => {
    const { region, user } = await open({ job: NO_TEXT });
    expect(toggle(region).getAttribute("aria-expanded")).toBe("false");
    expect(region.queryByRole("button", { name: "Я подався" })).toBeNull();
    await user.click(toggle(region));
    expect(region.getByText("Спершу аналіз")).toBeDefined();
    expect(region.queryByRole("button", { name: "Я подався" })).toBeNull();
  });
});

describe("подача є, а аналізу нема", () => {
  test("блок згорнутий, розгорнутий — повний блок подачі без «Спершу аналіз»", async () => {
    const { region, user } = await open({ application: apiApplication(1, { status: "applied", channel: "linkedin" }) });
    expect(toggle(region).getAttribute("aria-expanded")).toBe("false");
    expect(region.queryByText("LinkedIn")).toBeNull();
    await user.click(toggle(region));
    expect(region.getByText("LinkedIn")).toBeDefined();
    expect(region.getByRole("button", { name: "Є відповідь" })).toBeDefined();
    expect(region.queryByText("Спершу аналіз")).toBeNull();
  });
});

describe("аналіз є, завантажується або з помилкою", () => {
  test("аналіз є — блок як зараз, без перемикача згортання", async () => {
    const { region } = await open({ analysed: true });
    expect(region.queryByText("Подача", { selector: "summary strong" })).toBeNull();
    expect(await region.findByRole("button", { name: "Я подався" })).toBeDefined();
  });

  test("помилка аналізу — повний блок", async () => {
    const { region } = await open({ failAnalysis: true });
    expect(await region.findByRole("button", { name: "Я подався" })).toBeDefined();
    expect(region.queryByText("Спершу аналіз")).toBeNull();
  });

  test("поки аналіз вантажиться — скелетон подачі, не згорнутий блок", async () => {
    const backend = jobsBackend([JOB]);
    const hold = backend.holdAnalysis();
    const held = backend.holdApplication();
    renderClient("/vacancies/1", backend.fetchFn);
    await screen.findByRole("heading", { level: 1, name: "Senior Backend Engineer" });
    expect(screen.getByRole("status", { name: "Завантажуємо подачу" })).toBeDefined();
    held.release();
    hold.release();
  });
});
