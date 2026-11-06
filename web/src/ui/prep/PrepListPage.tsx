import { useCallback } from "react";

import { type PrepOverview, type QuizCount } from "../../domain/prep";
import { REQUESTS } from "../../domain/prompts";
import { DelegateToAgent } from "../agents/DelegateToAgent";
import { Button } from "../components/button";
import { Skeleton } from "../components/skeleton";
import { usePageTitle } from "../lib/usePageTitle";
import { PageHeading } from "../pages/PageHeading";
import { usePrepServices } from "./PrepServices";
import { problemText } from "./texts";
import { TopicRegister } from "./TopicRegister";
import { useLoaded } from "./useLoaded";

const ALERT = "flex flex-col items-start gap-3 rounded-xl border border-border bg-status-danger p-4 text-status-danger-foreground";

/** `/prep`: реєстр тем за пріоритетом, рядок квізу, порожній стан, завантаження й помилка з повтором. */
export function PrepListPage() {
  usePageTitle("Підготовка");
  const services = usePrepServices();
  const load = useCallback(async () => {
    const outcome = await services.topics();
    return outcome.ok ? { ok: true as const, value: outcome.overview } : outcome;
  }, [services]);
  const { state, reload } = useLoaded(load);
  return (
    <>
      <PageHeading title="Підготовка" subtitle="Теми закривають прогалини вакансій. Вище — потрібніші вакансіям із кращим скором." />
      <div className="flex flex-col gap-4">
        {state.status === "loading" ? (
          <div role="status" aria-label="Завантажуємо теми" className="flex flex-col gap-3">
            <Skeleton className="h-16" />
            <Skeleton className="h-16" />
            <Skeleton className="h-16" />
          </div>
        ) : state.status === "error" ? (
          <div role="alert" className={ALERT}>
            <p className="text-nav font-medium">{problemText(state.problem, "побачити теми", "Не вдалося завантажити теми")}</p>
            {state.problem === "unavailable" ? (
              <>
                <p className="text-caption">Перевір з’єднання й повтори спробу.</p>
                <Button type="button" variant="secondary" onClick={reload}>
                  Спробувати ще раз
                </Button>
              </>
            ) : null}
          </div>
        ) : (
          <Overview overview={state.data} />
        )}
      </div>
    </>
  );
}

function Overview({ overview }: { overview: PrepOverview }) {
  return (
    <>
      <QuizSummary quiz={overview.quiz} />
      {overview.topics.length === 0 ? (
        <div className="flex flex-col gap-3">
          <h2 className="text-section font-semibold">Тем ще немає</h2>
          <DelegateToAgent request={REQUESTS.topics} description="Агент запропонує теми підготовки на основі прогалин твоїх вакансій." />
        </div>
      ) : (
        <TopicRegister topics={overview.topics} />
      )}
    </>
  );
}

function QuizSummary({ quiz }: { quiz: QuizCount }) {
  return (
    <section aria-label="Квіз" className="flex flex-col gap-3">
      <p className="text-nav">
        Квіз: на повторення сьогодні <span className="sr-count">{quiz.due}</span> (усього <span className="sr-count">{quiz.total}</span>)
      </p>
      {quiz.due > 0 ? <DelegateToAgent request={REQUESTS.quiz()} description="Агент проведе квіз на сьогодні з усіх тем." /> : null}
    </section>
  );
}
