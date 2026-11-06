import { Search } from "lucide-react";
import { useId, useState, type FormEvent, type ReactNode } from "react";
import { useSearchParams } from "react-router";

import { PAGE_SIZES, type PageSize } from "../../domain/mail";
import {
  hasReplyFilters,
  openReplyId,
  parseReplyQuery,
  QUEUE_LABELS,
  REPLY_QUEUES,
  replyQueryParams,
  type ReplyCounts,
  type ReplyQuery,
  type ReplyQueue,
} from "../../domain/replies";
import { Button } from "../components/button";
import { Input } from "../components/input";
import { Select } from "../components/select";
import { Skeleton } from "../components/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/tabs";
import { cn } from "../lib/cn";
import { useMediaQuery } from "../lib/useMediaQuery";
import { usePageTitle } from "../lib/usePageTitle";
import { Pager } from "../mail/Pager";
import { problemText } from "../mail/texts";
import { PageHeading } from "../pages/PageHeading";
import { ReplyReader } from "./ReplyReader";
import { ReplyRow } from "./ReplyRow";
import { useReplyBoard, type ReplyBoardState } from "./useReplyBoard";

/** Від цієї ширини (64rem, `lg`) відповідь відкривається поруч зі списком, нижче — замість нього. */
const SPLIT = "(min-width: 64rem)";
const ALERT = "flex flex-wrap items-center gap-3 rounded-xl border border-border bg-status-danger p-4 text-status-danger-foreground";

const EMPTY: Record<ReplyQueue, { title: string; hint: string }> = {
  matched: { title: "У цій черзі все розібрано", hint: "Нові відповіді з’являться після пересилання та синхронізації пошти." },
  unmatched: { title: "Відповідей без вакансії немає", hint: "Усі листи компаній зіставлено з подачами." },
  reviewed: { title: "Розібраних відповідей поки немає", hint: "Розібрані листи з’являться тут." },
};

/** `/replies`: три черги відповідей компаній, пошук, сторінки й розбір. Усе, крім чернетки форми, живе в адресі сторінки. */
export function RepliesArea() {
  usePageTitle("Відповіді");
  const [params, setParams] = useSearchParams();
  const query = parseReplyQuery(params);
  const open = openReplyId(params);
  const { state, counts, reload } = useReplyBoard(query);
  const split = useMediaQuery(SPLIT, true);

  function go(next: ReplyQuery, opened: number | null = null) {
    const target = replyQueryParams(next);
    if (opened !== null) {
      target.set("open", String(opened));
    }
    setParams(target);
  }
  const reset = () => go({ ...query, q: "", page: 1 });
  // Після розбору лист живе в «Розібраних»; лічильники беруться з нової відповіді.
  const reviewed = (id: number) => {
    go({ queue: "reviewed", q: "", page: 1, perPage: query.perPage }, id);
    reload();
  };

  // На вузькому екрані відкрита відповідь займає весь екран: черги й пошук повертаються з «← До списку».
  const reading = !split && open !== null;
  return (
    <>
      <PageHeading title="Відповіді" subtitle="Розбери листи та підтвердь зміни у подачах." />
      <div className="flex flex-col gap-4">
        {reading ? null : (
          <Tabs value={query.queue} onValueChange={(queue) => go({ ...query, queue: queue as ReplyQueue, page: 1 })}>
              <TabsList aria-label="Черги відповідей" className="max-sm:w-full">
                {REPLY_QUEUES.map((queue) => (
                  <TabsTrigger key={queue} value={queue} className="max-sm:h-auto max-sm:min-w-0 max-sm:flex-1 max-sm:py-1.5 max-sm:whitespace-normal">
                    {tabLabel(queue, counts)}
                  </TabsTrigger>
                ))}
              </TabsList>
              <TabsContent value={query.queue} className="flex flex-col gap-4">
                <Toolbar query={query} onChange={(patch) => go({ ...query, page: 1, ...patch })} />
                <Results
                  state={state}
                  query={query}
                  open={open}
                  split={split}
                  onRetry={reload}
                  onReset={reset}
                  onPage={(page) => go({ ...query, page })}
                  onOpen={(id) => go(query, id)}
                  onReviewed={reviewed}
                />
              </TabsContent>
          </Tabs>
        )}
        {reading ? <ReplyReader openId={open} onBack={() => go(query)} onReviewed={reviewed} /> : null}
      </div>
    </>
  );
}

function tabLabel(queue: ReplyQueue, counts: ReplyCounts | null): string {
  return counts === null ? QUEUE_LABELS[queue] : `${QUEUE_LABELS[queue]} · ${counts[queue]}`;
}

interface ResultsProps {
  state: ReplyBoardState;
  query: ReplyQuery;
  open: number | null;
  split: boolean;
  onRetry(): void;
  onReset(): void;
  onPage(page: number): void;
  onOpen(id: number): void;
  onReviewed(id: number): void;
}

function Results({ state, query, open, split, onRetry, onReset, onPage, onOpen, onReviewed }: ResultsProps) {
  if (state.status === "loading") {
    return (
      <div role="status" aria-label="Завантажуємо відповіді…" className="flex flex-col gap-3">
        <Skeleton className="h-20" />
        <Skeleton className="h-20" />
        <Skeleton className="h-20" />
      </div>
    );
  }
  if (state.status === "error") {
    return (
      <div role="alert" className={ALERT}>
        <p className="text-nav font-medium">{problemText(state.problem, "побачити відповіді", "Не вдалося завантажити відповіді.")}</p>
        {state.problem === "unavailable" ? (
          <Button type="button" variant="secondary" onClick={onRetry}>
            Спробувати ще раз
          </Button>
        ) : null}
      </div>
    );
  }
  const { items, page } = state.board;
  if (page.total === 0) {
    return hasReplyFilters(query) ? (
      <Empty title="Немає збігів" hint="Спробуй інший запит.">
        <Button type="button" variant="secondary" onClick={onReset}>
          Скинути пошук
        </Button>
      </Empty>
    ) : (
      <Empty title={EMPTY[query.queue].title} hint={EMPTY[query.queue].hint} />
    );
  }
  return (
    <div className="flex flex-col gap-3">
      <p className="text-caption font-medium text-muted-foreground">{`Відповіді компаній · ${page.total}`}</p>
      <div className={cn("grid items-start gap-4", split && "grid-cols-[minmax(0,26rem)_minmax(0,1fr)]")}>
        <div className="flex min-w-0 flex-col gap-3">
          {items.length === 0 ? (
            <div className="flex flex-col items-start gap-2 rounded-xl border border-border bg-card p-4">
              <p className="text-nav font-medium">На цій сторінці відповідей нема</p>
              <Button type="button" variant="secondary" onClick={() => onPage(1)}>
                На першу сторінку
              </Button>
            </div>
          ) : (
            <ul aria-label="Список відповідей" className="flex flex-col gap-2">
              {items.map((reply) => (
                <ReplyRow key={reply.id} reply={reply} selected={open === reply.id} onOpen={() => onOpen(reply.id)} />
              ))}
            </ul>
          )}
          <Pager page={page} onPage={onPage} />
        </div>
        {split ? <ReplyReader openId={open} onBack={null} onReviewed={onReviewed} /> : null}
      </div>
    </div>
  );
}

function Empty({ title, hint, children }: { title: string; hint: string; children?: ReactNode }) {
  return (
    <div data-testid="empty" className="flex flex-col items-center gap-2 rounded-xl border border-border bg-card px-4 py-12 text-center">
      <h2 className="text-section font-semibold">{title}</h2>
      <p className="text-caption text-muted-foreground">{hint}</p>
      {children}
    </div>
  );
}

interface ToolbarProps {
  query: ReplyQuery;
  onChange(patch: Partial<ReplyQuery>): void;
}

/** Пошук застосовується за Enter чи «Знайти»; розмір сторінки — одразу після вибору. */
function Toolbar({ query, onChange }: ToolbarProps) {
  const sizeId = useId();
  return (
    <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_8rem] sm:items-end">
      <SearchForm key={query.q} initial={query.q} onSubmit={(q) => onChange({ q })} />
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
          <Input id={id} type="search" value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Відправник, компанія, тема або текст" className="pl-9" autoComplete="off" />
        </div>
        <Button type="submit" variant="secondary">
          Знайти
        </Button>
      </div>
    </form>
  );
}
