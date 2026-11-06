import { Plus, Search } from "lucide-react";
import { useId, useState, type FormEvent, type ReactNode } from "react";
import { Link, useLocation, useSearchParams } from "react-router";

import {
  bannerTitle,
  hasSourceFilters,
  parseSourcesQuery,
  replaceSource,
  sourcesQueryParams,
  STATE_FILTER_LABELS,
  STATE_FILTERS,
  visibleSources,
  withoutSource,
  type Source,
  type SourcesOverview,
  type SourcesQuery,
  type SourcesTab,
  type StateFilter,
} from "../../domain/sources";
import { Button } from "../components/button";
import { Input } from "../components/input";
import { Select } from "../components/select";
import { Skeleton } from "../components/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/tabs";
import { usePageTitle } from "../lib/usePageTitle";
import { PageHeading } from "../pages/PageHeading";
import { RefreshBar } from "./RefreshBar";
import { RemoveDialog, type RemoveResult } from "./RemoveDialog";
import { SourceRegister } from "./SourceRegister";
import { useSourcesServices } from "./SourcesServices";
import { problemText } from "./texts";
import { useSourcesOverview } from "./useSourcesOverview";

const ALERT = "flex flex-col items-start gap-3 rounded-xl border border-border bg-status-danger p-4 text-status-danger-foreground";
const GONE = "Джерела вже немає — список оновлено.";
export function newSourceHref(tab: SourcesTab): string {
  return tab === "feeds" ? "/sources/new?tab=feeds" : "/sources/new";
}

/** `/sources`: реєстр джерел вакансій. Вкладка, пошук, стан і розгорнуте джерело живуть в адресі сторінки. */
export function SourcesListPage() {
  usePageTitle("Джерела");
  const services = useSourcesServices();
  const [params, setParams] = useSearchParams();
  const query = parseSourcesQuery(params);
  const { state, reload, refetch, patch } = useSourcesOverview();
  // Форма «Додати джерело» залишає повідомлення про успіх у стані переходу.
  const arrival = useLocation().state as { message?: string } | null;
  const [message, setMessage] = useState(arrival?.message ?? "");
  const [queued, setQueued] = useState(false);
  const [requesting, setRequesting] = useState(false);
  const [busyId, setBusyId] = useState("");
  const [removing, setRemoving] = useState<Source | null>(null);

  const go = (next: SourcesQuery) => setParams(sourcesQueryParams(next));
  const reset = () => go({ ...query, q: "", status: "" });

  async function toggle(source: Source) {
    setBusyId(source.id);
    const outcome = await services.setEnabled(source.kind, source.id, !source.enabled);
    setBusyId("");
    if (outcome.ok) {
      patch((overview) => replaceSource(overview, outcome.source));
      setMessage(`${source.name} ${outcome.source.enabled ? "увімкнено" : "вимкнено"}.`);
    } else if (outcome.kind === "not-found") {
      setMessage(GONE);
      await refetch();
    } else {
      setMessage(problemText(outcome.kind, "змінити джерело", "Не вдалося змінити джерело. Спробуй ще раз."));
    }
  }

  async function remove(source: Source): Promise<RemoveResult> {
    const outcome = await services.remove(source.kind, source.id);
    if (outcome.ok) {
      patch((overview) => withoutSource(overview, source));
      setMessage("Джерело видалено. Імпортовані вакансії залишились.");
    } else if (outcome.kind === "not-found") {
      setMessage(GONE);
      await refetch();
    } else {
      return { ok: false, message: problemText(outcome.kind, "видалити джерело", "Не вдалося видалити джерело. Спробуй ще раз.") };
    }
    setRemoving(null);
    go({ ...query, open: "" });
    return { ok: true };
  }

  async function requestRefresh() {
    setRequesting(true);
    setMessage("");
    const outcome = await services.requestRefresh();
    setRequesting(false);
    if (outcome.ok) {
      patch((overview) => ({ ...overview, refresh: outcome.refresh }));
      setQueued(true);
    } else if (outcome.kind === "limit") {
      patch((overview) => ({ ...overview, refresh: { ...overview.refresh, remaining: 0, nextAt: outcome.nextAt } }));
      setMessage(outcome.message);
    } else {
      setMessage(problemText(outcome.kind, "оновити джерела", "Не вдалося запросити оновлення. Спробуй ще раз."));
    }
  }

  const overview = state.status === "ready" ? state.overview : null;
  return (
    <>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4 [&>div]:mb-0">
        <PageHeading title="Джерела вакансій" subtitle="Компанії та стрічки, з яких joboffer знаходить вакансії." />
        <Button asChild>
          <Link to={newSourceHref(query.tab)}>
            <Plus aria-hidden="true" />
            Додати джерело
          </Link>
        </Button>
      </div>
      <div className="flex flex-col gap-4">
        {overview === null ? null : (
          <>
            <RefreshBar refresh={overview.refresh} queued={queued} requesting={requesting} onRequest={() => void requestRefresh()} />
            <FilteredBanner count={overview.filteredOutCount} />
          </>
        )}
        <Tabs value={query.tab} onValueChange={(tab) => go({ tab: tab as SourcesTab, q: "", status: query.status, open: "" })}>
          <TabsList aria-label="Види джерел" className="max-sm:w-full">
            <TabsTrigger value="companies" className="max-sm:flex-1">
              {tabLabel("Компанії", overview?.companies.length)}
            </TabsTrigger>
            <TabsTrigger value="feeds" className="max-sm:flex-1">
              {tabLabel("RSS-стрічки", overview?.feeds.length)}
            </TabsTrigger>
          </TabsList>
          <TabsContent value={query.tab} className="flex flex-col gap-4">
            <Toolbar query={query} onChange={(patchQuery) => go({ ...query, open: "", ...patchQuery })} />
            <Results
              state={state}
              query={query}
              busyId={busyId}
              onRetry={reload}
              onReset={reset}
              onOpen={(source) => go({ ...query, open: query.open === source.id ? "" : source.id })}
              onToggle={(source) => void toggle(source)}
              onRemove={setRemoving}
            />
          </TabsContent>
        </Tabs>
        <p role="status" aria-label="Результат" className="min-h-6 text-caption font-medium text-primary empty:hidden">
          {message}
        </p>
        <details className="text-caption text-muted-foreground">
          <summary className="cursor-pointer text-primary pointer-coarse:flex pointer-coarse:min-h-11 pointer-coarse:items-center">Як працює відбір вакансій</summary>
          <p className="mt-2">
            Вакансії імпортуються з повним текстом, проходять фільтри профілю та перевірку дублів. Уже імпортоване не приховується автоматично при зміні профілю.
            Керування кар’єрною ціллю, локаціями та правилами відбору — у розділі «Профіль».
          </p>
        </details>
      </div>
      {removing === null ? null : <RemoveDialog key={removing.id} source={removing} onConfirm={() => remove(removing)} onClose={() => setRemoving(null)} />}
    </>
  );
}

function tabLabel(name: string, count: number | undefined): string {
  return count === undefined ? name : `${name} · ${count}`;
}

function FilteredBanner({ count }: { count: number }) {
  if (count === 0) {
    return null;
  }
  return (
    <section aria-label="Вакансії поза фільтром" className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-status-warning p-4 text-caption text-status-warning-foreground">
      <p>
        <strong>{bannerTitle(count)}</strong>
        <br />
        Переглянь причини та вибери, які приховати.
      </p>
      <Button asChild variant="secondary">
        <Link to="/sources/filtered">Переглянути</Link>
      </Button>
    </section>
  );
}

interface ToolbarProps {
  query: SourcesQuery;
  onChange(patch: Partial<SourcesQuery>): void;
}

/** Пошук застосовується за Enter чи «Знайти»; стан — одразу після вибору. */
function Toolbar({ query, onChange }: ToolbarProps) {
  const statusId = useId();
  return (
    <div className="grid gap-3 sm:grid-cols-[minmax(0,2fr)_minmax(0,1fr)] sm:items-end">
      <SearchForm key={query.q} initial={query.q} onSubmit={(q) => onChange({ q })} />
      <div className="flex min-w-0 flex-col gap-1.5">
        <label htmlFor={statusId} className="text-caption font-medium text-muted-foreground">
          Стан
        </label>
        <Select id={statusId} value={query.status} onChange={(event) => onChange({ status: event.target.value as StateFilter })}>
          {STATE_FILTERS.map((status) => (
            <option key={status} value={status}>
              {STATE_FILTER_LABELS[status]}
            </option>
          ))}
        </Select>
      </div>
    </div>
  );
}

function SearchForm({ initial, onSubmit }: { initial: string; onSubmit(query: string): void }) {
  const id = useId();
  const [draft, setDraft] = useState(initial);
  function submit(event: FormEvent) {
    event.preventDefault();
    onSubmit(draft.trim());
  }
  return (
    <form role="search" onSubmit={submit} className="flex min-w-0 flex-col gap-1.5">
      <label htmlFor={id} className="text-caption font-medium text-muted-foreground">
        Пошук
      </label>
      <div className="flex gap-2">
        <div className="relative min-w-0 flex-1">
          <Search aria-hidden="true" className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input id={id} type="search" value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Назва, платформа або параметри" className="pl-9" autoComplete="off" />
        </div>
        <Button type="submit" variant="secondary">
          Знайти
        </Button>
      </div>
    </form>
  );
}

interface ResultsProps {
  state: ReturnType<typeof useSourcesOverview>["state"];
  query: SourcesQuery;
  busyId: string;
  onRetry(): void;
  onReset(): void;
  onOpen(source: Source): void;
  onToggle(source: Source): void;
  onRemove(source: Source): void;
}

function Results({ state, query, busyId, onRetry, onReset, onOpen, onToggle, onRemove }: ResultsProps) {
  if (state.status === "loading") {
    return (
      <div role="status" aria-label="Завантажуємо джерела" className="flex flex-col gap-3">
        <Skeleton className="h-16" />
        <Skeleton className="h-16" />
        <Skeleton className="h-16" />
      </div>
    );
  }
  if (state.status === "error") {
    return (
      <div role="alert" className={ALERT}>
        <p className="text-nav font-medium">{problemText(state.problem, "побачити джерела", "Не вдалося завантажити джерела")}</p>
        {state.problem === "unavailable" ? (
          <>
            <p className="text-caption">Перевір з’єднання й повтори спробу.</p>
            <Button type="button" variant="secondary" onClick={onRetry}>
              Спробувати ще раз
            </Button>
          </>
        ) : null}
      </div>
    );
  }
  const sources = visibleSources(tabSources(state.overview, query.tab), query);
  if (sources.length === 0) {
    return hasSourceFilters(query) ? (
      <Empty title="Немає збігів" hint="Зміни пошук або фільтр стану.">
        <Button type="button" variant="secondary" onClick={onReset}>
          Скинути фільтри
        </Button>
      </Empty>
    ) : (
      <Empty title="Джерел поки немає" hint="Додай компанію чи RSS-стрічку для імпорту вакансій.">
        <Button asChild>
          <Link to={newSourceHref(query.tab)}>Додати джерело</Link>
        </Button>
      </Empty>
    );
  }
  const openId = sources.some((source) => source.id === query.open) ? query.open : "";
  return <SourceRegister sources={sources} tab={query.tab} openId={openId} busyId={busyId} onOpen={onOpen} onToggle={onToggle} onRemove={onRemove} />;
}

function tabSources(overview: SourcesOverview, tab: SourcesTab): Source[] {
  return tab === "companies" ? overview.companies : overview.feeds;
}

function Empty({ title, hint, children }: { title: string; hint: string; children: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-xl border border-border bg-card px-4 py-12 text-center">
      <h2 className="text-section font-semibold">{title}</h2>
      <p className="text-caption text-muted-foreground">{hint}</p>
      {children}
    </div>
  );
}
