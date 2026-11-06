import { Search } from "lucide-react";
import { useId, useState, type FormEvent, type ReactNode } from "react";
import { useSearchParams } from "react-router";

import {
  hasMailFilters,
  KIND_LABELS,
  mailQueryParams,
  MAIL_KINDS,
  PAGE_SIZES,
  parseMailQuery,
  madridDay,
  madridTime,
  type MailItem,
  type MailKind,
  type MailQuery,
  type PageSize,
} from "../../domain/mail";
import { Button } from "../components/button";
import { Input } from "../components/input";
import { Select } from "../components/select";
import { Skeleton } from "../components/skeleton";
import { cn } from "../lib/cn";
import { useMediaQuery } from "../lib/useMediaQuery";
import { useMail } from "./MailProvider";
import { MailReader, type OpenMail } from "./MailReader";
import { MailRow } from "./MailRow";
import { Pager } from "./Pager";
import { problemText } from "./texts";
import { useMailList } from "./useMailList";

/** Від цієї ширини (64rem, `lg`) лист відкривається поруч зі списком, нижче — замість нього. */
const SPLIT = "(min-width: 64rem)";
const ALERT = "flex flex-wrap items-center gap-3 rounded-xl border border-border bg-status-danger p-4 text-status-danger-foreground";
const POSITIVE_INTEGER = /^[1-9]\d*$/;

/** Відкритий лист з адреси сторінки: `open=<номер>`, для відкинутого ще й `dropped=1` (номери двох таблиць не збігаються). */
function openFrom(params: URLSearchParams): OpenMail | null {
  const id = params.get("open") ?? "";
  return POSITIVE_INTEGER.test(id) ? { id: Number(id), dropped: params.get("dropped") === "1" } : null;
}

export function InboxTab() {
  const [params, setParams] = useSearchParams();
  const query = parseMailQuery(params);
  const open = openFrom(params);
  const { state, reload } = useMailList(query);
  const split = useMediaQuery(SPLIT, true);

  function go(next: MailQuery, opened: OpenMail | null = null) {
    const target = mailQueryParams(next);
    if (opened !== null) {
      target.set("open", String(opened.id));
      if (opened.dropped) {
        target.set("dropped", "1");
      }
    }
    setParams(target);
  }
  const reset = () => go({ ...query, q: "", kind: "", page: 1 });

  // На вузькому екрані відкритий лист займає весь екран: пошук і синк повертаються з «← До списку».
  const reading = !split && open !== null;
  return (
    <div className="flex flex-col gap-4">
      {reading ? null : (
        <>
          <Toolbar query={query} onChange={(patch) => go({ ...query, page: 1, ...patch })} onReset={reset} />
          <SyncBar />
        </>
      )}
      <Results
        state={state}
        query={query}
        open={open}
        split={split}
        onRetry={reload}
        onReset={reset}
        onSettings={() => setParams(new URLSearchParams({ tab: "settings" }))}
        onPage={(page) => go({ ...query, page })}
        onOpen={(item) => go(query, { id: item.id, dropped: item.dropped })}
        onClose={() => go(query)}
      />
    </div>
  );
}

interface ResultsProps {
  state: ReturnType<typeof useMailList>["state"];
  query: MailQuery;
  open: OpenMail | null;
  split: boolean;
  onRetry(): void;
  onReset(): void;
  onSettings(): void;
  onPage(page: number): void;
  onOpen(item: MailItem): void;
  onClose(): void;
}

function Results({ state, query, open, split, onRetry, onReset, onSettings, onPage, onOpen, onClose }: ResultsProps) {
  if (state.status === "loading") {
    return (
      <div role="status" aria-label="Завантажуємо листи…" className="flex flex-col gap-3">
        <Skeleton className="h-20" />
        <Skeleton className="h-20" />
        <Skeleton className="h-20" />
      </div>
    );
  }
  if (state.status === "error") {
    return (
      <div role="alert" className={ALERT}>
        <p className="text-nav font-medium">{problemText(state.problem, "побачити листи", "Не вдалося завантажити листи.")}</p>
        {state.problem === "unavailable" ? (
          <Button type="button" variant="secondary" onClick={onRetry}>
            Спробувати ще раз
          </Button>
        ) : null}
      </div>
    );
  }
  const { items, page } = state.list;
  if (page.total === 0) {
    return hasMailFilters(query) ? (
      <Empty title="Немає збігів" hint="Спробуй інший запит або скинь фільтри.">
        <Button type="button" variant="secondary" onClick={onReset}>
          Скинути фільтри
        </Button>
      </Empty>
    ) : (
      <Empty title="Листів поки немає" hint="Налаштуй пересилання, потім синхронізуй скриньку.">
        <Button type="button" onClick={onSettings}>
          Налаштувати пересилання
        </Button>
      </Empty>
    );
  }
  const showList = split || open === null;
  const showReader = split || open !== null;
  return (
    <div className="flex flex-col gap-3">
      <p className="text-caption font-medium text-muted-foreground">{`Усі переслані листи · ${page.total}`}</p>
      <div className={cn("grid items-start gap-4", split && "grid-cols-[minmax(0,26rem)_minmax(0,1fr)]")}>
        {showList ? (
          <div className="flex min-w-0 flex-col gap-3">
            {items.length === 0 ? (
              <div className="flex flex-col items-start gap-2 rounded-xl border border-border bg-card p-4">
                <p className="text-nav font-medium">На цій сторінці листів нема</p>
                <Button type="button" variant="secondary" onClick={() => onPage(1)}>
                  На першу сторінку
                </Button>
              </div>
            ) : (
              <ul aria-label="Список листів" className="flex flex-col gap-2">
                {items.map((item) => (
                  <MailRow
                    key={`${item.dropped ? "d" : "m"}${item.id}`}
                    item={item}
                    selected={open !== null && open.id === item.id && open.dropped === item.dropped}
                    onOpen={() => onOpen(item)}
                  />
                ))}
              </ul>
            )}
            <Pager page={page} onPage={onPage} />
          </div>
        ) : null}
        {showReader ? <MailReader open={open} items={items} onBack={split ? null : onClose} /> : null}
      </div>
    </div>
  );
}

function Empty({ title, hint, children }: { title: string; hint: string; children: ReactNode }) {
  return (
    <div data-testid="empty" className="flex flex-col items-center gap-2 rounded-xl border border-border bg-card px-4 py-12 text-center">
      <h2 className="text-section font-semibold">{title}</h2>
      <p className="text-caption text-muted-foreground">{hint}</p>
      {children}
    </div>
  );
}

interface ToolbarProps {
  query: MailQuery;
  onChange(patch: Partial<MailQuery>): void;
  onReset(): void;
}

/** Пошук застосовується за Enter чи «Знайти»; вид і розмір сторінки — одразу після вибору. Стан живе в адресі. */
function Toolbar({ query, onChange, onReset }: ToolbarProps) {
  const kindId = useId();
  const sizeId = useId();
  return (
    <div className="flex flex-col gap-3">
      <SearchForm key={query.q} initial={query.q} onSubmit={(q) => onChange({ q })} />
      <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_8rem_auto] sm:items-end">
        <div className="flex min-w-0 flex-col gap-1.5">
          <label htmlFor={kindId} className="text-caption font-medium text-muted-foreground">
            Вид листа
          </label>
          <Select id={kindId} value={query.kind} onChange={(event) => onChange({ kind: event.target.value as "" | MailKind })}>
            <option value="">Усі види</option>
            {MAIL_KINDS.map((kind) => (
              <option key={kind} value={kind}>
                {KIND_LABELS[kind]}
              </option>
            ))}
          </Select>
        </div>
        <div className="flex min-w-0 flex-col gap-1.5">
          <label htmlFor={sizeId} className="text-caption font-medium text-muted-foreground">
            На сторінці
          </label>
          <Select id={sizeId} value={String(query.perPage)} onChange={(event) => onChange({ perPage: Number(event.target.value) as PageSize })}>
            {PAGE_SIZES.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </Select>
        </div>
        {hasMailFilters(query) ? (
          <Button type="button" variant="ghost" onClick={onReset}>
            Скинути фільтри
          </Button>
        ) : null}
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
          <Input id={id} type="search" value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Відправник, тема або текст" className="pl-9" autoComplete="off" />
        </div>
        <Button type="submit" variant="secondary">
          Знайти
        </Button>
      </div>
    </form>
  );
}

/** Рядок про синк і кнопка «Синхронізувати»: ті самі дані, що в «Налаштуваннях». */
function SyncBar() {
  const { state, manual, queued, requesting, syncMessage, requestSync } = useMail();
  const text = state.status === "ready" && manual !== null ? syncLine(state.settings.syncFailed, state.settings.syncedAt, manual, queued) : null;
  const blocked = queued || requesting || manual === null || manual.remaining === 0;
  return (
    <div className="flex flex-col gap-1">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-caption text-muted-foreground">{text}</p>
        <Button type="button" variant="secondary" disabled={blocked} onClick={() => void requestSync()}>
          {queued ? "Запит у черзі" : "Синхронізувати"}
        </Button>
      </div>
      <p role="status" className="text-caption text-status-danger-foreground empty:hidden">
        {syncMessage}
      </p>
    </div>
  );
}

function syncLine(
  failed: boolean,
  syncedAt: string | null,
  manual: { limit: number; remaining: number },
  queued: boolean,
): string {
  const last = failed ? "Синк: останній запуск не вдався" : syncedAt === null ? "Синку ще не було" : `Синк: ${madridDay(syncedAt)} · ${madridTime(syncedAt)} · Мадрид`;
  return `${last} · ${manual.remaining} з ${manual.limit} ручних запитів${queued ? " · запит очікує серверного таймера" : ""}`;
}
