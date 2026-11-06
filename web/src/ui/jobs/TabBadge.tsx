import type { JobsTab, JobTabCounts } from "../../domain/jobs";
import { plural } from "../../domain/profileSummary";
import { cn } from "../lib/cn";

const CORNER = "pointer-events-none absolute -top-2 -right-1 inline-flex h-5 min-w-5 items-center justify-center rounded-full border-2 border-background px-1 text-caption leading-none font-semibold";

/** Бейдж у правому верхньому куті таба: салатовий лічильник «У процесі», лічильник уваги на «Подано», стриманий «!» на «Потрібен текст». Нуль чи false — нічого. */
export function TabBadge({ tab, counts }: { tab: JobsTab; counts: JobTabCounts }) {
  if (tab === "in-progress" && counts.inProgress > 0) {
    const label = `${counts.inProgress} ${plural(counts.inProgress, "вакансія", "вакансії", "вакансій")} у процесі`;
    return (
      <span role="img" aria-label={label} className={cn(CORNER, "tabular bg-counter text-counter-foreground")}>
        {counts.inProgress}
      </span>
    );
  }
  if (tab === "applied" && counts.appliedUnreviewed > 0) {
    const label = `${counts.appliedUnreviewed} ${plural(counts.appliedUnreviewed, "вакансія", "вакансії", "вакансій")} з нерозібраними листами`;
    return (
      <span role="img" aria-label={label} className={cn(CORNER, "tabular bg-status-warning text-status-warning-foreground")}>
        {counts.appliedUnreviewed}
      </span>
    );
  }
  if (tab === "needs-text" && counts.needsText) {
    return <Attention label="Потребує уваги: є вакансії без тексту" />;
  }
  return null;
}

function Attention({ label }: { label: string }) {
  return (
    <span role="img" aria-label={label} className={cn(CORNER, "bg-status-warning text-status-warning-foreground")}>
      !
    </span>
  );
}
