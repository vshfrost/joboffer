import { useCallback } from "react";
import { Link } from "react-router";

import { gapOf, progressText, readinessText, type JobPrep, type TopicRow } from "../../domain/prep";
import { REQUESTS } from "../../domain/prompts";
import { DelegateToAgent } from "../agents/DelegateToAgent";
import { Button } from "../components/button";
import { CollapsibleBlock } from "../components/CollapsibleBlock";
import { Skeleton } from "../components/skeleton";
import { cn } from "../lib/cn";
import { usePrepServices } from "../prep/PrepServices";
import { ProgressBar } from "../prep/ProgressBar";
import { TopicBadge } from "../prep/TopicBadge";
import { useLoaded } from "../prep/useLoaded";
import { ALERT, LINK, SUMMARY, WRAP } from "./blockStyles";
import type { AnalysisState } from "./useAnalysis";
import { usePrepExpanded } from "./usePrepExpanded";

interface JobPrepBlockProps {
  jobId: number;
  /** Стан аналізу вакансії: без аналізу нема прогалин, з яких Claude складе теми. */
  analysis: AnalysisState["status"];
}

/** «Підготовка» в деталях вакансії: теми вакансії зі статусом і прогресом, готовність у заголовку; згортається до заголовка. */
export function JobPrepBlock({ jobId, analysis }: JobPrepBlockProps) {
  const services = usePrepServices();
  const load = useCallback(async () => {
    const outcome = await services.jobPrep(jobId);
    return outcome.ok ? { ok: true as const, value: outcome.jobPrep } : outcome;
  }, [services, jobId]);
  const { state, reload } = useLoaded(load);
  const [expanded, toggle] = usePrepExpanded();

  return (
    <CollapsibleBlock
      title="Підготовка"
      expanded={expanded}
      onToggle={toggle}
      aside={
        state.status === "ready" ? (
          <span className="text-caption text-muted-foreground">
            Готовність <span className="sr-count">{readinessText(state.data.readiness)}</span>
          </span>
        ) : null
      }
    >
      {state.status === "loading" ? (
        <div role="status" aria-label="Завантажуємо підготовку" aria-busy="true" className="flex flex-col gap-3">
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
        </div>
      ) : state.status === "error" ? (
        <div role="alert" className={ALERT}>
          <p className="text-nav font-medium">Не вдалося завантажити підготовку.</p>
          <Button type="button" variant="secondary" onClick={reload}>
            Спробувати підготовку ще раз
          </Button>
        </div>
      ) : (
        <Topics jobId={jobId} jobPrep={state.data} analysis={analysis} />
      )}
    </CollapsibleBlock>
  );
}

function Topics({ jobId, jobPrep, analysis }: { jobId: number; jobPrep: JobPrep; analysis: AnalysisState["status"] }) {
  if (jobPrep.topics.length > 0) {
    return (
      <ul aria-label="Теми вакансії" className="m-0 list-none p-0">
        {jobPrep.topics.map((topic) => (
          <TopicItem key={topic.id} topic={topic} jobId={jobId} />
        ))}
      </ul>
    );
  }
  if (analysis === "none" || analysis === "unavailable-for-job") {
    return (
      <div className="flex flex-col items-center gap-2 px-4 py-6 text-center">
        <h3 className="font-semibold">Спершу аналіз</h3>
        <p className="text-caption text-muted-foreground">Щоб визначити прогалини й запропонувати теми, потрібен аналіз вакансії.</p>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-3 p-4">
      <h3 className="font-semibold">Тем ще немає</h3>
      <DelegateToAgent request={REQUESTS.jobPrep(jobId)} description="Агент запропонує теми підготовки на основі прогалин вакансії." />
    </div>
  );
}

function TopicItem({ topic, jobId }: { topic: TopicRow; jobId: number }) {
  return (
    <li className="flex min-w-0 flex-col gap-2 border-t border-border py-3 first:border-t-0">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <Link to={`/prep/${topic.id}`} className={cn(LINK, "self-start font-semibold")}>
            {topic.title}
          </Link>
          <div className="flex flex-wrap items-center gap-2">
            <TopicBadge status={topic.status} />
            <span className="text-caption text-muted-foreground">{`${progressText(topic)} кроків`}</span>
          </div>
        </div>
        <span className="sr-count">{`${topic.percent}%`}</span>
      </div>
      <ProgressBar percent={topic.percent} label={topic.title} />
      <details className="group">
        <summary className={cn(SUMMARY, "text-caption text-muted-foreground")}>Прогалина</summary>
        <p className={cn("pt-1 text-caption text-muted-foreground", WRAP)}>{gapOf(topic, jobId)}</p>
      </details>
    </li>
  );
}
