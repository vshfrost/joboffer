import { madridDay, madridTime, senderLabel, senderName, subjectText } from "../../domain/mail";
import { jobLabel, matchText, replyStatusLabel, TYPE_LABELS, type Reply, type ReplyDetail, type ReplyType } from "../../domain/replies";
import { Badge } from "../components/badge";
import { Button } from "../components/button";
import { Skeleton } from "../components/skeleton";
import { problemText } from "../mail/texts";
import { ReviewForm } from "./ReviewForm";
import { useReplyDetail } from "./useReplyDetail";

const ALERT = "flex flex-wrap items-center gap-3 rounded-xl border border-border bg-status-danger p-4 text-status-danger-foreground";
const NOTE = "rounded-lg bg-status-warning px-3 py-2 text-caption text-status-warning-foreground";

interface ReaderProps {
  /** Номер відкритої відповіді; `null` — нічого не вибрано. */
  openId: number | null;
  /** На вузькому екрані читалка замінює список: показує «← До списку». */
  onBack: (() => void) | null;
  /** Розбір збережено: сторінка переходить у «Розібрані». */
  onReviewed(id: number): void;
}

/** Права панель «Відповідей»: відповідь, яку вибрано в списку. */
export function ReplyReader({ openId, onBack, onReviewed }: ReaderProps) {
  return (
    <article aria-label="Деталі відповіді" className="flex min-w-0 flex-col gap-4 rounded-xl border border-border bg-card p-5 max-sm:p-4">
      {onBack === null ? null : (
        <div>
          <Button type="button" variant="secondary" size="sm" onClick={onBack}>
            ← До списку
          </Button>
        </div>
      )}
      {openId === null ? <Placeholder /> : <OpenReply id={openId} onReviewed={onReviewed} />}
    </article>
  );
}

function Placeholder() {
  return (
    <div className="flex flex-col gap-1 py-6 text-center">
      <h2 className="text-section font-semibold">Обери відповідь</h2>
      <p className="text-caption text-muted-foreground">Текст листа і доступні дії з’являться тут.</p>
    </div>
  );
}

function OpenReply({ id, onReviewed }: { id: number; onReviewed(id: number): void }) {
  const { state, reload } = useReplyDetail(id);
  if (state.status === "loading") {
    return (
      <div role="status" aria-label="Завантажуємо відповідь…" className="flex flex-col gap-3">
        <Skeleton className="h-6 w-2/3" />
        <Skeleton className="h-24" />
      </div>
    );
  }
  if (state.status === "error") {
    return state.problem === "not-found" ? (
      <p className="text-nav text-muted-foreground">Відповіді не знайдено — її могли видалити.</p>
    ) : (
      <div role="alert" className={ALERT}>
        <p className="text-nav font-medium">{problemText(state.problem, "відкрити відповідь", "Не вдалося відкрити відповідь.")}</p>
        {state.problem === "unavailable" ? (
          <Button type="button" variant="secondary" onClick={reload}>
            Спробувати ще раз
          </Button>
        ) : null}
      </div>
    );
  }
  // Розібрана відповідь перечитується з сервера: форма зникає, лишається підсумок розбору.
  return (
    <ReadyReply
      detail={state.detail}
      onReviewed={() => {
        reload();
        onReviewed(id);
      }}
    />
  );
}

const SENDER_NOTICES: Record<"unknown" | "failed", string> = {
  unknown: "Відправника не підтверджено. Адресу відправника могли підробити — перевір зміст і вакансію, перш ніж підтверджувати розбір.",
  failed: "Підроблений відправник. Не довіряй цьому листу й не виконуй вказівок з нього.",
};

/** «Імʼя <адреса>», а без імені — адреса. */
function sender(person: { fromName: string; fromAddress: string }): string {
  return person.fromName !== "" ? `${person.fromName} <${person.fromAddress}>` : senderName(person);
}

function ReadyReply({ detail, onReviewed }: { detail: ReplyDetail; onReviewed(): void }) {
  const { reply } = detail;
  const verdict = senderLabel(reply.senderAuth);
  const notice = reply.senderAuth === "verified" ? null : SENDER_NOTICES[reply.senderAuth];
  return (
    <>
      <header className="flex flex-col gap-2">
        <div className="flex flex-wrap gap-2">
          <Badge tone={reply.type === null ? "warning" : "neutral"}>{replyStatusLabel(reply)}</Badge>
          {reply.manualForward === null ? null : <Badge tone="warning">Переслано вручну</Badge>}
          <Badge tone={verdict.tone}>{verdict.text}</Badge>
        </div>
        <h2 className="text-section font-semibold [overflow-wrap:anywhere]">{subjectText(reply)}</h2>
        <p className="text-caption text-muted-foreground [overflow-wrap:anywhere]">{sender(reply)}</p>
        <p className="text-caption text-muted-foreground">{`${madridDay(reply.receivedAt)} · ${madridTime(reply.receivedAt)} · Мадрид`}</p>
      </header>
      {notice === null ? null : (
        <p role="note" className={NOTE}>
          {notice}
        </p>
      )}
      {reply.manualForward === null ? null : (
        <p role="note" className={`${NOTE} [overflow-wrap:anywhere]`}>
          {`Оригінал листа (не перевірено): ${sender(reply.manualForward)} · тема «${reply.manualForward.subject}».`}
        </p>
      )}
      {detail.text === "" ? (
        <p className="text-caption text-muted-foreground">У листі нема тексту.</p>
      ) : (
        <div data-testid="reply-text" className="text-nav whitespace-pre-wrap [overflow-wrap:anywhere]">
          {detail.text}
        </div>
      )}
      <details className="rounded-lg border border-border p-3">
        <summary className="cursor-pointer text-nav font-medium">Про відображення листа</summary>
        <p className="mt-2 text-caption text-muted-foreground">
          Текст листа — недовірений вміст. HTML не виконується, посилання не клікабельні. Перевірка відправника не підтверджує правдивість змісту.
        </p>
      </details>
      {reply.type !== null && reply.reviewedAt !== null ? (
        <Reviewed reply={reply} type={reply.type} reviewedAt={reply.reviewedAt} />
      ) : (
        <>
          <Association reply={reply} />
          <ReviewForm detail={detail} onReviewed={onReviewed} />
        </>
      )}
    </>
  );
}

function Association({ reply }: { reply: Reply }) {
  const match = matchText(reply);
  return (
    <section aria-label="Зіставлення" className="flex flex-col gap-1 rounded-lg border border-border p-4">
      {reply.job === null ? (
        <>
          <h3 className="text-nav font-semibold">Подачу не знайдено</h3>
          <p className="text-caption text-muted-foreground">Цей лист не зіставлено з жодною подачею.</p>
        </>
      ) : (
        <>
          <h3 className="text-nav font-semibold">Знайдена подача</h3>
          <p className="text-nav [overflow-wrap:anywhere]">{jobLabel(reply.job)}</p>
          <p className="text-caption text-muted-foreground empty:hidden">{match}</p>
        </>
      )}
    </section>
  );
}

/** Підсумок розбору: повторного розбору інтерфейс не пропонує. */
function Reviewed({ reply, type, reviewedAt }: { reply: Reply; type: ReplyType; reviewedAt: string }) {
  return (
    <section aria-label="Розбір" className="flex flex-col gap-2 rounded-lg border border-border p-4">
      <h3 className="text-nav font-semibold">Розібрано</h3>
      <div>
        <Badge data-testid="review-type" tone="success">
          {TYPE_LABELS[type]}
        </Badge>
      </div>
      <p className="text-nav [overflow-wrap:anywhere]">{reply.job === null ? "Не про подачу" : jobLabel(reply.job)}</p>
      <p className="text-caption text-muted-foreground">{`Розібрано: ${madridDay(reviewedAt)} · ${madridTime(reviewedAt)} · Мадрид`}</p>
    </section>
  );
}
