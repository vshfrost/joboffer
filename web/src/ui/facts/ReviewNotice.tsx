import { pendingSummary, type FactCounts } from "../../domain/facts";
import { Button } from "../components/button";

/** Компактний блок «N на перевірці»: скільки фактів ще не потрапить у CV і перехід до них. */
export function ReviewNotice({ counts, onReview }: { counts: FactCounts; onReview(): void }) {
  return (
    <section aria-label="Перевірка фактів" className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3">
      {counts.pending === 0 ? (
        <p className="text-nav font-medium">Усі факти перевірено</p>
      ) : (
        <>
          <div>
            <p className="text-nav font-medium">{pendingSummary(counts.pending)}</p>
            <p className="text-caption text-muted-foreground">Решта {counts.confirmed} готові для CV</p>
          </div>
          <Button variant="secondary" onClick={onReview}>
            Переглянути
          </Button>
        </>
      )}
    </section>
  );
}
