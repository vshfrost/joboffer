/** Розбір відповіді: тип і вакансія, превʼю ефекту, небезпечне підтвердження відмови, помилки 422, перехід у «Розібрані». */
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { apiReply, apiUnmatched, repliesBackend, type ApiReply, type RepliesBackend, type RepliesOverrides } from "./repliesBackend";
import { json, renderClient } from "./testClient";
import { setViewport } from "./viewport";

type User = ReturnType<typeof userEvent.setup>;

async function openReply(user: User, backend: RepliesBackend, subject: string, path = "/replies", viewport: "desktop" | "mobile" = "desktop") {
  setViewport(viewport);
  renderClient(path, backend.fetchFn);
  await screen.findByRole("list", { name: "Список відповідей" });
  await user.click(screen.getByRole("button", { name: new RegExp(subject) }));
  await screen.findByRole("heading", { level: 3, name: "Підтвердити розбір" });
}

function form() {
  return within(screen.getByRole("group", { name: "Розбір відповіді" }));
}

const job = () => form().getByRole("combobox", { name: "Вакансія" }) as HTMLSelectElement;
const type = () => form().getByRole("combobox", { name: "Тип відповіді" }) as HTMLSelectElement;
const submit = () => form().getByRole("button", { name: "Підтвердити розбір" }) as HTMLButtonElement;

function selected(select: HTMLSelectElement): string {
  return select.selectedOptions[0]?.textContent ?? "";
}

function withReply(overrides: Partial<ApiReply> = {}, backendOverrides: RepliesOverrides = {}) {
  return repliesBackend([apiReply(1, { untrusted_subject: "Interview slot", ...overrides })], backendOverrides);
}

describe("форма", () => {
  test("вакансія зі списку подач і «Не про подачу»; збіг листа вибрано наперед", async () => {
    const user = userEvent.setup();
    await openReply(user, withReply(), "Interview slot");

    expect(within(job()).getAllByRole("option").map((option) => option.textContent)).toEqual([
      "Не про подачу",
      "#104 · Northstar — Senior Backend Engineer",
      "#108 · LumaPay — Senior Platform Engineer",
    ]);
    expect(selected(job())).toBe("#104 · Northstar — Senior Backend Engineer");
  });

  test("тип: усі п’ять; підказка за ключовими словами вибрана наперед і названа", async () => {
    const user = userEvent.setup();
    await openReply(user, withReply({ suggested_type: "assignment" }), "Interview slot");

    expect(within(type()).getAllByRole("option").map((option) => option.textContent)).toEqual(["Запрошення", "Тестове завдання", "Відмова", "Автопідтвердження", "Інше"]);
    expect(selected(type())).toBe("Тестове завдання");
    expect(form().getByText("Підказка за ключовими словами: Тестове завдання. Тип підтверджуєш ти.")).toBeDefined();
  });

  test("лист без збігу: вакансія «Не про подачу», превʼю не запитується", async () => {
    const user = userEvent.setup();
    const backend = repliesBackend([apiUnmatched(3, { untrusted_subject: "Cold hello" })]);
    await openReply(user, backend, "Cold hello", "/replies?queue=unmatched");

    expect(selected(job())).toBe("Не про подачу");
    expect(selected(type())).toBe("Інше");
    expect(form().getByText("Лист буде позначено розібраним без привʼязки до подачі. Статуси подач не зміняться.")).toBeDefined();
    expect(backend.previewUrls).toEqual([]);
  });

  test("збіг поза подачами власника не підставляється", async () => {
    const user = userEvent.setup();
    const stray = { job_id: 999, title: "Ghost", company: "Ghost Co", status: "applied" };
    await openReply(user, withReply({ job: stray }), "Interview slot");

    expect(selected(job())).toBe("Не про подачу");
  });

  test("форма не переноситься на іншу відповідь: чернетка скидається", async () => {
    const user = userEvent.setup();
    const backend = repliesBackend([apiReply(1, { untrusted_subject: "First one" }), apiReply(2, { untrusted_subject: "Second one", suggested_type: "rejection" })]);
    await openReply(user, backend, "First one");
    await user.selectOptions(type(), "assignment");
    expect(selected(type())).toBe("Тестове завдання");

    await user.click(screen.getByRole("button", { name: /Second one/ }));

    await screen.findByRole("heading", { level: 2, name: "Second one" });
    expect(selected(type())).toBe("Відмова");
  });
});

describe("превʼю ефекту", () => {
  test("із вибраною вакансією запитується /preview, ефект — зміна статусу", async () => {
    const user = userEvent.setup();
    const backend = withReply();
    await openReply(user, backend, "Interview slot");

    expect(await form().findByText("Статус подачі: Подано → Співбесіда.")).toBeDefined();
    expect(backend.previewUrls).toEqual(["/api/replies/1/preview?type=invitation&job_id=104"]);
  });

  test("зміна типу оновлює превʼю; тип без руху статусу — «не зміниться»", async () => {
    const user = userEvent.setup();
    const backend = withReply();
    await openReply(user, backend, "Interview slot");
    await form().findByText("Статус подачі: Подано → Співбесіда.");

    await user.selectOptions(type(), "auto_confirmation");

    expect(await form().findByText("Статус подачі не зміниться: Подано.")).toBeDefined();
    expect(backend.previewUrls.at(-1)).toBe("/api/replies/1/preview?type=auto_confirmation&job_id=104");
  });

  test("зміна вакансії оновлює превʼю; «Не про подачу» повертає текст без вакансії й не робить запиту", async () => {
    const user = userEvent.setup();
    const backend = withReply();
    await openReply(user, backend, "Interview slot");
    await form().findByText("Статус подачі: Подано → Співбесіда.");

    await user.selectOptions(job(), "108");
    expect(await form().findByText("Статус подачі: Є відповідь → Співбесіда.")).toBeDefined();
    expect(backend.previewUrls.at(-1)).toBe("/api/replies/1/preview?type=invitation&job_id=108");

    const requests = backend.previewUrls.length;
    await user.selectOptions(job(), "");
    expect(await form().findByText("Лист буде позначено розібраним без привʼязки до подачі. Статуси подач не зміняться.")).toBeDefined();
    expect(backend.previewUrls).toHaveLength(requests);
  });

  test("поки ефект рахується — «Рахуємо ефект…» і кнопка заблокована", async () => {
    const user = userEvent.setup();
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const backend = withReply({}, { preview: () => gate.then(() => json(200, { job_id: 104, current_status: "applied", status_after: "interview", changes: true })) });
    await openReply(user, backend, "Interview slot");

    expect(form().getByText("Рахуємо ефект…")).toBeDefined();
    expect(submit().disabled).toBe(true);
    release();
    expect(await form().findByText("Статус подачі: Подано → Співбесіда.")).toBeDefined();
    expect(submit().disabled).toBe(false);
  });

  test("відповідь на застаріле превʼю не затирає актуальне", async () => {
    const user = userEvent.setup();
    let releaseFirst: () => void = () => {};
    const backend = withReply(
      {},
      {
        preview: (_id, url) =>
          url.searchParams.get("type") === "invitation"
            ? new Promise<Response>((resolve) => {
                releaseFirst = () => resolve(json(200, { job_id: 104, current_status: "applied", status_after: "interview", changes: true }));
              })
            : undefined,
      },
    );
    await openReply(user, backend, "Interview slot");

    await user.selectOptions(type(), "auto_confirmation");
    expect(await form().findByText("Статус подачі не зміниться: Подано.")).toBeDefined();
    releaseFirst();
    await new Promise((resolve) => setTimeout(resolve, 20));

    expect(form().queryByText("Статус подачі: Подано → Співбесіда.")).toBeNull();
    expect(form().getByText("Статус подачі не зміниться: Подано.")).toBeDefined();
  });

  test("збій превʼю не блокує розбір", async () => {
    const user = userEvent.setup();
    await openReply(user, withReply({}, { preview: () => json(500, {}) }), "Interview slot");

    expect(await form().findByText("Не вдалося порахувати ефект розбору.")).toBeDefined();
    expect(submit().disabled).toBe(false);
  });
});

describe("розбір", () => {
  test("«Підтвердити розбір» шле тип і вакансію; лист переходить у «Розібрані», лічильники оновлюються", async () => {
    const user = userEvent.setup();
    const backend = repliesBackend([apiReply(1, { untrusted_subject: "Interview slot" }), apiReply(2, { untrusted_subject: "Other one" })]);
    await openReply(user, backend, "Interview slot");
    await form().findByText("Статус подачі: Подано → Співбесіда.");
    expect(screen.getByRole("tab", { name: "До розбору · 2" })).toBeDefined();

    await user.click(submit());

    expect(backend.reviews).toEqual([{ id: 1, body: { type: "invitation", job_id: 104 } }]);
    expect(await screen.findByRole("tab", { name: "Розібрані · 1", selected: true })).toBeDefined();
    expect(screen.getByRole("tab", { name: "До розбору · 1" })).toBeDefined();
    expect(screen.getByTestId("location").textContent).toBe("/replies?queue=reviewed&open=1");
    const open = within(screen.getByRole("article", { name: "Деталі відповіді" }));
    expect(await open.findByRole("heading", { level: 3, name: "Розібрано" })).toBeDefined();
    expect(open.getByTestId("review-type").textContent).toBe("Запрошення");
    expect(open.queryByRole("combobox")).toBeNull();
    await waitFor(() => {
      const [row] = within(screen.getByRole("list", { name: "Список відповідей" })).getAllByRole("listitem");
      expect(within(row as HTMLElement).getByTestId("status").textContent).toBe("Запрошення");
    });
  });

  test("інші тип і «Не про подачу» — у тілі запиту як є", async () => {
    const user = userEvent.setup();
    const backend = withReply();
    await openReply(user, backend, "Interview slot");

    await user.selectOptions(type(), "assignment");
    await user.selectOptions(job(), "");
    await user.click(submit());

    expect(backend.reviews).toEqual([{ id: 1, body: { type: "assignment", job_id: null } }]);
    expect(await screen.findByRole("tab", { name: "Розібрані · 1", selected: true })).toBeDefined();
  });

  test("поки розбір іде, кнопка заблокована, а подвійний клік дає один запит", async () => {
    const user = userEvent.setup();
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const backend = withReply({}, { review: () => gate.then(() => undefined) });
    await openReply(user, backend, "Interview slot");
    await form().findByText("Статус подачі: Подано → Співбесіда.");

    await user.dblClick(submit());

    expect(submit().disabled).toBe(true);
    expect(backend.reviews).toHaveLength(1);
    release();
    expect(await screen.findByRole("tab", { name: "Розібрані · 1", selected: true })).toBeDefined();
    expect(backend.reviews).toHaveLength(1);
  });

  test("на мобільному після розбору читалка показує розібрану відповідь", async () => {
    const user = userEvent.setup();
    const backend = withReply();
    await openReply(user, backend, "Interview slot", "/replies", "mobile");

    await user.click(submit());

    expect(await within(screen.getByRole("article", { name: "Деталі відповіді" })).findByRole("heading", { level: 3, name: "Розібрано" })).toBeDefined();
  });
});

describe("відмова", () => {
  test("відмова відкриває окреме небезпечне підтвердження з ефектом; без підтвердження запиту нема", async () => {
    const user = userEvent.setup();
    const backend = withReply();
    await openReply(user, backend, "Interview slot");
    await user.selectOptions(type(), "rejection");
    await form().findByText("Статус подачі: Подано → Відмова.");

    await user.click(submit());

    const dialog = await screen.findByRole("alertdialog", { name: "Позначити відповідь як відмову?" });
    expect(within(dialog).getByText("Статус подачі: Подано → Відмова. Розбір остаточний: змінити його потім не можна.")).toBeDefined();
    expect(backend.reviews).toEqual([]);

    await user.click(within(dialog).getByRole("button", { name: "Скасувати" }));

    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(backend.reviews).toEqual([]);
    expect(screen.getByTestId("location").textContent).toBe("/replies?open=1");
  });

  test("підтвердження відмови шле розбір і переносить лист у «Розібрані»", async () => {
    const user = userEvent.setup();
    const backend = withReply();
    await openReply(user, backend, "Interview slot");
    await user.selectOptions(type(), "rejection");
    await form().findByText("Статус подачі: Подано → Відмова.");
    await user.click(submit());

    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Так, це відмова" }));

    expect(backend.reviews).toEqual([{ id: 1, body: { type: "rejection", job_id: 104 } }]);
    expect(await screen.findByRole("tab", { name: "Розібрані · 1", selected: true })).toBeDefined();
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect((await screen.findByTestId("review-type")).textContent).toBe("Відмова");
  });

  test("інші типи розбираються без діалогу", async () => {
    const user = userEvent.setup();
    const backend = withReply();
    await openReply(user, backend, "Interview slot");

    await user.click(submit());

    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(backend.reviews).toHaveLength(1);
  });

  test("збій після підтвердження відмови показується у формі, діалог закрито", async () => {
    const user = userEvent.setup();
    const backend = withReply({}, { review: () => json(500, {}) });
    await openReply(user, backend, "Interview slot");
    await user.selectOptions(type(), "rejection");
    await user.click(submit());

    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Так, це відмова" }));

    expect(await form().findByText("Не вдалося підтвердити розбір. Спробуй ще раз.")).toBeDefined();
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });
});

describe("помилки розбору", () => {
  function invalid(...fields: { field: string; message: string }[]) {
    return json(422, { code: "invalid_value", message: "Розбір не пройшов перевірку", field_errors: fields, correlation_id: "c1" });
  }

  test("422 по типу — текст біля поля типу, лист лишається в черзі", async () => {
    const user = userEvent.setup();
    const backend = withReply({}, { review: () => invalid({ field: "type", message: "Тип — один з: invitation, assignment." }) });
    await openReply(user, backend, "Interview slot");

    await user.click(submit());

    const message = await form().findByText("Тип — один з: invitation, assignment.");
    expect(type().getAttribute("aria-invalid")).toBe("true");
    expect(type().getAttribute("aria-describedby")).toContain(message.id);
    expect(job().getAttribute("aria-invalid")).toBeNull();
    expect(screen.getByRole("tab", { name: "До розбору · 1" })).toBeDefined();
    expect(screen.getByTestId("location").textContent).toBe("/replies?open=1");
    expect(submit().disabled).toBe(false);
  });

  test("422 по вакансії — текст біля поля вакансії; зміна поля прибирає помилку", async () => {
    const user = userEvent.setup();
    const backend = withReply({}, { review: () => invalid({ field: "job_id", message: "Вакансія недоступна." }) });
    await openReply(user, backend, "Interview slot");
    await user.click(submit());

    const message = await form().findByText("Вакансія недоступна.");
    expect(job().getAttribute("aria-describedby")).toContain(message.id);

    await user.selectOptions(job(), "108");

    expect(form().queryByText("Вакансія недоступна.")).toBeNull();
    expect(job().getAttribute("aria-invalid")).toBeNull();
  });

  test("422 по невідомому полю — загальне повідомлення над кнопкою", async () => {
    const user = userEvent.setup();
    const backend = withReply({}, { review: () => invalid({ field: "request", message: "Запит не пройшов перевірку" }) });
    await openReply(user, backend, "Interview slot");

    await user.click(submit());

    expect((await form().findByRole("alert")).textContent).toBe("Запит не пройшов перевірку");
  });

  test("404 — лист чи подачу не знайдено", async () => {
    const user = userEvent.setup();
    await openReply(user, withReply({}, { review: () => json(404, { code: "not_found" }) }), "Interview slot");

    await user.click(submit());

    expect((await form().findByRole("alert")).textContent).toBe("Лист або подачу не знайдено. Онови сторінку.");
  });

  test("сесія завершилась і збій сервера — окремі повідомлення", async () => {
    const user = userEvent.setup();
    let status = 401;
    await openReply(user, withReply({}, { review: () => json(status, {}) }), "Interview slot");

    await user.click(submit());
    expect((await form().findByRole("alert")).textContent).toBe("Сесія завершилась. Увійди знову, щоб підтвердити розбір.");

    status = 500;
    await user.click(submit());
    await within(form().getByRole("alert")).findByText("Не вдалося підтвердити розбір. Спробуй ще раз.");
  });

  test("новий клік прибирає попередню помилку", async () => {
    const user = userEvent.setup();
    let fail = true;
    const backend = withReply({}, { review: () => (fail ? json(500, {}) : undefined) });
    await openReply(user, backend, "Interview slot");
    await user.click(submit());
    await form().findByRole("alert");

    fail = false;
    await user.click(submit());

    expect(await screen.findByRole("tab", { name: "Розібрані · 1", selected: true })).toBeDefined();
  });
});
