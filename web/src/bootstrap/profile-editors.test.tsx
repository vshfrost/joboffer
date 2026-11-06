import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { FULL_PROFILE, profileBackend, validationError, type ApiProfile } from "./profileBackend";
import { fakeBackend, json, MEANS_LOGGED_IN, renderClient } from "./testClient";

async function openTarget(profile: ApiProfile = FULL_PROFILE, overrides: Parameters<typeof profileBackend>[1] = {}) {
  const backend = profileBackend(profile, overrides);
  const view = renderClient("/profile/target", backend.fetchFn);
  await screen.findByRole("heading", { level: 1, name: "Кар’єрна ціль" });
  return { backend, user: userEvent.setup(), view };
}

async function openContacts(overrides: Parameters<typeof profileBackend>[1] = {}) {
  const backend = profileBackend(FULL_PROFILE, overrides);
  renderClient("/profile/contacts", backend.fetchFn);
  await screen.findByRole("heading", { level: 1, name: "Контакти для CV" });
  return { backend, user: userEvent.setup() };
}

const saveButton = () => screen.getByRole("button", { name: "Зберегти зміни" });
const cancelButton = () => screen.getByRole("button", { name: "Скасувати" });
const field = (label: string) => screen.getByLabelText(label) as HTMLInputElement | HTMLTextAreaElement;

async function replaceText(user: ReturnType<typeof userEvent.setup>, label: string, text: string) {
  const element = field(label);
  await user.clear(element);
  if (text !== "") {
    await user.type(element, text);
  }
}

describe("редактор «Кар’єрна ціль»", () => {
  test("відкривається за прямою адресою й показує збережені значення", async () => {
    await openTarget();
    expect(screen.getByText("Профіль / Кар’єрна ціль")).toBeDefined();
    expect(document.title).toBe("Кар’єрна ціль · Профіль · joboffer");
    expect(field("Цільові ролі").value).toBe("Backend Engineer\nSRE");
    expect(field("Мінімальна зарплата").value).toBe("65000");
    expect(field("Цільові галузі").value).toBe("fintech\npayments");
    const levels = Object.fromEntries(
      ["Junior", "Middle", "Senior", "Lead", "Principal"].map((name) => [
        name,
        screen.getByRole("checkbox", { name }).getAttribute("aria-checked"),
      ]),
    );
    expect(levels).toEqual({ Junior: "false", Middle: "false", Senior: "true", Lead: "true", Principal: "false" });
  });

  test("без змін «Зберегти» і «Скасувати» неактивні, статус каже, що змін нема", async () => {
    await openTarget();
    expect((saveButton() as HTMLButtonElement).disabled).toBe(true);
    expect((cancelButton() as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByRole("status").textContent).toBe("Немає незбережених змін");
  });

  test("після правки кнопки активні, статус: є незбережені зміни", async () => {
    const { user } = await openTarget();
    await user.type(field("Цільові ролі"), "\nQA");
    expect((saveButton() as HTMLButtonElement).disabled).toBe(false);
    expect((cancelButton() as HTMLButtonElement).disabled).toBe(false);
    expect(screen.getByRole("status").textContent).toBe("Є незбережені зміни");
  });

  test("збереження шле лише PUT /api/profile/target з тілом розділу", async () => {
    const { backend, user } = await openTarget();
    await replaceText(user, "Цільові ролі", "Platform Engineer\nSRE");
    await user.click(screen.getByRole("checkbox", { name: "Principal" }));
    await user.click(screen.getByRole("checkbox", { name: "Lead" }));
    await replaceText(user, "Мінімальна зарплата", "70 000");
    await user.click(saveButton());
    await screen.findByText("Збережено");
    expect(backend.puts).toEqual([
      {
        section: "target",
        body: {
          roles: ["Platform Engineer", "SRE"],
          seniority: ["senior", "principal"],
          min_salary_eur: 70000,
          target_domains: ["fintech", "payments"],
        },
      },
    ]);
  });

  test("контакти після збереження цілі не змінились", async () => {
    const { backend, user } = await openTarget();
    await user.type(field("Цільові ролі"), "\nQA");
    await user.click(saveButton());
    await screen.findByText("Збережено");
    expect(backend.state.contacts).toEqual(FULL_PROFILE.contacts);
    await user.click(within(screen.getByRole("navigation", { name: "Розділи профілю" })).getByRole("link", { name: /Контакти для CV/ }));
    expect(field("Email").value).toBe("user@example.com");
    expect(field("Ім’я латиницею").value).toBe("Test User");
  });

  test("успіх показується лише після відповіді сервера", async () => {
    let answer: (response: Response) => void = () => undefined;
    const reply = new Promise<Response>((resolve) => {
      answer = resolve;
    });
    const { backend, user } = await openTarget(FULL_PROFILE, { "PUT /api/profile/target": () => reply });
    await user.type(field("Цільові ролі"), "\nQA");
    await user.click(saveButton());
    expect(screen.getByRole("status").textContent).toBe("Зберігаємо…");
    expect(screen.queryByText("Збережено")).toBeNull();
    expect((saveButton() as HTMLButtonElement).disabled).toBe(true);
    await act(async () => {
      answer(json(200, { ...backend.state, target: { ...backend.state.target, roles: ["Backend Engineer", "SRE", "QA"] } }));
      await reply;
    });
    expect(await screen.findByText("Збережено")).toBeDefined();
    expect(screen.getByRole("status").textContent).toBe("Збережено");
  });

  test("після збереження сервер нормалізує значення, і форма показує його відповідь", async () => {
    const { user } = await openTarget(FULL_PROFILE, {
      "PUT /api/profile/target": () =>
        json(200, { ...FULL_PROFILE, target: { ...FULL_PROFILE.target, roles: ["SRE"] } }),
    });
    await replaceText(user, "Цільові ролі", "  sre \n SRE");
    await user.click(saveButton());
    await screen.findByText("Збережено");
    expect(field("Цільові ролі").value).toBe("SRE");
  });

  test("422 — помилка біля поля, введене лишається, успіху нема", async () => {
    const { user } = await openTarget(FULL_PROFILE, {
      "PUT /api/profile/target": () => validationError(["min_salary_eur", "Мінімальна зарплата не може бути від'ємною."]),
    });
    await replaceText(user, "Цільові ролі", "Platform Engineer");
    await replaceText(user, "Мінімальна зарплата", "5");
    await user.click(saveButton());
    const salary = await screen.findByLabelText("Мінімальна зарплата");
    expect(salary.getAttribute("aria-invalid")).toBe("true");
    const describedBy = salary.getAttribute("aria-describedby") ?? "";
    expect(describedBy.split(" ").map((id) => document.getElementById(id)?.textContent)).toContain(
      "Мінімальна зарплата не може бути від'ємною.",
    );
    expect(field("Цільові ролі").value).toBe("Platform Engineer");
    expect((salary as HTMLInputElement).value).toBe("5");
    expect(screen.queryByText("Збережено")).toBeNull();
    expect((saveButton() as HTMLButtonElement).disabled).toBe(false);
    expect(document.activeElement).toBe(salary);
  });

  test("помилка поля зникає, щойно поле змінено", async () => {
    const { user } = await openTarget(FULL_PROFILE, {
      "PUT /api/profile/target": () => validationError(["target_domains", "Цільових доменів — до 20, кожен до 100 символів."]),
    });
    await user.type(field("Цільові галузі"), "\nx");
    await user.click(saveButton());
    expect(await screen.findByText("Цільових доменів — до 20, кожен до 100 символів.")).toBeDefined();
    await user.type(field("Цільові галузі"), "y");
    expect(screen.queryByText("Цільових доменів — до 20, кожен до 100 символів.")).toBeNull();
  });

  test("422 для рівня — помилка під групою «Рівень», звʼязана через aria-describedby", async () => {
    const { user } = await openTarget(FULL_PROFILE, {
      "PUT /api/profile/target": () => validationError(["seniority", "Невідомий рівень."]),
    });
    await user.click(screen.getByRole("checkbox", { name: "Junior" }));
    await user.click(saveButton());
    expect(await screen.findByText("Невідомий рівень.")).toBeDefined();
    const group = screen.getByRole("group", { name: "Рівень" });
    const described = (group.getAttribute("aria-describedby") ?? "").split(" ").map((id) => document.getElementById(id)?.textContent);
    expect(described).toContain("Невідомий рівень.");
  });

  test.each([
    ["5xx", () => json(503, { code: "internal_error" })],
    ["мережевий збій", () => Promise.reject(new TypeError("fetch failed"))],
  ])("%s — загальна помилка, введене лишається, можна повторити", async (_name, failure) => {
    let attempts = 0;
    const { backend, user } = await openTarget(FULL_PROFILE, {
      "PUT /api/profile/target": (init) => {
        attempts += 1;
        if (attempts === 1) {
          return failure();
        }
        const body: unknown = JSON.parse(String(init?.body));
        backend.state.target = body as ApiProfile["target"];
        return json(200, backend.state);
      },
    });
    await user.type(field("Цільові ролі"), "\nQA");
    await user.click(saveButton());
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Не вдалося зберегти");
    expect(field("Цільові ролі").value).toBe("Backend Engineer\nSRE\nQA");
    expect(screen.queryByText("Збережено")).toBeNull();
    await user.click(saveButton());
    expect(await screen.findByText("Збережено")).toBeDefined();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  test("некоректна зарплата зупиняється на клієнті: помилка біля поля, запиту нема", async () => {
    const { backend, user } = await openTarget();
    await replaceText(user, "Мінімальна зарплата", "abc");
    await user.click(saveButton());
    expect(await screen.findByText("Мінімальна зарплата — ціле число в EUR, напр. 60000.")).toBeDefined();
    expect(backend.puts).toEqual([]);
    expect(field("Мінімальна зарплата").getAttribute("aria-invalid")).toBe("true");
  });

  test("«Скасувати» повертає збережені значення й гасить помилки", async () => {
    const { user } = await openTarget();
    await replaceText(user, "Цільові ролі", "Something else");
    await user.click(screen.getByRole("checkbox", { name: "Junior" }));
    await replaceText(user, "Мінімальна зарплата", "abc");
    await user.click(saveButton());
    await screen.findByText("Мінімальна зарплата — ціле число в EUR, напр. 60000.");
    await user.click(cancelButton());
    expect(field("Цільові ролі").value).toBe("Backend Engineer\nSRE");
    expect(field("Мінімальна зарплата").value).toBe("65000");
    expect(screen.getByRole("checkbox", { name: "Junior" }).getAttribute("aria-checked")).toBe("false");
    expect(screen.queryByText("Мінімальна зарплата — ціле число в EUR, напр. 60000.")).toBeNull();
    expect(screen.getByRole("status").textContent).toBe("Немає незбережених змін");
  });

  test("пусту ціль можна зберегти: роль додано, решта порожня", async () => {
    const empty = structuredClone(FULL_PROFILE);
    empty.target = { roles: [], seniority: [], min_salary_eur: null, target_domains: [] };
    const { backend, user } = await openTarget(empty);
    await user.type(field("Цільові ролі"), "QA");
    await user.click(saveButton());
    await screen.findByText("Збережено");
    expect(backend.puts[0]?.body).toEqual({ roles: ["QA"], seniority: [], min_salary_eur: null, target_domains: [] });
  });
});

describe("редактор «Контакти для CV»", () => {
  test("показує збережені значення", async () => {
    await openContacts();
    expect(field("Ім’я латиницею").value).toBe("Test User");
    expect(field("Місто").value).toBe("Valencia, Spain");
    expect(field("Email").value).toBe("user@example.com");
    expect(field("Телефон").value).toBe("+34 600 000 000");
    expect(field("LinkedIn").value).toBe("https://linkedin.com/in/user");
    expect(field("GitHub").value).toBe("https://github.com/user");
    expect(field("Дозвіл на роботу").value).toBe("Spain / EU work authorization");
  });

  test("прев’ю шапки CV оновлюється під час набору", async () => {
    const { user } = await openContacts();
    const preview = screen.getByRole("region", { name: "Попередній перегляд контактів" });
    expect(preview.textContent).toContain("Test User");
    expect(preview.textContent).toContain("Valencia, Spain · Spain / EU work authorization");
    expect(preview.textContent).toContain("user@example.com · +34 600 000 000");
    await replaceText(user, "Ім’я латиницею", "Katya Test");
    await replaceText(user, "Телефон", "");
    expect(preview.textContent).toContain("Katya Test");
    expect(preview.textContent).toContain("user@example.com");
    expect(preview.textContent).not.toContain("+34 600");
  });

  test("збереження шле лише PUT /api/profile/contacts; ціль не змінюється", async () => {
    const { backend, user } = await openContacts();
    await replaceText(user, "Місто", "Madrid, Spain");
    await user.click(saveButton());
    await screen.findByText("Збережено");
    expect(backend.puts).toEqual([
      { section: "contacts", body: { ...FULL_PROFILE.contacts, city: "Madrid, Spain" } },
    ]);
    expect(backend.state.target).toEqual(FULL_PROFILE.target);
  });

  test("422 — помилки біля Email і LinkedIn, введене лишається", async () => {
    const { user } = await openContacts({
      "PUT /api/profile/contacts": () =>
        validationError(
          ["email", "Email виглядає некоректно, напр. name@example.com."],
          ["linkedin_url", "LinkedIn — посилання з https://."],
        ),
    });
    await replaceText(user, "Email", "nope");
    await replaceText(user, "LinkedIn", "linkedin.com/in/user");
    await user.click(saveButton());
    expect(await screen.findByText("Email виглядає некоректно, напр. name@example.com.")).toBeDefined();
    expect(screen.getByText("LinkedIn — посилання з https://.")).toBeDefined();
    expect(field("Email").getAttribute("aria-invalid")).toBe("true");
    expect(field("LinkedIn").getAttribute("aria-invalid")).toBe("true");
    expect(field("Email").value).toBe("nope");
    expect(field("LinkedIn").value).toBe("linkedin.com/in/user");
    expect(document.activeElement).toBe(field("Email"));
  });

  test("5xx — загальна помилка, введене лишається", async () => {
    const { user } = await openContacts({ "PUT /api/profile/contacts": () => json(500, { code: "internal_error" }) });
    await replaceText(user, "Місто", "Madrid");
    await user.click(saveButton());
    expect((await screen.findByRole("alert")).textContent).toContain("Не вдалося зберегти");
    expect(field("Місто").value).toBe("Madrid");
  });

  test("«Скасувати» повертає збережені контакти", async () => {
    const { user } = await openContacts();
    await replaceText(user, "Email", "other@example.com");
    await user.click(cancelButton());
    expect(field("Email").value).toBe("user@example.com");
  });

  test("поле сервера, якого нема у формі, потрапляє в загальне повідомлення", async () => {
    const { user } = await openContacts({
      "PUT /api/profile/contacts": () => validationError(["unknown_field", "Щось пішло не так."]),
    });
    await replaceText(user, "Місто", "Madrid");
    await user.click(saveButton());
    expect((await screen.findByRole("alert")).textContent).toContain("Щось пішло не так.");
  });
});

describe("завантаження та помилка в редакторі", () => {
  test("пряме відкриття редактора при помилці завантаження показує повтор", async () => {
    const user = userEvent.setup();
    let attempts = 0;
    renderClient(
      "/profile/target",
      fakeBackend({
        ...MEANS_LOGGED_IN,
        "GET /api/profile": () => {
          attempts += 1;
          return attempts === 1 ? json(500, {}) : json(200, FULL_PROFILE);
        },
      }),
    );
    await user.click(await screen.findByRole("button", { name: "Спробувати ще раз" }));
    await waitFor(() => expect(field("Цільові ролі").value).toBe("Backend Engineer\nSRE"));
  });
});
