/** Документи в деталях вакансії: дві картки CV і Cover letter, звіт ATS, історія версій, запит для Claude (макет A). */
import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { COPIED, delegateBlocks, findDelegate, queryDelegate } from "./delegateHarness";
import { apiDocument, apiJob, apiLint, jobsBackend, type ApiDocument, type ApiJob } from "./jobsBackend";
import { connectPrompts } from "./promptsBackend";
import { renderClient } from "./testClient";

const JOB = apiJob(1, { title: "Senior Backend Engineer", company: "Northstar Labs", text: "Розробка API на Python." });
const REQUEST_CV =
  "Prepare a CV for job #1 in joboffer using prepare_cv. Use the confirmed facts and the rules from the brief. Save the new version with save_cv and check the ATS report. Do not add unconfirmed claims.";
const REQUEST_CL =
  "Prepare a cover letter for job #1 in joboffer using prepare_cover_letter. Use the confirmed facts and the rules from the brief. Save the new version with save_cover_letter and check the ATS report. Do not add unconfirmed claims.";
const EMPTY_CV = "Агент підготує CV на основі аналізу вакансії та підтверджених фактів.";
const EMPTY_LETTER = "Агент підготує Cover letter на основі аналізу вакансії та підтверджених фактів.";
const NEW_VERSION = "Агент підготує нову версію за актуальним аналізом і підтвердженими фактами.";
const PAGES_ISSUE = { code: "pages", message: "3 сторінок, а можна до 2 — скороти." };

async function open(documents: ApiDocument[], job: ApiJob = JOB) {
  const backend = jobsBackend([job], [], documents);
  connectPrompts(backend);
  const view = renderClient("/vacancies/1", backend.fetchFn);
  await screen.findByRole("heading", { level: 1, name: "Senior Backend Engineer" });
  return { backend, view, user: userEvent.setup() };
}

/** Картка виду документа; чекаємо, поки документи завантажаться. */
async function card(name: "CV" | "Cover letter") {
  return within(await cardElement(name));
}

function cardElement(name: "CV" | "Cover letter") {
  return screen.findByRole("region", { name });
}

const BOTH = [
  apiDocument(5, "cl", 2, { created_at: "2026-10-22T09:44:00Z" }),
  apiDocument(4, "cv", 3),
  apiDocument(3, "cl", 1, { created_at: "2026-10-21T16:25:00Z" }),
  apiDocument(2, "cv", 2, { created_at: "2026-10-21T16:20:00Z" }),
  apiDocument(1, "cv", 1, { created_at: "2026-10-20T10:10:00Z" }),
];

afterEach(() => {
  vi.restoreAllMocks();
});

describe("фото в шапці CV", () => {
  test("остання версія CV з фото — «з фото»", async () => {
    await open([apiDocument(2, "cv", 2, { photo_id: 4 }), apiDocument(1, "cv", 1)]);

    expect((await card("CV")).getByText("з фото")).toBeDefined();
    expect((await card("CV")).queryByText("без фото")).toBeNull();
  });

  test("остання версія CV без фото — «без фото», навіть якщо попередня була з фото", async () => {
    await open([apiDocument(2, "cv", 2), apiDocument(1, "cv", 1, { photo_id: 4 })]);

    expect((await card("CV")).getByText("без фото")).toBeDefined();
    expect((await card("CV")).queryByText("з фото")).toBeNull();
  });

  test("фото, видалене після збереження, — «без фото»: PDF лишається", async () => {
    await open([apiDocument(1, "cv", 1, { photo_id: null })]);

    const cv = await card("CV");
    expect(cv.getByText("без фото")).toBeDefined();
    expect(cv.getByRole("link", { name: "CV, версія 1: відкрити PDF у новій вкладці" })).toBeDefined();
  });

  test("у картці листа позначки фото нема", async () => {
    await open(BOTH);

    const letter = await card("Cover letter");
    expect(letter.queryByText("з фото")).toBeNull();
    expect(letter.queryByText("без фото")).toBeNull();
  });
});

describe("дві картки", () => {
  test("обидва документи: остання версія кожного виду, назва файлу, дата й час за Мадридом", async () => {
    await open(BOTH);

    const cv = await card("CV");
    expect(cv.getByText("v3 · остання")).toBeDefined();
    expect(cv.getByText("Alex_Example_CV.pdf")).toBeDefined();
    expect(cv.getByText("2026-10-22, 11:40 · Мадрид")).toBeDefined();
    const letter = await card("Cover letter");
    expect(letter.getByText("v2 · остання")).toBeDefined();
    expect(letter.getByText("Alex_Example_Cover_Letter.pdf")).toBeDefined();
    expect(letter.getByText("2026-10-22, 11:44 · Мадрид")).toBeDefined();
  });

  test("картки лежать в одному блоці «Документи» поруч, CV першою", async () => {
    await open(BOTH);

    const section = await screen.findByRole("region", { name: "Документи" });
    const cards = within(section).getAllByRole("region", { name: /^(CV|Cover letter)$/ });
    expect(cards.map((item) => item.getAttribute("aria-labelledby") && item.querySelector("h3")?.textContent)).toEqual(["CV", "Cover letter"]);
    expect(cards[0]?.parentElement?.className).toContain("md:grid-cols-2");
  });

  test("метадані лише з контракту: сторінки зі звіту, фото за photo_id, без вигаданої мови", async () => {
    await open([apiDocument(1, "cv", 1, { lint: apiLint({ pages: 2 }) })]);

    const cv = await card("CV");
    expect(cv.getByText("2 стор.")).toBeDefined();
    expect(cv.getByText("без фото")).toBeDefined();
    expect(cv.queryByText(/Англійська/i)).toBeNull();
  });

  test("жодного документа: обидві картки порожні, з блоком «Делегувати агенту» замість кнопки запиту", async () => {
    await open([]);

    for (const [name, description] of [
      ["CV", EMPTY_CV],
      ["Cover letter", EMPTY_LETTER],
    ] as const) {
      const empty = await card(name);
      expect(empty.getByText(`${name} ще немає`)).toBeDefined();
      await findDelegate(description, await cardElement(name));
      expect(empty.queryByRole("button", { name: "Підготувати запит" })).toBeNull();
      expect(empty.queryByText("Підготуйте документ у Claude на основі аналізу вакансії та підтверджених фактів.")).toBeNull();
      expect(empty.queryByRole("link")).toBeNull();
    }
  });

  test("є остання версія — у картці блок про нову версію, а блоку порожнього стану нема", async () => {
    await open(BOTH);

    const cv = await cardElement("CV");
    await findDelegate(NEW_VERSION, cv);
    expect(queryDelegate(EMPTY_CV, cv)).toBeNull();
    expect(delegateBlocks(cv)).toHaveLength(1);
    expect(within(cv).queryByRole("button", { name: "Нова версія через Claude" })).toBeNull();
  });

  test("лише CV: лист порожній", async () => {
    await open([apiDocument(1, "cv", 1)]);

    expect((await card("CV")).getByText("v1 · остання")).toBeDefined();
    const letter = await card("Cover letter");
    expect(letter.getByText("Cover letter ще немає")).toBeDefined();
    expect(letter.queryByText(/остання/)).toBeNull();
  });

  test("лише лист: CV порожнє", async () => {
    await open([apiDocument(1, "cl", 1)]);

    expect((await card("Cover letter")).getByText("v1 · остання")).toBeDefined();
    expect((await card("CV")).getByText("CV ще немає")).toBeDefined();
  });

  test("«остання» — не «відправлена»: пояснення під картками", async () => {
    await open(BOTH);

    expect(await screen.findByText(/«Остання» означає найновішу збережену версію, а не позначку про відправлення\./)).toBeDefined();
    expect(screen.getByText(/Зауваження ATS не блокують відкриття PDF\./)).toBeDefined();
  });

  test("вакансія без тексту: документ не підготувати — запиту нема", async () => {
    await open([], apiJob(1, { title: "Senior Backend Engineer", text: null }));

    const cv = await card("CV");
    expect(cv.getByText("Спершу додай текст вакансії — без нього документ не підготувати.")).toBeDefined();
    expect(cv.queryByRole("button")).toBeNull();
    expect(delegateBlocks(await cardElement("CV"))).toHaveLength(0);
  });
});

describe("версії та їхня нумерація", () => {
  test("історія кожного виду окремо, незалежна нумерація", async () => {
    const { user } = await open(BOTH);

    const cv = await card("CV");
    await user.click(cv.getByText("Попередні версії · 2"));
    expect(cv.getAllByText(/^Версія \d$/).map((item) => item.textContent)).toEqual(["Версія 2", "Версія 1"]);
    const letter = await card("Cover letter");
    await user.click(letter.getByText("Попередні версії · 1"));
    expect(letter.getAllByText(/^Версія \d$/).map((item) => item.textContent)).toEqual(["Версія 1"]);
  });

  test("єдина версія — історії нема", async () => {
    await open([apiDocument(1, "cv", 1)]);

    expect((await card("CV")).queryByText(/Попередні версії/)).toBeNull();
  });

  test("історія розкривається й показує дату кожної версії", async () => {
    const { user } = await open(BOTH);
    const cv = await card("CV");

    const summary = cv.getByText("Попередні версії · 2");
    expect(summary.getAttribute("aria-expanded")).toBe("false");
    await user.click(summary);

    expect(summary.getAttribute("aria-expanded")).toBe("true");
    expect(cv.getByText("2026-10-21, 18:20")).toBeDefined();
    expect(cv.getByText("2026-10-20, 12:10")).toBeDefined();
  });
});

describe("ATS-статус і звіт", () => {
  test("без зауважень: «пройдено», звіт у disclosure", async () => {
    const { user } = await open([apiDocument(1, "cv", 1, { lint: apiLint({ issues: [], pages: 2 }) })]);
    const cv = await card("CV");

    expect(cv.getByText("✓ ATS: перевірку пройдено")).toBeDefined();
    const summary = cv.getByText("Розгорнути звіт ATS");
    expect(summary.getAttribute("aria-expanded")).toBe("false");
    await user.click(summary);

    expect(summary.getAttribute("aria-expanded")).toBe("true");
    expect(cv.getByText("Технічних зауважень немає")).toBeDefined();
    expect(cv.getByText("2 стор. · Звіт збережено разом із цією версією.")).toBeDefined();
  });

  test("зауваження: кількість у статусі, тексти в розкритому звіті", async () => {
    const lint = apiLint({ issues: [PAGES_ISSUE, { code: "headings", message: "Заголовки не окремим рядком у PDF: Skills." }], pages: 3 });
    const { user } = await open([apiDocument(1, "cv", 1, { lint })]);
    const cv = await card("CV");

    expect(cv.getByText("ATS · 2 зауваження")).toBeDefined();
    await user.click(cv.getByText("Розгорнути звіт ATS"));

    expect(cv.getByText("Потребує уваги")).toBeDefined();
    expect(cv.getByText("⚠ 3 сторінок, а можна до 2 — скороти.")).toBeDefined();
    expect(cv.getByText("⚠ Заголовки не окремим рядком у PDF: Skills.")).toBeDefined();
  });

  test("ключові слова: знайдено / усього, відсоток, що є й чого нема", async () => {
    const lint = apiLint({ keywords: { covered: ["Python", "FastAPI"], missing: ["Kafka"], percent: 67 } });
    const { user } = await open([apiDocument(1, "cv", 1, { lint })]);
    const cv = await card("CV");

    expect(cv.getByText("Ключові слова: 2/3 · 67%")).toBeDefined();
    await user.click(cv.getByText("Розгорнути звіт ATS"));

    expect(cv.getByText("Є у документі")).toBeDefined();
    expect(cv.getByText("Python")).toBeDefined();
    expect(cv.getByText("FastAPI")).toBeDefined();
    expect(cv.getByText("Не знайдено")).toBeDefined();
    expect(cv.getByText("Kafka")).toBeDefined();
    expect(cv.getByText(/Покриття ключових слів не визначає статус ATS\./)).toBeDefined();
  });

  test("покриття не міняє статус: 0 % при чистому звіті — «пройдено»; 100 % із зауваженням — «зауваження»", async () => {
    await open([
      apiDocument(2, "cv", 1, { lint: apiLint({ issues: [], keywords: { covered: [], missing: ["Go"], percent: 0 } }) }),
      apiDocument(3, "cl", 1, { lint: apiLint({ issues: [PAGES_ISSUE], keywords: { covered: ["Go"], missing: [], percent: 100 } }) }),
    ]);

    const cv = await card("CV");
    expect(cv.getByText("✓ ATS: перевірку пройдено")).toBeDefined();
    expect(cv.getByText("Ключові слова: 0/1 · 0%")).toBeDefined();
    const letter = await card("Cover letter");
    expect(letter.getByText("ATS · 1 зауваження")).toBeDefined();
    expect(letter.getByText("Ключові слова: 1/1 · 100%")).toBeDefined();
  });

  test("вакансію не аналізовано: покриття не рахувалося, не «0 %»", async () => {
    const { user } = await open([apiDocument(1, "cv", 1, { lint: apiLint({ keywords: null }) })]);
    const cv = await card("CV");

    expect(cv.getByText("Покриття не рахувалося: вакансію не аналізовано")).toBeDefined();
    await user.click(cv.getByText("Розгорнути звіт ATS"));
    expect(cv.queryByText("Є у документі")).toBeNull();
    expect(cv.queryByText(/0%/)).toBeNull();
  });

  test("в аналізі нема ключових слів: без 0/0", async () => {
    await open([apiDocument(1, "cv", 1, { lint: apiLint({ keywords: { covered: [], missing: [], percent: 100 } }) })]);

    const cv = await card("CV");
    expect(cv.getByText("В аналізі нема ключових слів")).toBeDefined();
    expect(cv.queryByText(/0\/0/)).toBeNull();
  });

  test("без звіту (lint = null): «немає звіту», не «пройдено» й не нулі", async () => {
    const { user } = await open([apiDocument(1, "cv", 1, { lint: null })]);
    const cv = await card("CV");

    expect(cv.getByText("ATS: немає звіту")).toBeDefined();
    expect(cv.getByText("Покриття не перевірено")).toBeDefined();
    expect(cv.queryByText(/ATS: перевірку пройдено|ATS: пройдено/)).toBeNull();
    expect(cv.queryByText(/^\d+ стор\./)).toBeNull();
    await user.click(cv.getByText("Розгорнути звіт ATS"));
    expect(cv.getByText("Ця версія не має збереженого звіту. Це не означає, що перевірку пройдено.")).toBeDefined();
  });

  test("новіша версія з зауваженнями й старіша «пройдено»: кожна зі своїм звітом", async () => {
    const newer = apiDocument(2, "cv", 2, { lint: apiLint({ issues: [PAGES_ISSUE], pages: 3 }) });
    const older = apiDocument(1, "cv", 1, { lint: apiLint({ issues: [], pages: 2 }) });
    const { user } = await open([newer, older]);
    const cv = await card("CV");

    expect(cv.getByText("ATS · 1 зауваження")).toBeDefined();
    await user.click(cv.getByText("Попередні версії · 1"));
    const row = within(cv.getByText("Версія 1").closest("div[data-version]") as HTMLElement);
    expect(row.getByText("ATS: пройдено")).toBeDefined();
    await user.click(row.getByText("Розгорнути звіт ATS"));
    expect(row.getByText("Технічних зауважень немає")).toBeDefined();
    expect(row.queryByText(/3 сторінок/)).toBeNull();
  });

  test("історія: статус ATS кожної версії — є зауваження / пройдено / немає звіту", async () => {
    const { user } = await open([
      apiDocument(4, "cv", 4),
      apiDocument(3, "cv", 3, { lint: apiLint({ issues: [PAGES_ISSUE] }) }),
      apiDocument(2, "cv", 2, { lint: apiLint({ issues: [] }) }),
      apiDocument(1, "cv", 1, { lint: null }),
    ]);
    const cv = await card("CV");
    await user.click(cv.getByText("Попередні версії · 3"));

    expect(cv.getByText("ATS: є зауваження")).toBeDefined();
    expect(cv.getByText("ATS: пройдено")).toBeDefined();
    expect(cv.getByText("Немає звіту ATS")).toBeDefined();
  });
});

describe("відкриття PDF", () => {
  test("нативне посилання на конкретну версію: нова вкладка, без opener, та сама сесія", async () => {
    await open(BOTH);

    const cv = await card("CV");
    const link = cv.getByRole("link", { name: "CV, версія 3: відкрити PDF у новій вкладці" });
    expect(link.getAttribute("href")).toBe("/api/documents/4/pdf");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
    expect(link.textContent).toContain("Відкрити PDF");
    const letter = await card("Cover letter");
    expect(letter.getByRole("link", { name: "Cover letter, версія 2: відкрити PDF у новій вкладці" }).getAttribute("href")).toBe("/api/documents/5/pdf");
  });

  test("кожна версія в історії має своє посилання", async () => {
    const { user } = await open(BOTH);
    const cv = await card("CV");
    await user.click(cv.getByText("Попередні версії · 2"));

    for (const [version, id] of [
      [2, 2],
      [1, 1],
    ] as const) {
      const link = cv.getByRole("link", { name: `CV, версія ${version}: відкрити PDF у новій вкладці` });
      expect(link.getAttribute("href")).toBe(`/api/documents/${id}/pdf`);
      expect(link.getAttribute("target")).toBe("_blank");
      expect(link.getAttribute("rel")).toBe("noopener noreferrer");
    }
  });

  test("файл версії зник: посилання нема, чесний текст, інша версія не підставляється", async () => {
    const { user } = await open([apiDocument(2, "cv", 2, { pdf_available: false }), apiDocument(1, "cv", 1)]);
    const cv = await card("CV");

    expect(cv.getByText("Файл PDF цієї версії недоступний. Іншу версію не підставляємо.")).toBeDefined();
    expect(cv.queryByRole("link", { name: /версія 2/ })).toBeNull();
    await user.click(cv.getByText("Попередні версії · 1"));
    expect(cv.getByRole("link", { name: "CV, версія 1: відкрити PDF у новій вкладці" }).getAttribute("href")).toBe("/api/documents/1/pdf");
  });

  test("файл зник у попередній версії: лише вона без посилання", async () => {
    const { user } = await open([apiDocument(2, "cv", 2), apiDocument(1, "cv", 1, { pdf_available: false })]);
    const cv = await card("CV");
    await user.click(cv.getByText("Попередні версії · 1"));

    expect(cv.getByText("PDF недоступний")).toBeDefined();
    expect(cv.queryByRole("link", { name: /версія 1/ })).toBeNull();
    expect(cv.getByRole("link", { name: /версія 2/ })).toBeDefined();
  });
});

describe("нова версія через «Делегувати агенту»", () => {
  test("«Копіювати промпт» лише копіює запит для CV — без запитів до сервера", async () => {
    const { backend, user } = await open(BOTH);
    const writeText = vi.spyOn(navigator.clipboard, "writeText");

    const block = await findDelegate(NEW_VERSION, await cardElement("CV"));
    // Лічильник — лише коли сторінка й блок уже завантажені: стартові GET (вакансія, документи, аналіз, заявка) мають бути вже подані, інакше під навантаженням вони потраплять у «after».
    const before = backend.requests.length;
    await user.click(block.getByRole("button", { name: "Копіювати промпт" }));

    expect(writeText).toHaveBeenCalledWith(REQUEST_CV);
    expect(await block.findByText(COPIED)).toBeDefined();
    expect(backend.requests.length).toBe(before);
    expect(backend.bodies).toEqual([]);
  });

  test("запит для листа — свій", async () => {
    const { user } = await open(BOTH);
    const writeText = vi.spyOn(navigator.clipboard, "writeText");

    const block = await findDelegate(NEW_VERSION, await cardElement("Cover letter"));
    await user.click(block.getByRole("button", { name: "Копіювати промпт" }));

    expect(writeText).toHaveBeenCalledWith(REQUEST_CL);
  });

  test("порожня картка готує запит так само", async () => {
    const { user } = await open([]);
    const writeText = vi.spyOn(navigator.clipboard, "writeText");

    const block = await findDelegate(EMPTY_CV, await cardElement("CV"));
    await user.click(block.getByRole("button", { name: "Копіювати промпт" }));

    expect(writeText).toHaveBeenCalledWith(REQUEST_CV);
  });

  test("буфер недоступний: промпт розкрито для ручного копіювання", async () => {
    const { user } = await open(BOTH);
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValueOnce(new Error("denied"));

    const block = await findDelegate(NEW_VERSION, await cardElement("CV"));
    await user.click(block.getByRole("button", { name: "Копіювати промпт" }));

    expect(await block.findByText("Не вдалося скопіювати автоматично. Виділи текст промпту й скопіюй вручну.")).toBeDefined();
    expect(block.getByRole("region", { name: "Промпт" }).textContent).toContain(REQUEST_CV);
  });

  test("генерація не імітується: жодних станів «готується» чи черги", async () => {
    const { user } = await open(BOTH);

    const block = await findDelegate(NEW_VERSION, await cardElement("CV"));
    await user.click(block.getByRole("button", { name: "Копіювати промпт" }));

    expect(screen.queryByText(/Генеруємо|У черзі|Готуємо документ/)).toBeNull();
  });
});

describe("стани блоку", () => {
  test("завантаження: скелет, потім картки", async () => {
    const backend = jobsBackend([JOB], [], BOTH);
    const gate = backend.holdDocuments();
    renderClient("/vacancies/1", backend.fetchFn);
    await screen.findByRole("heading", { level: 1, name: "Senior Backend Engineer" });

    expect(await screen.findByRole("status", { name: "Завантажуємо документи" })).toBeDefined();
    gate.release();
    expect((await card("CV")).getByText("v3 · остання")).toBeDefined();
    expect(screen.queryByRole("status", { name: "Завантажуємо документи" })).toBeNull();
  });

  test("відповідь, що прийшла після закриття сторінки, ігнорується", async () => {
    const backend = jobsBackend([JOB], [], BOTH);
    const gate = backend.holdDocuments();
    const view = renderClient("/vacancies/1", backend.fetchFn);
    await screen.findByRole("status", { name: "Завантажуємо документи" });

    view.unmount();
    gate.release();
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(screen.queryByRole("region", { name: "CV" })).toBeNull();
  });

  test("збій: повідомлення й повтор, збережені версії не змінено", async () => {
    const backend = jobsBackend([JOB], [], BOTH);
    backend.documentStatuses.push(500);
    const user = userEvent.setup();
    renderClient("/vacancies/1", backend.fetchFn);

    const alert = await screen.findByText("Не вдалося завантажити документи.");
    expect(screen.getByText("Збережені версії не змінено.")).toBeDefined();
    expect(alert.closest('[role="alert"]')).not.toBeNull();
    await user.click(screen.getByRole("button", { name: "Спробувати документи ще раз" }));

    expect((await card("CV")).getByText("v3 · остання")).toBeDefined();
    expect(backend.requests.filter((line) => line.endsWith("/documents"))).toEqual(["GET /api/jobs/1/documents", "GET /api/jobs/1/documents"]);
  });

  test("збій документів не ламає решту сторінки", async () => {
    const backend = jobsBackend([JOB], [], BOTH);
    backend.documentStatuses.push(500);
    renderClient("/vacancies/1", backend.fetchFn);

    await screen.findByText("Не вдалося завантажити документи.");

    expect(screen.getByRole("heading", { level: 1, name: "Senior Backend Engineer" })).toBeDefined();
    expect(screen.getByText("Відповідність профілю")).toBeDefined();
  });

  test("401: сесія завершилась — посилання на вхід, без повтору", async () => {
    const backend = jobsBackend([JOB], [], BOTH);
    backend.documentStatuses.push(401);
    renderClient("/vacancies/1", backend.fetchFn);

    expect(await screen.findByText("Сесія завершилась. Увійди знову, щоб побачити документи.")).toBeDefined();
    expect(screen.getByRole("link", { name: "Увійти" }).getAttribute("href")).toBe("/login");
    expect(screen.queryByRole("button", { name: "Спробувати документи ще раз" })).toBeNull();
  });

  test("403: нема доступу, без повтору", async () => {
    const backend = jobsBackend([JOB], [], BOTH);
    backend.documentStatuses.push(403);
    renderClient("/vacancies/1", backend.fetchFn);

    expect(await screen.findByText("Немає доступу до документів цієї вакансії.")).toBeDefined();
    expect(screen.queryByRole("button", { name: "Спробувати документи ще раз" })).toBeNull();
  });

  test("404: вакансії нема — документи недоступні", async () => {
    const backend = jobsBackend([JOB], [], BOTH);
    backend.documentStatuses.push(404);
    renderClient("/vacancies/1", backend.fetchFn);

    expect(await screen.findByText("Документи недоступні: вакансію не знайдено.")).toBeDefined();
  });
});

describe("довгі значення й клавіатура", () => {
  test("довга назва файлу й довгі ключові слова переносяться, а не розпирають картку", async () => {
    const fileName = `${"Дуже_довге_імʼя_".repeat(12)}CV.pdf`;
    const keyword = "кубернетес-оркестрація-контейнерів-і-безперервне-розгортання-у-хмарі".repeat(2);
    const lint = apiLint({ keywords: { covered: [keyword], missing: [], percent: 100 } });
    const { user } = await open([apiDocument(1, "cv", 1, { file_name: fileName, lint })]);
    const cv = await card("CV");

    expect(cv.getByText(fileName).className).toContain("[overflow-wrap:anywhere]");
    await user.click(cv.getByText("Розгорнути звіт ATS"));
    expect(cv.getByText(keyword).className).toContain("[overflow-wrap:anywhere]");
    expect(screen.getByRole("region", { name: "CV" }).className).toContain("min-w-0");
  });

  test("Tab: посилання PDF → звіт → «Копіювати промпт» → «Переглянути промпт» → історія, у порядку читання", async () => {
    const { user } = await open(BOTH);
    const cv = await card("CV");
    await findDelegate(NEW_VERSION, await cardElement("CV"));

    cv.getByRole("link", { name: /CV, версія 3/ }).focus();
    await user.tab();
    expect(document.activeElement).toBe(cv.getAllByText("Розгорнути звіт ATS")[0]);
    await user.tab();
    expect(document.activeElement).toBe(cv.getByRole("button", { name: "Копіювати промпт" }));
    await user.tab();
    expect(document.activeElement).toBe(cv.getByRole("button", { name: "Переглянути промпт" }));
    await user.tab();
    expect(document.activeElement).toBe(cv.getByText("Попередні версії · 2"));
  });

  test("disclosure відкривається з клавіатури: Enter і пробіл", async () => {
    const { user } = await open(BOTH);
    const cv = await card("CV");
    const report = cv.getAllByText("Розгорнути звіт ATS")[0] as HTMLElement;

    report.focus();
    await user.keyboard("{Enter}");
    expect(report.getAttribute("aria-expanded")).toBe("true");
    await user.keyboard("{Enter}");
    expect(report.getAttribute("aria-expanded")).toBe("false");
    await user.keyboard(" ");
    expect(report.getAttribute("aria-expanded")).toBe("true");
  });

  test("кнопка копіювання й посилання доступні з клавіатури", async () => {
    const { user } = await open(BOTH);
    const writeText = vi.spyOn(navigator.clipboard, "writeText");

    (await findDelegate(NEW_VERSION, await cardElement("CV"))).getByRole("button", { name: "Копіювати промпт" }).focus();
    await user.keyboard("{Enter}");

    await waitFor(() => expect(writeText).toHaveBeenCalledWith(REQUEST_CV));
  });
});
