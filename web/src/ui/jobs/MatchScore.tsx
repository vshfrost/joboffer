import { scoreText } from "../../domain/analysis";
import { cn } from "../lib/cn";

/** Оцінка відповідності: «Не оцінено» лише коли оцінки нема, 0 — валідна оцінка. Шкала 0–100 одна для всіх екранів. */
export function MatchScore({ score, className }: { score: number | null; className?: string }) {
  return (
    <div className={cn("flex flex-col gap-2", className)}>
      <p data-testid="match-score" className="tabular text-metric font-semibold">
        {scoreText(score)}
      </p>
      {score === null ? null : (
        <div aria-hidden="true" className="h-2 w-full overflow-hidden rounded-full bg-muted">
          <span className="block h-full rounded-full bg-primary" style={{ width: `${score}%` }} />
        </div>
      )}
    </div>
  );
}
