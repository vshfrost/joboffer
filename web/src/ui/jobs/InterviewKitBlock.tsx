import { useCallback, useId, type ReactNode } from "react";
import { Link } from "react-router";

import { KIT_QUESTION_LABELS, STORY_PARTS, type InterviewKit, type KitStory } from "../../domain/prep";
import { REQUESTS } from "../../domain/prompts";
import { DelegateToAgent } from "../agents/DelegateToAgent";
import { Badge } from "../components/badge";
import { Button } from "../components/button";
import { Skeleton } from "../components/skeleton";
import { cn } from "../lib/cn";
import { usePrepServices } from "../prep/PrepServices";
import { useLoaded } from "../prep/useLoaded";
import { ALERT, LINK, SUMMARY, WRAP } from "./blockStyles";

/** «Пакет до інтерв'ю» в деталях вакансії: остання версія з трьома розкривними розділами. Лише читає; пакет складає Claude. */
export function InterviewKitBlock({ jobId }: { jobId: number }) {
  const services = usePrepServices();
  const load = useCallback(async () => {
    const outcome = await services.interviewKit(jobId);
    return outcome.ok ? { ok: true as const, value: outcome.kit } : outcome;
  }, [services, jobId]);
  const { state, reload } = useLoaded(load);
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} className="min-w-0 rounded-xl border border-border bg-card p-4">
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <h2 id={headingId} className="text-section font-semibold">
          Пакет до інтерв’ю
        </h2>
        {state.status === "ready" ? (
          <>
            <Badge tone="success">{`v${state.data.version}`}</Badge>
            <span className="text-caption text-muted-foreground sm:ml-auto">{`${state.data.createdOn} · остання версія`}</span>
          </>
        ) : null}
      </div>
      {state.status === "loading" ? (
        <div role="status" aria-label="Завантажуємо пакет до інтерв’ю" aria-busy="true" className="flex flex-col gap-3">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      ) : state.status === "error" ? (
        state.problem === "not-found" ? (
          <div className="flex flex-col gap-3">
            <h3 className="font-semibold">Пакета ще немає</h3>
            <DelegateToAgent request={REQUESTS.interviewKit(jobId)} description="Агент складе питання до інтерв’ю, STAR-історії й питання до компанії." />
          </div>
        ) : (
          <div role="alert" className={ALERT}>
            <p className="text-nav font-medium">Не вдалося завантажити пакет до інтерв’ю.</p>
            <Button type="button" variant="secondary" onClick={reload}>
              Спробувати пакет ще раз
            </Button>
          </div>
        )
      ) : (
        <Kit kit={state.data} />
      )}
    </section>
  );
}

function Kit({ kit }: { kit: InterviewKit }) {
  return (
    <div className="flex flex-col">
      <KitSection title="Ймовірні питання" count={kit.questions.length} open>
        <ol className="m-0 list-none p-0">
          {kit.questions.map((question, index) => (
            <li key={index} className="flex min-w-0 flex-col items-start gap-1 border-t border-border py-3">
              <Badge>{KIT_QUESTION_LABELS[question.kind]}</Badge>
              <p className={WRAP}>
                <span className="sr-count">{`${index + 1}.`}</span> {question.question}
              </p>
              {question.topicId === null ? null : (
                <Link to={`/prep/${question.topicId}`} className={LINK}>
                  {`Тема #${question.topicId}`}
                </Link>
              )}
            </li>
          ))}
        </ol>
      </KitSection>
      <KitSection title="STAR-історії" count={kit.stories.length}>
        <ul className="m-0 flex list-none flex-col gap-3 p-0 pb-3">
          {kit.stories.map((story, index) => (
            <li key={index} className="min-w-0">
              <Story story={story} open={index === 0} />
            </li>
          ))}
        </ul>
      </KitSection>
      <KitSection title="Питання до компанії" count={kit.companyQuestions.length}>
        <ul className="m-0 list-none p-0">
          {kit.companyQuestions.map((question, index) => (
            <li key={index} className="border-t border-border py-3">
              <p className={WRAP}>
                <span className="sr-count">{`${index + 1}.`}</span> {question}
              </p>
            </li>
          ))}
        </ul>
      </KitSection>
    </div>
  );
}

function KitSection({ title, count, open = false, children }: { title: string; count: number; open?: boolean; children: ReactNode }) {
  return (
    <details open={open} className="group border-t border-border first:border-t-0">
      <summary className={SUMMARY}>
        <strong className="font-semibold">{title}</strong>
        <span className="sr-count">{count}</span>
      </summary>
      {children}
    </details>
  );
}

function Story({ story, open }: { story: KitStory; open: boolean }) {
  return (
    <details open={open} className="group rounded-lg border border-border bg-card">
      <summary className={cn(SUMMARY, "p-3.5")}>
        <strong className={cn("min-w-0 font-semibold", WRAP)}>{story.title}</strong>
      </summary>
      <div className="px-3.5 pb-4">
        {STORY_PARTS.map((part) => (
          <div key={part.letter} className="my-3 grid grid-cols-[1.5rem_minmax(0,1fr)] gap-2">
            <strong className="text-primary">{part.letter}</strong>
            <div>
              <span className="text-caption text-muted-foreground">{part.label}</span>
              <div className={WRAP}>{story[part.field]}</div>
            </div>
          </div>
        ))}
        {story.factIds.length === 0 ? null : (
          <p className="flex flex-wrap items-center gap-2 text-caption text-muted-foreground">
            Підтверджені факти
            {story.factIds.map((id) => (
              <Badge key={id}>{`#${id}`}</Badge>
            ))}
          </p>
        )}
      </div>
    </details>
  );
}
