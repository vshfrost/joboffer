import { useEffect, useId, useRef, useState } from "react";
import { Plus } from "lucide-react";
import { Link, useLocation, useSearchParams } from "react-router";

import { filterConditions, hasActiveFilters, jobsQuery, jobTitle, TABS, TAB_LABELS, type JobFilters, type JobSummary, type JobsTab, LIST_LIMIT } from "../../domain/jobs";
import { plural } from "../../domain/profileSummary";
import { REQUESTS } from "../../domain/prompts";
import { DelegateToAgent } from "../agents/DelegateToAgent";
import { Button } from "../components/button";
import { EmptyState } from "../components/empty-state";
import { Skeleton } from "../components/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/tabs";
import { usePageTitle } from "../lib/usePageTitle";
import { useMediaQuery } from "../lib/useMediaQuery";
import { PageHeading } from "../pages/PageHeading";
import { DismissDialog, type DismissTarget } from "./DismissDialog";
import { FilterChips, FilterPanel, FiltersToggle, NO_FILTER_VALUES, SearchForm, type FilterValues } from "./FilterControls";
import { filtersFromParams, paramsFromFilters } from "./filters";
import { JobCards, JobsTable } from "./JobRows";
import { useJobsServices } from "./JobsServices";
import { useOpenedJob } from "./OpenedJob";
import { TabBadge } from "./TabBadge";
import { TriageHint } from "./TriageHint";
import { useJobList } from "./useJobList";

/** Від цієї ширини (80rem, `xl`) список — таблиця, нижче — картки: шість колонок (з тріажем і аналізом) у вужчому вікні не вміщаються. */
const DESKTOP = "(min-width: 80rem)";
const RESTORE_FAILED = "Не вдалося повернути вакансію. Спробуй ще раз.";

const EMPTY: Record<JobsTab, { title: string; hint: string }> = {
  open: { title: "Відкритих вакансій немає", hint: "Додай вакансію або передай текст опису через Claude. Вакансії, з якими ти вже працював, лежать у «У процесі»." },
  "in-progress": { title: "Вакансій у процесі немає", hint: "Сюди потрапляють вакансії з аналізом, документами чи підготовкою до співбесіди, а також відкликані подачі." },
  applied: { title: "Поданих вакансій немає", hint: "Коли позначиш вакансію поданою, вона зʼявиться тут." },
  "needs-text": { title: "Вакансій без тексту немає", hint: "Сюди потрапляють вакансії з листів-алертів, до яких ще не додано опис." },
  dismissed: { title: "Схованих вакансій немає", hint: "Вакансії, позначені «Не цікаво», зʼявляться тут, і їх можна повернути." },
};

export function JobsListPage() {
  usePageTitle("Вакансії");
  const services = useJobsServices();
  const opened = useOpenedJob();
  const { search } = useLocation();
  const [params, setParams] = useSearchParams();
  const filters = filtersFromParams(params);
  const { state, counts, reload, drop } = useJobList(jobsQuery(filters));
  const conditions = filterConditions(filters);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const panelId = useId();
  const desktop = useMediaQuery(DESKTOP, true);
  const [target, setTarget] = useState<DismissTarget | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const resultsRef = useRef<HTMLDivElement>(null);

  // Після повернення з деталей фокус — на назву вакансії, яку відкривали.
  useEffect(() => {
    if (state.status !== "ready") {
      return;
    }
    const id = opened.take();
    if (id !== null) {
      resultsRef.current?.querySelector<HTMLElement>(`[data-job-link="${id}"]`)?.focus();
    }
  }, [state.status, opened]);

  // Нове завантаження — нові повідомлення.
  useEffect(() => {
    setNotice(null);
    setFailure(null);
  }, [params]);

  function change(patch: Partial<JobFilters>) {
    setParams(paramsFromFilters({ ...filters, ...patch }));
  }

  function apply(values: FilterValues) {
    change(values);
    setFiltersOpen(false);
  }

  function removeCondition(key: FilterValues extends infer V ? keyof V : never) {
    const cleared: Partial<FilterValues> = {};
    cleared[key] = "";
    change(cleared);
  }

  async function restore(job: JobSummary) {
    setFailure(null);
    const outcome = await services.restore(job.id);
    if (outcome.ok) {
      drop(job.id);
      setNotice(`Вакансію «${jobTitle(job)}» повернуто.`);
    } else if (outcome.kind === "not-found") {
      drop(job.id);
    } else {
      setFailure(RESTORE_FAILED);
    }
  }

  function dismissed(done: DismissTarget) {
    drop(done.id);
    setNotice(`Вакансію «${done.title}» сховано.`);
    setTarget(null);
  }

  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-x-4">
        <PageHeading title="Вакансії" subtitle="Наступний крок у твоїй кар’єрі." />
        <Button asChild>
          <Link to={{ pathname: "/vacancies/new", search }}>
            <Plus aria-hidden="true" />
            Додати вакансію
          </Link>
        </Button>
      </div>
      <div className="mb-6 flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <DelegateToAgent request={REQUESTS.triage} description="Агент оцінить одну пачку нових вакансій (до 5) за тими самими правилами, що й автотріаж сервера, покаже підсумок і спитає, чи продовжувати." />
        </div>
        <TriageHint />
      </div>
      <div className="mb-4">
        <SearchForm key={filters.query} initial={filters.query} onSubmit={(query) => change({ query })} />
      </div>
      <Tabs value={filters.tab} onValueChange={(tab) => change({ tab: tab as JobsTab })}>
        <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 pt-2">
          <TabsList aria-label="Групи вакансій" className="grid w-full grid-cols-2 overflow-visible sm:inline-flex sm:w-fit">
            {TABS.map((tab) => (
              <TabsTrigger key={tab} value={tab} className="relative h-auto min-h-8 flex-1 py-1.5 text-center leading-5 whitespace-normal sm:flex-none">
                {TAB_LABELS[tab]}
                <TabBadge tab={tab} counts={counts} />
              </TabsTrigger>
            ))}
          </TabsList>
          <FiltersToggle open={filtersOpen} count={conditions.length} controls={panelId} onToggle={() => setFiltersOpen((open) => !open)} />
        </div>
        {TABS.map((tab) => (
          <TabsContent key={tab} value={tab} className="flex flex-col gap-4">
            {tab === filters.tab ? (
              <>
                {filtersOpen ? (
                  <FilterPanel
                    key={`${filters.tab}|${conditions.map((condition) => `${condition.key}=${condition.value}`).join("|")}`}
                    id={panelId}
                    filters={filters}
                    sources={state.status === "ready" ? state.list.sources : []}
                    onApply={apply}
                    onReset={() => change(NO_FILTER_VALUES)}
                  />
                ) : null}
                <FilterChips conditions={conditions} onRemove={removeCondition} />
                {failure === null ? null : (
                  <p role="alert" className="rounded-lg bg-status-danger px-3 py-2 text-caption font-medium text-status-danger-foreground">
                    {failure}
                  </p>
                )}
                <div ref={resultsRef} tabIndex={-1} className="flex min-w-0 flex-col gap-4 outline-none">
                  {state.status === "loading" ? <ListSkeleton /> : null}
                  {state.status === "error" ? (
                    <div role="alert" className="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-status-danger p-4 text-status-danger-foreground">
                      <p className="text-nav font-medium">Не вдалося завантажити вакансії.</p>
                      <Button variant="secondary" onClick={reload}>
                        Спробувати ще раз
                      </Button>
                    </div>
                  ) : null}
                  {state.status === "ready" ? (
                    <>
                      <p role="status" aria-label="Результат" className="text-caption text-muted-foreground">
                        {`Показано ${state.list.items.length} ${plural(state.list.items.length, "вакансію", "вакансії", "вакансій")}`}
                        {notice === null ? null : <span className="sr-only">{`. ${notice}`}</span>}
                      </p>
                      {notice === null ? null : (
                        <p aria-hidden="true" className="rounded-lg bg-status-success px-3 py-2 text-caption font-medium text-status-success-foreground">
                          {notice}
                        </p>
                      )}
                      {state.list.items.length === 0 ? (
                        <Empty filters={filters} onReset={() => change({ query: "", ...NO_FILTER_VALUES })} />
                      ) : desktop ? (
                        <JobsTable items={state.list.items} onHide={(job) => setTarget({ id: job.id, title: jobTitle(job) })} onRestore={(job) => void restore(job)} />
                      ) : (
                        <JobCards items={state.list.items} onHide={(job) => setTarget({ id: job.id, title: jobTitle(job) })} onRestore={(job) => void restore(job)} />
                      )}
                      {state.list.items.some((item) => item.triageVerdict === "skip") ? (
                        <p className="text-caption text-muted-foreground">«Пропустити» — рекомендація тріажу. Вакансія залишається у списку.</p>
                      ) : null}
                      {state.list.items.length >= LIST_LIMIT ? (
                        <p className="text-caption text-muted-foreground">{`Показано перші ${LIST_LIMIT} вакансій. Звузь пошук, щоб побачити решту.`}</p>
                      ) : null}
                    </>
                  ) : null}
                </div>
              </>
            ) : null}
          </TabsContent>
        ))}
      </Tabs>
      <DismissDialog
        target={target}
        onClose={() => setTarget(null)}
        onDismissed={dismissed}
        focusAfterDismiss={() => resultsRef.current?.focus()}
        onApplied={reload}
      />
    </>
  );
}

function Empty({ filters, onReset }: { filters: JobFilters; onReset(): void }) {
  if (hasActiveFilters(filters)) {
    return (
      <EmptyState
        title="Нічого не знайдено"
        hint="Жодна вакансія не підходить під пошук і фільтри. Зміни їх або скинь."
        action={
          <Button variant="secondary" onClick={onReset}>
            Скинути пошук і фільтри
          </Button>
        }
      />
    );
  }
  const empty = EMPTY[filters.tab];
  return <EmptyState title={empty.title} hint={empty.hint} />;
}

function ListSkeleton() {
  return (
    <div role="status" aria-label="Завантажуємо вакансії" aria-busy="true" className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4">
      {[0, 1, 2, 3].map((row) => (
        <div key={row} className="flex items-center gap-4">
          <Skeleton className="h-5 w-2/5" />
          <Skeleton className="h-5 w-1/4" />
          <Skeleton className="h-5 w-16" />
        </div>
      ))}
    </div>
  );
}
