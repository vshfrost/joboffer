import { useId, type ReactNode } from "react";
import { Link } from "react-router";

import {
  GAP_STATUS_LABELS,
  NOT_STATED,
  relocationText,
  salaryText,
  SENIORITY_LABELS,
  WORK_MODE_LABELS,
  type Gap,
  type GapStatus,
  type JobAnalysis,
} from "../../domain/analysis";
import { madridDay, type Job } from "../../domain/jobs";
import { REQUESTS } from "../../domain/prompts";
import { DelegateToAgent } from "../agents/DelegateToAgent";
import { Badge } from "../components/badge";
import { Button } from "../components/button";
import { EmptyState } from "../components/empty-state";
import { Skeleton } from "../components/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/tabs";
import { MatchScore } from "./MatchScore";
import type { AnalysisState } from "./useAnalysis";

const WRAP = "[overflow-wrap:anywhere]";
export const NOT_SCORED_NOTE = "Оцінка за рубрикою 0–100. Це не ймовірність отримати оффер.";
const FACT_CAVEAT = "відсутність факту не означає відсутність навички";

interface FitProps {
  job: Job;
  state: AnalysisState;
  onRetry(): void;
}

/** Головний блок деталей: оцінка відповідності за станом аналізу, примітка, висновок, фільтри профілю, застарілість, блок «Делегувати агенту». */
export function Fit({ job, state, onRetry }: FitProps) {
  if (state.status === "loading") {
    return (
      <div role="status" aria-label="Завантажуємо аналіз" aria-busy="true" className="flex flex-col gap-3">
        <Skeleton className="h-10 w-24" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-2/3" />
      </div>
    );
  }
  if (state.status === "error") {
    return (
      <div role="alert" className="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-status-danger p-4 text-status-danger-foreground">
        <p className="text-nav font-medium">Не вдалося завантажити аналіз.</p>
        <Button variant="secondary" onClick={onRetry}>
          Спробувати ще раз
        </Button>
      </div>
    );
  }
  if (state.status === "ready") {
    return <FitReady job={job} analysis={state.analysis} />;
  }
  return (
    <div className="flex flex-col gap-4">
      <MatchScore score={null} />
      <p className="text-caption text-muted-foreground">{NOT_SCORED_NOTE}</p>
      {state.status === "unavailable-for-job" ? (
        <p className="rounded-lg bg-status-warning px-3 py-2 text-caption text-status-warning-foreground">Аналіз неможливий без тексту опису: спершу додай текст вакансії.</p>
      ) : (
        <div className="flex flex-col gap-3">
          <div>
            <p className="text-section font-semibold">Повного аналізу ще немає</p>
            <p className="mt-1 max-w-md text-caption text-muted-foreground">Тріаж допомагає з вибором. Для оцінки вимог потрібен аналіз із підтвердженими фактами.</p>
          </div>
          <DelegateToAgent request={REQUESTS.analysis(job.id)} description="Агент проаналізує вакансію за підтвердженими фактами й збереже оцінку відповідності." />
        </div>
      )}
    </div>
  );
}

function FitReady({ job, analysis }: { job: Job; analysis: JobAnalysis }) {
  return (
    <div className="flex flex-col gap-4">
      <MatchScore score={analysis.score} />
      <p className="text-caption text-muted-foreground">{NOT_SCORED_NOTE}</p>
      <p className={`text-base ${WRAP}`}>{analysis.summary}</p>
      {analysis.filtersPassed ? (
        <Badge tone="success">Проходить фільтри профілю</Badge>
      ) : (
        <div className="flex flex-col items-start gap-2">
          <Badge tone="danger">Не підходить</Badge>
          <ul aria-label="Чому не підходить" className="flex flex-col gap-1 text-sm">
            {analysis.flags.map((flag) => (
              <li key={flag} className={WRAP}>
                {flag}
              </li>
            ))}
          </ul>
        </div>
      )}
      {analysis.staleSince === null ? null : (
        <p role="status" aria-label="Аналіз застарів" className="w-fit rounded-lg bg-status-warning px-3 py-2 text-caption font-medium text-status-warning-foreground">
          {`Аналіз застарів: профіль змінено ${madridDay(analysis.staleSince)}`}
        </p>
      )}
      <p className="text-caption text-muted-foreground">{`Аналіз від ${madridDay(analysis.updatedAt)}`}</p>
      <DelegateToAgent request={REQUESTS.analysis(job.id)} description="Агент оновить аналіз вакансії за актуальним профілем і фактами." />
    </div>
  );
}

/** Вкладки блоками (макет A): огляд, вимоги, прогалини, повний текст вакансії. Усі поля реального аналізу — тут. */
export function AnalysisTabs({ job, analysis }: { job: Job; analysis: JobAnalysis }) {
  const requirements = analysis.mustHave.length + analysis.niceToHave.length;
  return (
    <Tabs defaultValue="overview" className="border-t border-border pt-8">
      <TabsList aria-label="Розділи аналізу" className="grid w-full grid-cols-2 gap-1 overflow-visible sm:inline-flex sm:w-fit">
        <Trigger value="overview">Огляд</Trigger>
        <Trigger value="requirements">{`Вимоги · ${requirements}`}</Trigger>
        <Trigger value="gaps">{`Прогалини · ${analysis.gaps.length}`}</Trigger>
        <Trigger value="description">Опис вакансії</Trigger>
      </TabsList>
      <TabsContent value="overview">
        <Overview analysis={analysis} />
      </TabsContent>
      <TabsContent value="requirements">
        <Requirements analysis={analysis} />
      </TabsContent>
      <TabsContent value="gaps">
        <Gaps job={job} analysis={analysis} />
      </TabsContent>
      <TabsContent value="description">
        <Description job={job} />
      </TabsContent>
    </Tabs>
  );
}

function Trigger({ value, children }: { value: string; children: ReactNode }) {
  return (
    <TabsTrigger value={value} className="h-auto min-h-8 flex-1 py-1.5 text-center leading-5 whitespace-normal sm:flex-none">
      {children}
    </TabsTrigger>
  );
}

function Block({ title, children }: { title: string; children: ReactNode }) {
  const id = useId();
  return (
    <section aria-labelledby={id} className="min-w-0">
      <h3 id={id} className="mb-2 text-nav font-semibold">
        {title}
      </h3>
      {children}
    </section>
  );
}

function Items({ label, items, empty }: { label: string; items: readonly string[]; empty: string }) {
  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground">{empty}</p>;
  }
  return (
    <ul aria-label={label} className="flex list-disc flex-col gap-1.5 pl-5 text-sm">
      {items.map((item, index) => (
        <li key={`${index}-${item}`} className={`min-w-0 ${WRAP}`}>
          {item}
        </li>
      ))}
    </ul>
  );
}

function Overview({ analysis }: { analysis: JobAnalysis }) {
  const conditions: [string, string][] = [
    ["Формат", analysis.workMode === null ? NOT_STATED : WORK_MODE_LABELS[analysis.workMode]],
    ["Рівень", analysis.seniority === null ? NOT_STATED : SENIORITY_LABELS[analysis.seniority]],
    ["Локація", analysis.location ?? NOT_STATED],
    ["Мови", analysis.languages.length === 0 ? NOT_STATED : analysis.languages.join(", ")],
    ["Зарплата", salaryText(analysis.salaryMinEur, analysis.salaryMaxEur)],
    ["Переїзд", relocationText(analysis.relocation)],
  ];
  return (
    <div className="mt-6 grid gap-8 md:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <Block title="Що вплинуло на оцінку">
        <Items label="Що вплинуло на оцінку" items={analysis.reasons} empty="Причин не вказано." />
      </Block>
      <div className="flex min-w-0 flex-col gap-6 rounded-xl border border-border bg-card p-4">
        <Block title="Умови вакансії">
          <ul aria-label="Умови вакансії" className="flex flex-col gap-1.5 text-sm">
            {conditions.map(([name, value]) => (
              <li key={name} className={`min-w-0 ${WRAP}`}>
                <span className="text-muted-foreground">{`${name}: `}</span>
                <span>{value}</span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-caption text-muted-foreground">Позначки фільтрів профілю — знімок на момент збереження аналізу.</p>
        </Block>
        <Block title="Ключові слова">
          {analysis.keywords.length === 0 ? (
            <p className="text-sm text-muted-foreground">Ключових слів не вказано.</p>
          ) : (
            <ul aria-label="Ключові слова" className="flex flex-wrap gap-2">
              {analysis.keywords.map((keyword) => (
                <li key={keyword} className={`min-w-0 rounded-md bg-muted px-2 py-0.5 text-caption ${WRAP}`}>
                  {keyword}
                </li>
              ))}
            </ul>
          )}
        </Block>
      </div>
    </div>
  );
}

function Requirements({ analysis }: { analysis: JobAnalysis }) {
  return (
    <div className="mt-6 flex flex-col gap-6">
      <Block title="Обов’язкові">
        <Items label="Обов’язкові вимоги" items={analysis.mustHave} empty="Обов’язкових вимог не вказано." />
      </Block>
      <Block title="Бажані">
        <Items label="Бажані вимоги" items={analysis.niceToHave} empty="Бажаних вимог не вказано." />
      </Block>
      <p className="max-w-prose text-caption text-muted-foreground">
        {`Докази з підтверджених фактів тут не показуються: аналіз не зберігає зв’язків «вимога → факт». Відсутність факту не означає відсутність навички — уточни свої факти на сторінці «Факти».`}
      </p>
    </div>
  );
}

const GAP_TONES: Record<GapStatus, "warning" | "success" | "neutral"> = { open: "warning", closed: "success", no_experience: "neutral" };

function Gaps({ job, analysis }: { job: Job; analysis: JobAnalysis }) {
  if (analysis.gaps.length === 0) {
    return (
      <EmptyState
        className="mt-6"
        title="Прогалин не зафіксовано"
        hint={`Це не гарантія: аналіз спирається лише на підтверджені факти, а ${FACT_CAVEAT}.`}
      />
    );
  }
  return (
    <div className="mt-6 grid gap-8 md:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <div className="min-w-0">
        <ul aria-label="Прогалини" className="flex flex-col gap-3">
          {analysis.gaps.map((gap) => (
            <GapItem key={gap.number} gap={gap} />
          ))}
        </ul>
      </div>
      <div className="min-w-0">
        <DelegateToAgent request={REQUESTS.gaps(job.id)} description="Агент спитає про відкриті прогалини вакансії й збереже твої відповіді." />
      </div>
    </div>
  );
}

function GapItem({ gap }: { gap: Gap }) {
  return (
    <li aria-label={gap.gap} className={`flex min-w-0 flex-col items-start gap-1 rounded-xl border border-border bg-card p-3 text-sm ${WRAP}`}>
      <span className="font-medium">{gap.gap}</span>
      {gap.question === null ? null : <span className="text-caption text-muted-foreground">{gap.question}</span>}
      <Badge tone={GAP_TONES[gap.status]}>{GAP_STATUS_LABELS[gap.status]}</Badge>
      {gap.factIds.length === 0 ? null : (
        <span className="flex flex-wrap gap-x-2 text-caption">
          Факти:
          {gap.factIds.map((id) => (
            <Link key={id} to={{ pathname: "/facts", search: `?q=${encodeURIComponent(`#${id}`)}` }} className="underline underline-offset-2">{`#${id}`}</Link>
          ))}
        </span>
      )}
    </li>
  );
}

function Description({ job }: { job: Job }) {
  return (
    <div className="mt-6">
      {job.text === null ? (
        <p className="text-sm text-muted-foreground">Опису ще нема.</p>
      ) : (
        <div className={`max-w-prose whitespace-pre-wrap ${WRAP}`}>{job.text}</div>
      )}
    </div>
  );
}
