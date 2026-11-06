import { Plus } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useBlocker, useSearchParams } from "react-router";

import {
  countFacts,
  filterFacts,
  hasActiveFilters,
  isDraftChanged,
  KIND_LABELS,
  NO_FILTERS,
  SOURCE_LABELS,
  SOURCES,
  STATUS_LABELS,
  STATUSES,
  type Fact,
  type FactDraft,
  type FactFilters,
  type FactSource,
  type StatusFilter,
} from "../../domain/facts";
import { REQUESTS } from "../../domain/prompts";
import { DelegateToAgent } from "../agents/DelegateToAgent";
import { Button } from "../components/button";
import { EmptyState } from "../components/empty-state";
import { Input } from "../components/input";
import { Select } from "../components/select";
import { Skeleton } from "../components/skeleton";
import { usePageTitle } from "../lib/usePageTitle";
import { PageHeading } from "../pages/PageHeading";
import { AddFactForm } from "./AddFactForm";
import { CategoryNav } from "./CategoryNav";
import { DeleteDialog } from "./DeleteDialog";
import { FactItem } from "./FactItem";
import { useFactsServices } from "./FactsServices";
import { OriginalCvPanel } from "./OriginalCvPanel";
import { ReviewNotice } from "./ReviewNotice";
import { UnsavedDialog } from "./UnsavedDialog";
import { useFactLibrary } from "./useFactLibrary";

const GONE = "Факт не знайдено — можливо, його вже видалено. Список оновлено.";

interface Editing {
  id: number;
  draft: FactDraft;
}

export function FactsPage() {
  usePageTitle("Факти");
  const services = useFactsServices();
  const library = useFactLibrary();
  // Посилання з прогалини вакансії відкриває сторінку вже з пошуком (`?q=%2312` — факт #12).
  const [params] = useSearchParams();
  const [filters, setFilters] = useState<FactFilters>({ ...NO_FILTERS, query: params.get("q") ?? "" });
  const [selected, setSelected] = useState<ReadonlySet<number>>(new Set());
  const [editing, setEditing] = useState<Editing | null>(null);
  const [deleting, setDeleting] = useState<Fact | null>(null);
  // Дія, що чекає відповіді користувача на «Є незбережені зміни».
  const [waiting, setWaiting] = useState<(() => void) | null>(null);
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [failure, setFailure] = useState<string | null>(null);
  const resultsRef = useRef<HTMLDivElement>(null);
  const refocus = useRef<number | null | "results">(null);

  const facts = useMemo(() => (library.state.status === "ready" ? library.state.facts : []), [library.state]);
  const counts = useMemo(() => countFacts(facts), [facts]);
  const shown = useMemo(() => filterFacts(facts, filters), [facts, filters]);
  // Вибрані — лише ті, що ще існують і зараз видимі: приховане не підтверджується випадково.
  const chosen = useMemo(() => shown.filter((fact) => selected.has(fact.id)).map((fact) => fact.id), [shown, selected]);

  const editedFact = editing === null ? undefined : facts.find((fact) => fact.id === editing.id);
  const dirty = editing !== null && editedFact !== undefined && isDraftChanged(editedFact, editing.draft);
  const blocker = useBlocker(() => dirty);

  useEffect(() => {
    if (!dirty) {
      return;
    }
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  // Після закриття редактора чи видалення фокус — на «Редагувати» того факту, а якщо його вже нема в списку, на область списку.
  useEffect(() => {
    if (refocus.current === null || editing !== null) {
      return;
    }
    const target = refocus.current;
    refocus.current = null;
    const button = target === "results" ? null : resultsRef.current?.querySelector<HTMLElement>(`[data-edit-button="${target}"]`);
    (button ?? resultsRef.current)?.focus();
  });

  // Обробники елементів списку мають бути стабільними (див. `FactItem`): живі значення беремо з ref.
  const dirtyRef = useRef(dirty);
  useLayoutEffect(() => {
    dirtyRef.current = dirty;
  });
  const confirming = useRef(false);
  const { replace, add, drop, refresh } = library;

  /** Дія, що може втратити чернетку: без правок — одразу, з правками — після відповіді користувача. */
  const guard = useCallback((action: () => void) => {
    if (dirtyRef.current) {
      setWaiting(() => action);
    } else {
      action();
    }
  }, []);

  const changeFilters = useCallback(
    (patch: Partial<FactFilters>) =>
      guard(() => {
        setFilters((current) => ({ ...current, ...patch }));
        setSelected(new Set());
        setEditing(null);
      }),
    [guard],
  );

  const select = useCallback((id: number, next: boolean) => {
    setSelected((current) => {
      const copy = new Set(current);
      if (next) {
        copy.add(id);
      } else {
        copy.delete(id);
      }
      return copy;
    });
  }, []);

  const startEditing = useCallback(
    (fact: Fact) => guard(() => setEditing({ id: fact.id, draft: { kind: fact.kind, text: fact.text } })),
    [guard],
  );

  const updateDraft = useCallback((id: number, draft: FactDraft) => setEditing({ id, draft }), []);

  const closeEditor = useCallback((id: number | "results") => {
    refocus.current = id;
    setEditing(null);
  }, []);

  const confirm = useCallback(
    async (ids: readonly number[], single: Fact | null) => {
      if (confirming.current) {
        return;
      }
      confirming.current = true;
      setBusy(true);
      setNotice("");
      setFailure(null);
      const outcome = await services.confirm(ids);
      confirming.current = false;
      setBusy(false);
      if (outcome.ok) {
        replace(outcome.facts);
        setSelected((current) => new Set([...current].filter((id) => !ids.includes(id))));
        setNotice(single === null ? `Вибрані факти підтверджено: ${outcome.facts.length}.` : `Факт ${single.id} підтверджено. Тепер його можна використати у CV.`);
      } else if (outcome.kind === "invalid") {
        setFailure(outcome.message);
      } else if (outcome.kind === "not-found") {
        setFailure(GONE);
        refresh();
      } else {
        setFailure(single === null ? "Не вдалося підтвердити вибрані факти. Вибір збережено — спробуй ще раз." : `Не вдалося підтвердити факт ${single.id}. Спробуй ще раз.`);
      }
    },
    [services, replace, refresh],
  );

  const confirmOne = useCallback((fact: Fact) => void confirm([fact.id], fact), [confirm]);

  const saved = useCallback(
    (fact: Fact) => {
      replace([fact]);
      setNotice(`Факт ${fact.id} змінено — підтверди його знову.`);
      setFailure(null);
      closeEditor(fact.id);
    },
    [replace, closeEditor],
  );

  const added = useCallback(
    (fact: Fact) => {
      add(fact);
      setNotice(`Факт ${fact.id} додано.`);
      setFailure(null);
      setAdding(false);
    },
    [add],
  );

  const gone = useCallback(
    (id: number) => {
      drop(id);
      setFailure(GONE);
      refresh();
      closeEditor("results");
    },
    [drop, refresh, closeEditor],
  );

  function deleted(fact: Fact, existed: boolean) {
    drop(fact.id);
    setDeleting(null);
    setFailure(existed ? null : GONE);
    setNotice(existed ? `Факт ${fact.id} видалено назавжди.` : "");
    closeEditor("results");
  }

  const blocked = blocker.state === "blocked";
  const subject = editing === null ? "факту" : `факту ${editing.id}`;

  return (
    <>
      <div className="flex flex-wrap items-start justify-between gap-x-4">
        <PageHeading title="Факти" subtitle="Атомарні твердження з твого CV. У CV потрапляють лише підтверджені факти." />
        {library.state.status === "ready" && !adding ? (
          <Button onClick={() => setAdding(true)}>
            <Plus aria-hidden="true" />
            Додати факт
          </Button>
        ) : null}
      </div>
      <div className="flex flex-col gap-4">
        <OriginalCvPanel cv={library.cv} />
        <p role="status" aria-label="Повідомлення" className="sr-only">
          {notice}
        </p>
        {adding ? <AddFactForm onAdded={added} onCancel={() => setAdding(false)} /> : null}
        <DelegateToAgent request={REQUESTS.facts} description="Агент допоможе сформулювати нові факти й збереже їх після твого схвалення." />
        {notice === "" ? null : (
          <p aria-hidden="true" className="rounded-lg bg-status-success px-3 py-2 text-caption font-medium text-status-success-foreground">
            {notice}
          </p>
        )}
        {failure === null ? null : (
          <p role="alert" className="rounded-lg bg-status-danger px-3 py-2 text-caption font-medium text-status-danger-foreground">
            {failure}
          </p>
        )}
        {library.state.status === "loading" ? <FactsSkeleton /> : null}
        {library.state.status === "error" ? (
          <div role="alert" className="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-status-danger p-4 text-status-danger-foreground">
            <p className="text-nav font-medium">Не вдалося завантажити факти.</p>
            <Button variant="secondary" onClick={library.reload}>
              Спробувати ще
            </Button>
          </div>
        ) : null}
        {library.state.status === "ready" && facts.length === 0 ? (
          <EmptyState title="Фактів поки немає" hint="Прикріпи своє CV в чаті й попроси Claude розібрати CV: факти зʼявляться тут на перевірку." />
        ) : null}
        {library.state.status === "ready" && facts.length > 0 ? (
          <>
            <ReviewNotice
              counts={counts}
              onReview={() => changeFilters({ query: "", status: "pending", kind: null })}
            />
            <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_14rem_14rem]">
              <Input
                type="search"
                aria-label="Пошук фактів"
                placeholder="Пошук за текстом або #номером"
                autoComplete="off"
                value={filters.query}
                onChange={(event) => changeFilters({ query: event.target.value })}
              />
              <Select aria-label="Статус" value={filters.status} onChange={(event) => changeFilters({ status: event.target.value as StatusFilter })}>
                {STATUSES.map((status) => (
                  <option key={status} value={status}>
                    {STATUS_LABELS[status]}
                  </option>
                ))}
              </Select>
              <Select
                aria-label="Джерело"
                value={filters.source ?? "all"}
                onChange={(event) => changeFilters({ source: event.target.value === "all" ? null : (event.target.value as FactSource) })}
              >
                <option value="all">Усі джерела</option>
                {SOURCES.map((source) => (
                  <option key={source} value={source}>
                    {SOURCE_LABELS[source]}
                  </option>
                ))}
              </Select>
            </div>
            <div className="grid gap-4 lg:grid-cols-[13rem_minmax(0,1fr)]">
              <CategoryNav counts={counts} value={filters.kind} onChange={(kind) => changeFilters({ kind })} />
              <div ref={resultsRef} tabIndex={-1} className="flex min-w-0 flex-col gap-3 outline-none">
                {/* Рядок не міняє висоти, коли зʼявляються кнопки вибору, і лишається на місці при прокрутці довгого списку. */}
                <div className="sticky top-0 z-10 flex min-h-12 flex-wrap items-center justify-between gap-x-3 gap-y-1 bg-background py-1">
                  <h2 className="text-section font-semibold">{`${filters.kind === null ? "Усі" : KIND_LABELS[filters.kind]} · ${shown.length}`}</h2>
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-caption text-muted-foreground">{`Вибрано: ${chosen.length}`}</p>
                    {chosen.length === 0 ? null : (
                      <>
                        <Button size="sm" disabled={busy} onClick={() => void confirm(chosen, null)}>
                          {`Підтвердити вибрані (${chosen.length})`}
                        </Button>
                        <Button size="sm" variant="secondary" onClick={() => setSelected(new Set())}>
                          Зняти вибір
                        </Button>
                      </>
                    )}
                  </div>
                </div>
                {shown.length === 0 ? (
                  <div className="rounded-xl border border-border bg-card px-4 py-12 text-center">
                    <p className="text-section font-semibold">Фактів не знайдено</p>
                    <p className="mt-1 text-caption text-muted-foreground">Змініть пошук або фільтри.</p>
                    {hasActiveFilters(filters) ? (
                      <Button className="mt-4" variant="secondary" onClick={() => changeFilters(NO_FILTERS)}>
                        Скинути фільтри
                      </Button>
                    ) : null}
                  </div>
                ) : (
                  <ul aria-label="Факти" className="flex flex-col gap-3">
                    {shown.map((fact) => (
                      <FactItem
                        key={fact.id}
                        fact={fact}
                        selected={selected.has(fact.id)}
                        draft={editing?.id === fact.id ? editing.draft : null}
                        onSelect={select}
                        onConfirm={confirmOne}
                        onEdit={startEditing}
                        onDraft={updateDraft}
                        onCancel={closeEditor}
                        onDelete={setDeleting}
                        onSaved={saved}
                        onGone={gone}
                      />
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </>
        ) : null}
      </div>
      <DeleteDialog
        target={deleting}
        onClose={() => setDeleting(null)}
        onDeleted={deleted}
        focusAfterDelete={() => resultsRef.current?.focus()}
      />
      <UnsavedDialog
        open={waiting !== null || blocked}
        subject={subject}
        onStay={() => {
          setWaiting(null);
          if (blocked) {
            blocker.reset();
          }
        }}
        onDiscard={() => {
          const action = waiting;
          setWaiting(null);
          if (action !== null) {
            action();
          } else if (blocked) {
            blocker.proceed();
          }
        }}
      />
    </>
  );
}

function FactsSkeleton() {
  return (
    <div role="status" aria-label="Завантажуємо факти" aria-busy="true" className="flex flex-col gap-3">
      <Skeleton className="h-14" />
      <Skeleton className="h-10" />
      {Array.from({ length: 4 }, (_, index) => (
        <Skeleton key={index} className="h-24" />
      ))}
    </div>
  );
}
