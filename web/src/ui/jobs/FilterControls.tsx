import { Search, SlidersHorizontal, X } from "lucide-react";
import { useId, useState, type FormEvent, type ReactNode } from "react";

import { VERDICT_LABELS, VERDICTS, WORK_MODE_LABELS, WORK_MODES, type TriageVerdict, type WorkMode } from "../../domain/analysis";
import { ACTIVE_STATUSES, STATUS_LABELS, type ApplicationStatus } from "../../domain/applications";
import { FRESHNESS_OPTIONS, type FilterCondition, type JobFilters } from "../../domain/jobs";
import { Button } from "../components/button";
import { Input } from "../components/input";
import { Select } from "../components/select";
import { cn } from "../lib/cn";

/** Умови панелі «Фільтри»; пошук і таб до них не належать. */
export type FilterValues = Pick<JobFilters, "days" | "source" | "status" | "verdict" | "mode">;

export const NO_FILTER_VALUES: FilterValues = { days: "", source: "", status: "", verdict: "", mode: "" };

/** Пошук стоїть над табами й застосовується за Enter чи «Знайти»; стан живе в адресі. */
export function SearchForm({ initial, onSubmit }: { initial: string; onSubmit(query: string): void }) {
  const id = useId();
  const [draft, setDraft] = useState(initial);
  function submit(event: FormEvent) {
    event.preventDefault();
    onSubmit(draft.trim());
  }
  return (
    <form role="search" onSubmit={submit} className="flex min-w-0 gap-2">
      <label htmlFor={id} className="sr-only">
        Пошук
      </label>
      <div className="relative min-w-0 flex-1">
        <Search aria-hidden="true" className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input id={id} type="search" value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Посада чи компанія" className="pl-9" autoComplete="off" />
      </div>
      <Button type="submit" variant="secondary">
        Знайти
      </Button>
    </form>
  );
}

interface FiltersToggleProps {
  open: boolean;
  /** Скільки умов застосовано (пошук не рахується). */
  count: number;
  controls: string;
  onToggle(): void;
}

/** Другорядна текстова кнопка без рамки й стрілки: відкриває й закриває панель фільтрів. */
export function FiltersToggle({ open, count, controls, onToggle }: FiltersToggleProps) {
  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      aria-expanded={open}
      aria-controls={controls}
      onClick={onToggle}
      className={cn("shrink-0 px-2 text-muted-foreground hover:bg-transparent hover:text-primary", open && "text-primary")}
    >
      <SlidersHorizontal aria-hidden="true" />
      Фільтри
      {count === 0 ? null : <span className="tabular rounded-md bg-selected px-1.5 text-caption font-medium text-selected-foreground">{count}</span>}
    </Button>
  );
}

interface FilterPanelProps {
  id: string;
  filters: JobFilters;
  /** Джерела вакансій користувача (з відповіді сервера). */
  sources: readonly string[];
  onApply(values: FilterValues): void;
  onReset(): void;
}

/** Умови вибираються в чернетці й застосовуються разом кнопкою «Застосувати фільтри». */
export function FilterPanel({ id, filters, sources, onApply, onReset }: FilterPanelProps) {
  const [draft, setDraft] = useState<FilterValues>({ days: filters.days, source: filters.source, status: filters.status, verdict: filters.verdict, mode: filters.mode });
  const sourceOptions = draft.source === "" || sources.includes(draft.source) ? sources : [...sources, draft.source];
  function set(patch: Partial<FilterValues>) {
    setDraft((current) => ({ ...current, ...patch }));
  }
  function reset() {
    setDraft(NO_FILTER_VALUES);
    onReset();
  }
  return (
    <section id={id} aria-label="Фільтри вакансій" className="flex flex-col gap-4 rounded-xl border border-border bg-card p-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-section font-semibold">Фільтри</h2>
        <Button type="button" variant="ghost" size="sm" onClick={reset}>
          Скинути
        </Button>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <Labeled label="Свіжість">
          {(fieldId) => (
            <Select id={fieldId} value={draft.days} onChange={(event) => set({ days: event.target.value })}>
              {FRESHNESS_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          )}
        </Labeled>
        <Labeled label="Джерело">
          {(fieldId) => (
            <Select id={fieldId} value={draft.source} onChange={(event) => set({ source: event.target.value })}>
              <option value="">Усі джерела</option>
              {sourceOptions.map((source) => (
                <option key={source} value={source}>
                  {source}
                </option>
              ))}
            </Select>
          )}
        </Labeled>
        {filters.tab === "applied" ? (
          <Labeled label="Статус подачі">
            {(fieldId) => (
              <Select id={fieldId} value={draft.status} onChange={(event) => set({ status: event.target.value as "" | ApplicationStatus })}>
                <option value="">Усі статуси</option>
                {ACTIVE_STATUSES.map((status) => (
                  <option key={status} value={status}>
                    {STATUS_LABELS[status]}
                  </option>
                ))}
              </Select>
            )}
          </Labeled>
        ) : null}
        <Labeled label="Вердикт тріажу">
          {(fieldId) => (
            <Select id={fieldId} value={draft.verdict} onChange={(event) => set({ verdict: event.target.value as "" | TriageVerdict })}>
              <option value="">Усі вердикти</option>
              {VERDICTS.map((verdict) => (
                <option key={verdict} value={verdict}>
                  {VERDICT_LABELS[verdict]}
                </option>
              ))}
            </Select>
          )}
        </Labeled>
        <Labeled label="Формат">
          {(fieldId) => (
            <Select id={fieldId} value={draft.mode} onChange={(event) => set({ mode: event.target.value as "" | WorkMode })}>
              <option value="">Усі формати</option>
              {WORK_MODES.map((mode) => (
                <option key={mode} value={mode}>
                  {WORK_MODE_LABELS[mode]}
                </option>
              ))}
            </Select>
          )}
        </Labeled>
      </div>
      <div className="flex justify-end">
        <Button type="button" onClick={() => onApply(draft)}>
          Застосувати фільтри
        </Button>
      </div>
    </section>
  );
}

/** Застосовані умови: кожну можна прибрати окремо. */
export function FilterChips({ conditions, onRemove }: { conditions: readonly FilterCondition[]; onRemove(key: FilterCondition["key"]): void }) {
  if (conditions.length === 0) {
    return null;
  }
  return (
    <ul aria-label="Активні фільтри" className="flex flex-wrap gap-2">
      {conditions.map((condition) => (
        <li key={condition.key}>
          <button
            type="button"
            aria-label={`Прибрати фільтр ${condition.group}: ${condition.value}`}
            onClick={() => onRemove(condition.key)}
            className="inline-flex items-center gap-1.5 rounded-md bg-selected px-2 py-1 text-caption font-medium text-selected-foreground transition-colors duration-140 hover:bg-accent pointer-coarse:min-h-11"
          >
            {`${condition.group}: ${condition.value}`}
            <X aria-hidden="true" className="size-3.5" />
          </button>
        </li>
      ))}
    </ul>
  );
}

function Labeled({ label, children }: { label: string; children: (id: string) => ReactNode }) {
  const id = useId();
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <label htmlFor={id} className="text-caption font-medium text-muted-foreground">
        {label}
      </label>
      {children(id)}
    </div>
  );
}
