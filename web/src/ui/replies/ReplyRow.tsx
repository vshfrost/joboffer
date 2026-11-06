import { madridDay, madridTime, senderName, subjectText } from "../../domain/mail";
import { jobTag, replyStatusLabel, type Reply } from "../../domain/replies";
import { Badge } from "../components/badge";
import { cn } from "../lib/cn";

/** Рядок черги: відправник, час за Мадридом, тема, стан і вакансія. Відправник і тема — недовірені дані. */
export function ReplyRow({ reply, selected, onOpen }: { reply: Reply; selected: boolean; onOpen(): void }) {
  return (
    <li className={cn("rounded-lg border bg-card", selected ? "border-primary bg-selected" : "border-border")}>
      <button type="button" aria-pressed={selected} onClick={onOpen} className="flex w-full min-w-0 flex-col gap-1 rounded-lg px-3 pt-3 pb-1 text-left">
        <span className="flex items-baseline justify-between gap-3">
          <strong className="min-w-0 truncate text-nav">{senderName(reply)}</strong>
          <span className="flex shrink-0 gap-2 text-caption text-muted-foreground">
            <span>{madridDay(reply.receivedAt)}</span>
            <span>{madridTime(reply.receivedAt)}</span>
          </span>
        </span>
        <span className="text-nav [overflow-wrap:anywhere]">{subjectText(reply)}</span>
      </button>
      <div className="flex flex-wrap gap-2 px-3 pt-1 pb-3">
        <Badge data-testid="status" tone={reply.type === null ? "warning" : "neutral"}>
          {replyStatusLabel(reply)}
        </Badge>
        {reply.manualForward === null ? null : <Badge tone="warning">Переслано вручну</Badge>}
        {reply.job === null ? null : <Badge tone="success">{jobTag(reply.job)}</Badge>}
      </div>
    </li>
  );
}
