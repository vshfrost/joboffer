/** Спільне для тестів блоків «Підготовка» і «Пакет до інтерв'ю» в деталях вакансії: підроблений бекенд вакансій + підготовки в одному `fetch`. */
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { apiAnalysis, apiJob as apiVacancy, jobsBackend, type ApiAnalysis, type ApiJob as ApiVacancy, type JobsBackend } from "./jobsBackend";
import { connectPrompts } from "./promptsBackend";
import { prepBackend, problem, type ApiKit, type ApiTopic, type PrepBackend } from "./prepBackend";
import { renderClient } from "./testClient";
import { setViewport } from "./viewport";

export { apiAnalysis, apiVacancy };

/** Затримка відповіді: `release()` пускає її далі (стан завантаження блоку). */
export interface Hold {
  release(): void;
}

export interface JobBlocksBackend {
  fetchFn: typeof fetch;
  vacancies: JobsBackend;
  prep: PrepBackend;
  /** Скільки найближчих відповідей на `/prep` і `/interview-kit` зробити помилкою 500. */
  failures: { prep: number; kit: number };
  /** Затримує відповіді `/prep` (`kind: "prep"`) чи `/interview-kit` (`"kit"`), доки не викличуть `release()`. */
  hold(kind: "prep" | "kit"): Hold;
}

export interface JobBlocksData {
  jobs?: ApiVacancy[];
  analyses?: ApiAnalysis[];
  topics?: ApiTopic[];
  kits?: ApiKit[];
}

const BLOCK_ROUTE = /^\/api\/jobs\/\d+\/(prep|interview-kit)$/;

export function jobBlocksBackend(data: JobBlocksData = {}): JobBlocksBackend {
  const vacancies = jobsBackend(data.jobs ?? [apiVacancy(1)], data.analyses ?? [apiAnalysis(1)]);
  const prep = prepBackend({ topics: data.topics ?? [], kits: data.kits ?? [] });
  const holds: Record<"prep" | "kit", Promise<void> | null> = { prep: null, kit: null };
  const backend: JobBlocksBackend = {
    fetchFn: fetch,
    vacancies,
    prep,
    failures: { prep: 0, kit: 0 },
    hold(kind) {
      let release = () => {};
      holds[kind] = new Promise<void>((resolve) => {
        release = resolve;
      });
      return { release };
    },
  };
  backend.fetchFn = async (input, init) => {
    const raw = typeof input === "string" ? input : input instanceof URL ? input.pathname : input.url;
    const { pathname } = new URL(raw, "https://app.test");
    const route = BLOCK_ROUTE.exec(pathname);
    if (route === null) {
      // Сторінка теми (/prep/{n}) — теж підготовка; решта — вакансії й сесія.
      return pathname.startsWith("/api/prep") ? prep.fetchFn(input, init) : vacancies.fetchFn(input, init);
    }
    const kind = route[1] === "prep" ? "prep" : "kit";
    await holds[kind];
    if (backend.failures[kind] > 0) {
      backend.failures[kind] -= 1;
      return problem(500, "internal_error", "Внутрішня помилка");
    }
    return prep.fetchFn(input, init);
  };
  return backend;
}

/** Відкриває деталі вакансії й чекає її заголовок (блоки вантажаться самі). */
export async function openJob(backend: JobBlocksBackend, id = 1, viewport: "desktop" | "mobile" = "desktop") {
  setViewport(viewport);
  connectPrompts(backend);
  const view = renderClient(`/vacancies/${id}`, backend.fetchFn);
  await screen.findByRole("heading", { level: 1 });
  return { view, user: userEvent.setup() };
}

/** `<summary>` блоку «Підготовка». */
export async function prepSummary(): Promise<HTMLElement> {
  const title = await screen.findByText("Підготовка", { selector: "summary strong" });
  return title.closest("summary") as HTMLElement;
}

/** `<details>` блоку «Підготовка». */
export async function prepDetails(): Promise<HTMLDetailsElement> {
  return (await prepSummary()).closest("details") as HTMLDetailsElement;
}

/** `<details>` розділу пакета за назвою («Ймовірні питання», «STAR-історії», «Питання до компанії»). */
export function kitSection(title: string): HTMLDetailsElement {
  return screen.getByText(title, { selector: "summary strong" }).closest("details") as HTMLDetailsElement;
}
