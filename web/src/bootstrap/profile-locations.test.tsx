import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { FULL_PROFILE, profileBackend, validationError, type ApiProfile } from "./profileBackend";
import { json, renderClient } from "./testClient";

type User = ReturnType<typeof userEvent.setup>;

async function openLocations(profile: ApiProfile = FULL_PROFILE, overrides: Parameters<typeof profileBackend>[1] = {}) {
  const backend = profileBackend(profile, overrides);
  const view = renderClient("/profile/locations", backend.fetchFn);
  await screen.findByRole("heading", { level: 1, name: "Локації та формат" });
  return { backend, user: userEvent.setup(), view };
}

const row = (number: number) => screen.getByRole("group", { name: `Локація ${number}` });
const saveButton = () => screen.getByRole("button", { name: "Зберегти зміни" });
const addButton = () => screen.getByRole("button", { name: "Додати локацію" });
const placeOf = (number: number) => within(row(number)).getByLabelText("Місце") as HTMLInputElement;
const aliasesOf = (number: number) => within(row(number)).getByLabelText("Синоніми") as HTMLTextAreaElement;
const modeOf = (scope: HTMLElement, label: string) => within(scope).getByRole("checkbox", { name: label });
const checked = (element: HTMLElement) => element.getAttribute("aria-checked") === "true";
const globalModes = () => screen.getByRole("group", { name: "Загальні формати" });
const rowCount = () => screen.queryAllByRole("group", { name: /^Локація \d+$/ }).length;

async function addLocation(user: User, place: string, modes: string[] = ["Remote"], aliases = "") {
  await user.click(addButton());
  const number = rowCount();
  await user.type(placeOf(number), place);
  if (aliases !== "") {
    await user.type(aliasesOf(number), aliases);
  }
  for (const mode of modes) {
    await user.click(modeOf(row(number), mode));
  }
  return number;
}

describe("редактор «Локації та формат»", () => {
  test("відкривається за прямою адресою й показує збережене", async () => {
    await openLocations();
    expect(screen.getByText("Профіль / Локації та формат")).toBeDefined();
    expect(document.title).toBe("Локації та формат · Профіль · joboffer");
    expect(["Remote", "Hybrid", "Офіс"].map((label) => checked(modeOf(globalModes(), label)))).toEqual([true, true, false]);
    expect(rowCount()).toBe(2);
    expect(placeOf(1).value).toBe("Valencia");
    expect(aliasesOf(1).value).toBe("Валенсія");
    expect(["Remote", "Hybrid", "Офіс"].map((label) => checked(modeOf(row(1), label)))).toEqual([false, true, false]);
    expect(placeOf(2).value).toBe("Madrid");
    expect(["Remote", "Hybrid", "Офіс"].map((label) => checked(modeOf(row(2), label)))).toEqual([true, false, true]);
    expect(checked(screen.getByRole("checkbox", { name: "Брати вакансії з невідомим форматом, якщо локація підходить" }))).toBe(false);
    expect(checked(screen.getByRole("checkbox", { name: "Розглядаю релокейт" }))).toBe(true);
  });

  test("пояснює, як працюють формати й синоніми", async () => {
    await openLocations();
    expect(screen.getByText("Для кожної локації можна обрати свій формат роботи.")).toBeDefined();
    expect(screen.getByText("Загальні формати — окремий фільтр: вакансія з іншим форматом не проходить.")).toBeDefined();
  });

  test("порожні локації: підказка, що місце не обмежує пошук, і жодного рядка", async () => {
    const empty = structuredClone(FULL_PROFILE);
    empty.locations = { work_modes: [], locations: [], include_unknown_mode: true, relocation: false };
    await openLocations(empty);
    expect(rowCount()).toBe(0);
    expect(screen.getByText("Локацій ще нема — місце пошук не обмежує.")).toBeDefined();
    expect(addButton()).toBeDefined();
  });

  test("«Додати локацію» додає порожній рядок і переносить фокус на «Місце»", async () => {
    const { user } = await openLocations();
    await user.click(addButton());
    expect(rowCount()).toBe(3);
    expect(placeOf(3).value).toBe("");
    expect(document.activeElement).toBe(placeOf(3));
    expect(screen.getByRole("status").textContent).toBe("Є незбережені зміни");
  });

  test("«Видалити» прибирає рядок, решта зберігає порядок і значення", async () => {
    const { user } = await openLocations();
    await user.click(screen.getByRole("button", { name: "Видалити локацію 1" }));
    expect(rowCount()).toBe(1);
    expect(placeOf(1).value).toBe("Madrid");
    expect(screen.getByRole("status").textContent).toBe("Є незбережені зміни");
  });

  test("після видалення фокус іде на «Місце» наступного рядка", async () => {
    const { user } = await openLocations();
    await user.click(screen.getByRole("button", { name: "Видалити локацію 1" }));
    expect(document.activeElement).toBe(placeOf(1));
    expect(placeOf(1).value).toBe("Madrid");
  });

  test("після видалення останнього рядка фокус іде на «Місце» попереднього", async () => {
    const { user } = await openLocations();
    await user.click(screen.getByRole("button", { name: "Видалити локацію 2" }));
    expect(document.activeElement).toBe(placeOf(1));
    expect(placeOf(1).value).toBe("Valencia");
  });

  test("після видалення єдиного рядка фокус іде на «Додати локацію»", async () => {
    const single = structuredClone(FULL_PROFILE);
    single.locations.locations = [{ place: "Valencia", aliases: [], work_modes: ["remote"] }];
    const { user } = await openLocations(single);
    await user.click(screen.getByRole("button", { name: "Видалити локацію 1" }));
    expect(rowCount()).toBe(0);
    expect(document.activeElement).toBe(addButton());
  });

  test("додати й видалити, зберегти — порядок той самий після перезавантаження", async () => {
    const { backend, user, view } = await openLocations();
    await user.click(screen.getByRole("button", { name: "Видалити локацію 1" }));
    await addLocation(user, "Barcelona", ["Hybrid"], "Барселона\nBCN");
    await user.click(saveButton());
    await screen.findByText("Збережено");
    expect(backend.puts).toEqual([
      {
        section: "locations",
        body: {
          work_modes: ["remote", "hybrid"],
          locations: [
            { place: "Madrid", aliases: [], work_modes: ["remote", "onsite"] },
            { place: "Barcelona", aliases: ["Барселона", "BCN"], work_modes: ["hybrid"] },
          ],
          include_unknown_mode: false,
          relocation: true,
        },
      },
    ]);
    view.unmount();
    renderClient("/profile/locations", backend.fetchFn);
    await screen.findByRole("heading", { level: 1, name: "Локації та формат" });
    expect([placeOf(1).value, placeOf(2).value]).toEqual(["Madrid", "Barcelona"]);
    expect(aliasesOf(2).value).toBe("Барселона\nBCN");
  });

  test("загальні формати й два прапорці зберігаються разом із локаціями", async () => {
    const { backend, user } = await openLocations();
    await user.click(modeOf(globalModes(), "Офіс"));
    await user.click(screen.getByRole("checkbox", { name: "Розглядаю релокейт" }));
    await user.click(screen.getByRole("checkbox", { name: "Брати вакансії з невідомим форматом, якщо локація підходить" }));
    await user.click(saveButton());
    await screen.findByText("Збережено");
    expect(backend.puts[0]).toMatchObject({
      section: "locations",
      body: { work_modes: ["remote", "hybrid", "onsite"], include_unknown_mode: true, relocation: false },
    });
  });

  test("збереження локацій шле лише PUT /api/profile/locations; правила й ціль не змінюються", async () => {
    const { backend, user } = await openLocations();
    await addLocation(user, "Cádiz", ["Офіс"]);
    await user.click(saveButton());
    await screen.findByText("Збережено");
    expect(backend.puts.map(({ section }) => section)).toEqual(["locations"]);
    expect(backend.state.rules).toEqual(FULL_PROFILE.rules);
    expect(backend.state.target).toEqual(FULL_PROFILE.target);
  });

  test("дубль місця (інший регістр) — помилка біля рядка, введене лишається", async () => {
    const { user } = await openLocations(FULL_PROFILE, {
      "PUT /api/profile/locations": () =>
        validationError(["locations.2.place", "Місця в локаціях пошуку не мають повторюватись."]),
    });
    await addLocation(user, "VALENCIA", ["Remote"], "VLC");
    await user.click(saveButton());
    const place = placeOf(3);
    await waitFor(() => expect(place.getAttribute("aria-invalid")).toBe("true"));
    const described = (place.getAttribute("aria-describedby") ?? "").split(" ").map((id) => document.getElementById(id)?.textContent);
    expect(described).toContain("Місця в локаціях пошуку не мають повторюватись.");
    expect(within(row(3)).getByText("Місця в локаціях пошуку не мають повторюватись.")).toBeDefined();
    expect(place.value).toBe("VALENCIA");
    expect(aliasesOf(3).value).toBe("VLC");
    expect(checked(modeOf(row(3), "Remote"))).toBe(true);
    expect(placeOf(1).getAttribute("aria-invalid")).toBeNull();
    expect(document.activeElement).toBe(place);
    expect(screen.queryByText("Збережено")).toBeNull();
  });

  test("локація без формату — помилка біля рядка, введене лишається", async () => {
    const { user } = await openLocations(FULL_PROFILE, {
      "PUT /api/profile/locations": () =>
        validationError(["locations.2.work_modes", "Для місця «Cádiz» обери хоч один формат: remote, hybrid чи onsite."]),
    });
    await addLocation(user, "Cádiz", []);
    await user.click(saveButton());
    const message = "Для місця «Cádiz» обери хоч один формат: remote, hybrid чи onsite.";
    expect(await within(row(3)).findByText(message)).toBeDefined();
    const formats = within(row(3)).getByRole("group", { name: "Формати місця" });
    const described = (formats.getAttribute("aria-describedby") ?? "").split(" ").map((id) => document.getElementById(id)?.textContent);
    expect(described).toContain(message);
    expect(placeOf(3).value).toBe("Cádiz");
  });

  test("помилка рядка зникає, щойно його поле змінено", async () => {
    const { user } = await openLocations(FULL_PROFILE, {
      "PUT /api/profile/locations": () => validationError(["locations.0.place", "Місце — від 1 до 100 символів, напр. Valencia."]),
    });
    await user.type(placeOf(1), "x");
    await user.click(saveButton());
    expect(await screen.findByText("Місце — від 1 до 100 символів, напр. Valencia.")).toBeDefined();
    await user.type(placeOf(1), "y");
    expect(screen.queryByText("Місце — від 1 до 100 символів, напр. Valencia.")).toBeNull();
  });

  test("51 локація — помилка про кількість біля «Додати локацію»", async () => {
    const { user } = await openLocations(FULL_PROFILE, {
      "PUT /api/profile/locations": () => validationError(["locations", "Локацій пошуку — до 50."]),
    });
    await addLocation(user, "Cádiz");
    await user.click(saveButton());
    expect(await screen.findByText("Локацій пошуку — до 50.")).toBeDefined();
    expect(placeOf(3).value).toBe("Cádiz");
  });

  test("5xx — загальна помилка, рядки лишаються", async () => {
    const { user } = await openLocations(FULL_PROFILE, { "PUT /api/profile/locations": () => json(500, { code: "internal_error" }) });
    await addLocation(user, "Cádiz");
    await user.click(saveButton());
    expect((await screen.findByRole("alert")).textContent).toContain("Не вдалося зберегти");
    expect(rowCount()).toBe(3);
    expect(placeOf(3).value).toBe("Cádiz");
  });

  test("формат місця, якого нема в загальних, лише підказка — зберегти можна", async () => {
    const { backend, user } = await openLocations();
    expect(within(row(1)).queryByText(/не входить до загальних форматів/)).toBeNull();
    expect(within(row(2)).getByText("Формат «Офіс» не входить до загальних форматів угорі.")).toBeDefined();
    await user.type(placeOf(1), "x");
    await user.click(saveButton());
    await screen.findByText("Збережено");
    expect(backend.puts).toHaveLength(1);
  });

  test("без загальних форматів підказки нема: обмеження не діє", async () => {
    const none = structuredClone(FULL_PROFILE);
    none.locations.work_modes = [];
    await openLocations(none);
    expect(screen.queryByText(/не входить до загальних форматів/)).toBeNull();
  });

  test("«Скасувати» повертає видалені й прибирає додані рядки", async () => {
    const { user } = await openLocations();
    await user.click(screen.getByRole("button", { name: "Видалити локацію 1" }));
    await addLocation(user, "Cádiz");
    await user.click(screen.getByRole("button", { name: "Скасувати" }));
    expect(rowCount()).toBe(2);
    expect([placeOf(1).value, placeOf(2).value]).toEqual(["Valencia", "Madrid"]);
    expect(screen.getByRole("status").textContent).toBe("Немає незбережених змін");
  });

  test("чернетка локацій переживає перехід у «Правила» і назад", async () => {
    const { user } = await openLocations();
    await addLocation(user, "Cádiz");
    const nav = screen.getByRole("navigation", { name: "Розділи профілю" });
    await user.click(within(nav).getByRole("link", { name: /Правила відбору/ }));
    await screen.findByRole("heading", { level: 1, name: "Правила відбору" });
    await user.click(within(screen.getByRole("navigation", { name: "Розділи профілю" })).getByRole("link", { name: /Локації та формат/ }));
    expect(rowCount()).toBe(3);
    expect(placeOf(3).value).toBe("Cádiz");
  });

  test("огляд показує збережені локації після збереження", async () => {
    const { user } = await openLocations();
    await user.click(screen.getByRole("button", { name: "Видалити локацію 2" }));
    await user.click(saveButton());
    await screen.findByText("Збережено");
    await user.click(screen.getByRole("link", { name: /Огляд профілю/ }));
    const heading = await screen.findByRole("heading", { level: 2, name: "Локації та формат" });
    expect(heading.closest("li")?.textContent).toContain("Valencia · Hybrid");
    expect(heading.closest("li")?.textContent).not.toContain("Madrid");
  });
});

describe("формати й помилки у формі локацій", () => {
  test("формат знімається так само, як ставиться: загальний і формат місця", async () => {
    const { backend, user } = await openLocations();
    await user.click(modeOf(globalModes(), "Remote"));
    await user.click(modeOf(row(1), "Hybrid"));
    expect(checked(modeOf(globalModes(), "Remote"))).toBe(false);
    expect(checked(modeOf(row(1), "Hybrid"))).toBe(false);
    await user.click(saveButton());
    await screen.findByText("Збережено");
    expect(backend.puts[0]?.body).toMatchObject({
      work_modes: ["hybrid"],
      locations: [{ place: "Valencia", work_modes: [] }, { place: "Madrid" }],
    });
  });

  test("помилка загальних форматів — під групою «Загальні формати»", async () => {
    const { user } = await openLocations(FULL_PROFILE, {
      "PUT /api/profile/locations": () => validationError(["work_modes", "Невідомий формат роботи."]),
    });
    await user.click(modeOf(globalModes(), "Офіс"));
    await user.click(saveButton());
    expect(await within(globalModes()).findByText("Невідомий формат роботи.")).toBeDefined();
    const described = (globalModes().getAttribute("aria-describedby") ?? "").split(" ").map((id) => document.getElementById(id)?.textContent);
    expect(described).toContain("Невідомий формат роботи.");
  });

  test("кілька форматів поза загальними — підказка у множині", async () => {
    const wide = structuredClone(FULL_PROFILE);
    wide.locations.work_modes = ["remote"];
    wide.locations.locations = [{ place: "Valencia", aliases: [], work_modes: ["hybrid", "onsite"] }];
    await openLocations(wide);
    expect(within(row(1)).getByText("Формати «Hybrid», «Офіс» не входять до загальних форматів угорі.")).toBeDefined();
  });

  test("видалення рядка гасить помилки рядків, що зсунулись", async () => {
    const { user } = await openLocations(FULL_PROFILE, {
      "PUT /api/profile/locations": () => validationError(["locations.1.place", "Місця в локаціях пошуку не мають повторюватись."]),
    });
    await user.type(placeOf(2), "x");
    await user.click(saveButton());
    expect(await screen.findByText("Місця в локаціях пошуку не мають повторюватись.")).toBeDefined();
    await user.click(screen.getByRole("button", { name: "Видалити локацію 1" }));
    expect(screen.queryByText("Місця в локаціях пошуку не мають повторюватись.")).toBeNull();
  });
});

describe("клавіатура в динамічних рядках", () => {
  test("Tab у рядку йде: місце, синоніми, формати, видалити, наступний рядок", async () => {
    const { user } = await openLocations();
    placeOf(1).focus();
    const expected = [
      aliasesOf(1),
      modeOf(row(1), "Remote"),
      modeOf(row(1), "Hybrid"),
      modeOf(row(1), "Офіс"),
      screen.getByRole("button", { name: "Видалити локацію 1" }),
      placeOf(2),
    ];
    for (const element of expected) {
      await user.tab();
      expect(document.activeElement).toBe(element);
    }
  });

  test("«Додати локацію» і «Видалити» працюють з Enter і пробілом", async () => {
    const { user } = await openLocations();
    addButton().focus();
    await user.keyboard("{Enter}");
    expect(rowCount()).toBe(3);
    screen.getByRole("button", { name: "Видалити локацію 3" }).focus();
    await user.keyboard(" ");
    expect(rowCount()).toBe(2);
  });

  test("формат місця перемикається пробілом", async () => {
    const { user } = await openLocations();
    const remote = modeOf(row(1), "Remote");
    remote.focus();
    await user.keyboard(" ");
    expect(checked(remote)).toBe(true);
  });

  test("номери рядків і підписи кнопок оновлюються після видалення", async () => {
    const { user } = await openLocations();
    await user.click(screen.getByRole("button", { name: "Видалити локацію 1" }));
    expect(screen.getByRole("button", { name: "Видалити локацію 1" })).toBeDefined();
    expect(screen.queryByRole("button", { name: "Видалити локацію 2" })).toBeNull();
  });

  test("20 синонімів і довгі рядки лишаються у формі й зберігаються цілими", async () => {
    const aliases = Array.from({ length: 20 }, (_, index) => `${index}-${"a".repeat(95)}`);
    const long = structuredClone(FULL_PROFILE);
    long.locations.locations = [{ place: "P".repeat(100), aliases, work_modes: ["remote"] }];
    const { backend, user } = await openLocations(long);
    expect(aliasesOf(1).value.split("\n")).toEqual(aliases);
    await user.click(modeOf(row(1), "Hybrid"));
    await user.click(saveButton());
    await screen.findByText("Збережено");
    const body = backend.puts[0]?.body as { locations: { place: string; aliases: string[] }[] };
    expect(body.locations[0]?.place).toBe("P".repeat(100));
    expect(body.locations[0]?.aliases).toEqual(aliases);
  });
});
