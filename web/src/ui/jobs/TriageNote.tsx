import { TRIAGE_SOURCE_NOTES, VERDICT_LABELS, type Triage } from "../../domain/analysis";

const WRAP = "[overflow-wrap:anywhere]";

/** Попередній тріаж — окремо від повного аналізу, згорнутий; розкривається нативним details/summary (клавіатура безкоштовна). */
export function TriageNote({ triage }: { triage: Triage }) {
  return (
    <details className="max-w-prose rounded-lg border border-border bg-card px-4 py-3">
      <summary className="cursor-pointer text-nav font-medium">{`Попередній тріаж: ${triage.score}/100 · ${VERDICT_LABELS[triage.verdict]}`}</summary>
      <p className={`mt-3 text-sm ${WRAP}`}>{triage.reason}</p>
      <p className="mt-2 text-caption text-muted-foreground">{TRIAGE_SOURCE_NOTES[triage.source]}</p>
      <p className="mt-2 text-caption text-muted-foreground">
        Це окремий результат швидкого відбору, не повний аналіз. Вердикт не приховує вакансію.
      </p>
    </details>
  );
}
