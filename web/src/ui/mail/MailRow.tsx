import { dropReasonText, itemLabel, madridDay, madridTime, senderName, subjectText, type MailItem } from "../../domain/mail";
import { Badge } from "../components/badge";
import { Tooltip, TooltipContent, TooltipTrigger } from "../components/tooltip";
import { cn } from "../lib/cn";

/** Позначка виду листа; відхилений лист має поруч підказку з причиною (при наведенні й фокусі). */
export function KindBadge({ item }: { item: MailItem }) {
  if (!item.dropped) {
    return <Badge data-testid="kind">{itemLabel(item)}</Badge>;
  }
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button type="button" aria-label="Відхилено: причина" className="rounded-md">
          <Badge data-testid="kind" tone="warning">
            {itemLabel(item)}
          </Badge>
        </button>
      </TooltipTrigger>
      <TooltipContent>{dropReasonText(item)}</TooltipContent>
    </Tooltip>
  );
}

/** Рядок «Вхідних»: відправник, час за Мадридом, тема й вид. Відправник і тема — недовірені дані. */
export function MailRow({ item, selected, onOpen }: { item: MailItem; selected: boolean; onOpen(): void }) {
  return (
    <li className={cn("rounded-lg border bg-card", selected ? "border-primary bg-selected" : "border-border")}>
      <button type="button" aria-pressed={selected} onClick={onOpen} className="flex w-full min-w-0 flex-col gap-1 rounded-lg px-3 pt-3 pb-1 text-left">
        <span className="flex items-baseline justify-between gap-3">
          <strong className="min-w-0 truncate text-nav">{senderName(item)}</strong>
          <span className="flex shrink-0 gap-2 text-caption text-muted-foreground">
            <span>{madridDay(item.receivedAt)}</span>
            <span>{madridTime(item.receivedAt)}</span>
          </span>
        </span>
        <span className="text-nav [overflow-wrap:anywhere]">{subjectText(item)}</span>
      </button>
      <div className="px-3 pt-1 pb-3">
        <KindBadge item={item} />
      </div>
    </li>
  );
}
