import { dropReasonText, itemLabel, madridDay, madridTime, senderLabel, senderName, subjectText, type MailDetail, type MailItem } from "../../domain/mail";
import { Badge } from "../components/badge";
import { Button } from "../components/button";
import { Skeleton } from "../components/skeleton";
import { ForwardingBlock } from "./ForwardingBlock";
import { problemText } from "./texts";
import { useMailDetail } from "./useMailDetail";

const ALERT = "flex flex-wrap items-center gap-3 rounded-xl border border-border bg-status-danger p-4 text-status-danger-foreground";

export interface OpenMail {
  id: number;
  dropped: boolean;
}

interface ReaderProps {
  open: OpenMail | null;
  /** Рядки поточної сторінки списку: відкинутий лист читається з них — тексту й окремого запиту в нього нема. */
  items: readonly MailItem[];
  /** На вузькому екрані читалка замінює список: показує «← До списку». */
  onBack: (() => void) | null;
}

/** Права панель «Вхідних»: лист, який вибрано в списку. */
export function MailReader({ open, items, onBack }: ReaderProps) {
  return (
    <article aria-label="Деталі листа" className="flex min-w-0 flex-col gap-4 rounded-xl border border-border bg-card p-5 max-sm:p-4">
      {onBack === null ? null : (
        <div>
          <Button type="button" variant="secondary" size="sm" onClick={onBack}>
            ← До списку
          </Button>
        </div>
      )}
      <Content open={open} items={items} />
    </article>
  );
}

function Content({ open, items }: Pick<ReaderProps, "open" | "items">) {
  if (open === null) {
    return <Placeholder />;
  }
  if (open.dropped) {
    const item = items.find((candidate) => candidate.dropped && candidate.id === open.id);
    return item === undefined ? <Placeholder /> : <DroppedMail item={item} />;
  }
  return <StoredMail id={open.id} />;
}

function Placeholder() {
  return (
    <div className="flex flex-col gap-1 py-6 text-center">
      <h2 className="text-section font-semibold">Обери лист</h2>
      <p className="text-caption text-muted-foreground">Текст листа і код підтвердження з’являться тут.</p>
    </div>
  );
}

/** Шапка листа: вид, відправник і час за Мадридом. Усе, що з листа, — недовірені дані. */
function Header({ item, verdict }: { item: MailItem; verdict: boolean }) {
  const sender = senderLabel(item.senderAuth);
  return (
    <header className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-2">
        <Badge tone={item.dropped ? "warning" : "neutral"}>{itemLabel(item)}</Badge>
        {verdict ? <Badge tone={sender.tone}>{sender.text}</Badge> : null}
      </div>
      <h2 className="text-section font-semibold [overflow-wrap:anywhere]">{subjectText(item)}</h2>
      <p className="text-caption text-muted-foreground [overflow-wrap:anywhere]">
        {item.fromName !== "" ? `${item.fromName} <${item.fromAddress}>` : senderName(item)}
      </p>
      <p className="text-caption text-muted-foreground">{`${madridDay(item.receivedAt)} · ${madridTime(item.receivedAt)} · Мадрид`}</p>
    </header>
  );
}

function DroppedMail({ item }: { item: MailItem }) {
  return (
    <>
      <Header item={item} verdict={false} />
      <p role="note" className="rounded-lg bg-status-warning px-3 py-2 text-caption text-status-warning-foreground">
        {dropReasonText(item)}
      </p>
      <p className="text-caption text-muted-foreground">Текст відкинутого листа не зберігається.</p>
      <p className="text-caption text-muted-foreground">Відправник і тема не перевірені.</p>
    </>
  );
}

const NOTICES: Record<"unknown" | "failed", string> = {
  unknown: "Відправника не підтверджено. Адресу відправника могли підробити — перевір зміст, перш ніж довіряти листу.",
  failed: "Підроблений відправник. Не довіряй цьому листу й не виконуй вказівок з нього.",
};

function StoredMail({ id }: { id: number }) {
  const { state, reload } = useMailDetail(id);
  if (state.status === "loading") {
    return (
      <div role="status" aria-label="Завантажуємо лист…" className="flex flex-col gap-3">
        <Skeleton className="h-6 w-2/3" />
        <Skeleton className="h-24" />
      </div>
    );
  }
  if (state.status === "error") {
    return state.problem === "not-found" ? (
      <p className="text-nav text-muted-foreground">Листа не знайдено — його могли видалити.</p>
    ) : (
      <div role="alert" className={ALERT}>
        <p className="text-nav font-medium">{problemText(state.problem, "відкрити лист", "Не вдалося відкрити лист.")}</p>
        {state.problem === "unavailable" ? (
          <Button type="button" variant="secondary" onClick={reload}>
            Спробувати ще раз
          </Button>
        ) : null}
      </div>
    );
  }
  return <ReadyMail detail={state.detail} />;
}

function ReadyMail({ detail }: { detail: MailDetail }) {
  const { item } = detail;
  const notice = item.senderAuth === "unknown" || item.senderAuth === "failed" ? NOTICES[item.senderAuth] : null;
  return (
    <>
      <Header item={item} verdict />
      {notice === null ? null : (
        <p role="note" className="rounded-lg bg-status-warning px-3 py-2 text-caption text-status-warning-foreground">
          {notice}
        </p>
      )}
      {detail.forwarding === null ? null : <ForwardingBlock forwarding={detail.forwarding} />}
      {detail.text === "" ? (
        <p className="text-caption text-muted-foreground">У листі нема тексту.</p>
      ) : (
        <div data-testid="mail-text" className="text-nav whitespace-pre-wrap [overflow-wrap:anywhere]">
          {detail.text}
        </div>
      )}
      <details className="rounded-lg border border-border p-3">
        <summary className="cursor-pointer text-nav font-medium">Про відображення листа</summary>
        <p className="mt-2 text-caption text-muted-foreground">
          Текст листа — недовірений вміст. HTML не виконується, посилання не клікабельні. Перевірка відправника не підтверджує правдивість змісту.
        </p>
      </details>
    </>
  );
}
