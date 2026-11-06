import { quotaText, stampText, type RefreshState } from "../../domain/sources";
import { Button } from "../components/button";

interface RefreshBarProps {
  refresh: RefreshState;
  /** Запит цього візиту вже в черзі. */
  queued: boolean;
  requesting: boolean;
  onRequest(): void;
}

/** «Оновити зараз»: ставить запит у чергу (не оновлює одразу); ліміт — 2 запити за 30 хв. */
export function RefreshBar({ refresh, queued, requesting, onRequest }: RefreshBarProps) {
  const last = queued
    ? "Запит у черзі · очікує серверного прогону"
    : refresh.lastRunAt === null
      ? "Оновлень ще не було"
      : `Остання спроба оновлення: ${stampText(refresh.lastRunAt)} (Мадрид)`;
  const exhausted = refresh.remaining === 0;
  return (
    <section aria-label="Оновлення джерел" className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex flex-col gap-0.5 text-caption text-muted-foreground">
        <p>{last}</p>
        <p>{quotaText(refresh)}</p>
        {exhausted && refresh.nextAt !== null ? <p>{`Наступний запит: ${stampText(refresh.nextAt)} (Мадрид)`}</p> : null}
      </div>
      <Button type="button" variant="secondary" disabled={queued || requesting || exhausted} onClick={onRequest}>
        {queued ? "Запит у черзі" : "Оновити зараз"}
      </Button>
    </section>
  );
}
