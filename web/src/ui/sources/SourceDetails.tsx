import type { ReactNode } from "react";

import { madridDay, madridTime } from "../../domain/mail";
import { FAILURE_TEXT, KIND_TEXT, platformLabel, stampText, type LastRun, type Source } from "../../domain/sources";
import { Button } from "../components/button";
import { StateBadge } from "./StateBadge";

const STATS: readonly [keyof LastRun, string][] = [
  ["found", "Знайдено"],
  ["imported", "Імпортовано"],
  ["filtered", "Відсіяно"],
  ["duplicate", "Дублі"],
  ["completed", "Дописано текст"],
];

export function detailsId(source: Source): string {
  return `source-details-${source.id}`;
}

interface SourceDetailsProps {
  source: Source;
  /** Зміна стану йде: кнопка «Вимкнути» / «Увімкнути» неактивна. */
  busy: boolean;
  onToggle(): void;
  onRemove(): void;
}

/** Деталі під рядком: останній прогін або причина його збою, дії над джерелом, пояснення цифр. */
export function SourceDetails({ source, busy, onToggle, onRemove }: SourceDetailsProps) {
  return (
    <div id={detailsId(source)} className="flex min-w-0 flex-col gap-4 p-4">
      <div className="flex min-w-0 flex-col gap-1">
        <h2 className="text-section font-semibold [overflow-wrap:anywhere]">{source.name}</h2>
        <p className="text-caption text-muted-foreground">{`${platformLabel(source.platform)} · ${KIND_TEXT[source.kind]}`}</p>
        <StateBadge source={source} />
        <p className="mt-1">
          <code className="text-caption text-muted-foreground [overflow-wrap:anywhere]">{source.key}</code>
        </p>
      </div>
      <LastRunBlock source={source} />
      {source.enabled ? null : (
        <p className="text-caption text-muted-foreground">Нові прогони пропускають це джерело. Збережена статистика та імпортовані вакансії залишаються.</p>
      )}
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="secondary" disabled={busy} onClick={onToggle}>
          {source.enabled ? "Вимкнути" : "Увімкнути"}
        </Button>
        <Button type="button" variant="secondary" className="text-destructive" onClick={onRemove}>
          Видалити
        </Button>
      </div>
      <details className="text-caption text-muted-foreground">
        <summary className="cursor-pointer text-primary pointer-coarse:flex pointer-coarse:min-h-11 pointer-coarse:items-center">Як рахуються результати</summary>
        <p className="mt-2">
          Імпортовано — нові вакансії, що пройшли фільтри профілю. Дублі — вакансії, які вже є в базі. Дописано текст — раніше створені вакансії LinkedIn, до яких
          додано повний текст. Ці числа стосуються лише останнього прогону.
        </p>
      </details>
    </div>
  );
}

function LastRunBlock({ source }: { source: Source }) {
  const run = source.lastRun;
  if (run === null) {
    return <Notice>Це джерело ще не оновлювалось. Статистика з’явиться після першого прогону.</Notice>;
  }
  if (run.error !== null) {
    return (
      <Notice failure>
        <strong>{FAILURE_TEXT[run.error]}</strong>
        <br />
        {`Остання спроба: ${madridDay(run.ranAt)} · ${madridTime(run.ranAt)} (Мадрид). Інші джерела оновилися. Наступний загальний прогін повторить спробу.`}
      </Notice>
    );
  }
  return (
    <div className="flex flex-col gap-3">
      <p className="text-caption text-muted-foreground">{`Останній прогін: ${stampText(run.ranAt)} (Мадрид)`}</p>
      <dl className="sr-stats grid grid-cols-2 gap-4 sm:grid-cols-3">
        {STATS.map(([key, label]) => (
          <div key={key} className="flex min-w-0 flex-col gap-0.5">
            <dt className="text-caption text-muted-foreground">{label}</dt>
            <dd className="text-section">{run[key]}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function Notice({ failure = false, children }: { failure?: boolean; children: ReactNode }) {
  return (
    <p className={failure ? "rounded-lg bg-status-danger p-3 text-caption text-status-danger-foreground" : "rounded-lg bg-status-warning p-3 text-caption text-status-warning-foreground"}>
      {children}
    </p>
  );
}
