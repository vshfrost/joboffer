import { FACT_KINDS, KIND_LABELS, type FactCounts, type FactKind } from "../../domain/facts";
import { cn } from "../lib/cn";

interface CategoryNavProps {
  counts: FactCounts;
  value: FactKind | null;
  onChange(kind: FactKind | null): void;
}

/** Категорії з лічильниками: стовпчик ліворуч, на вузькому екрані — компактні кнопки в кілька рядків. */
export function CategoryNav({ counts, value, onChange }: CategoryNavProps) {
  const entries = [
    { kind: null, label: "Усі", total: counts.total },
    ...FACT_KINDS.map((kind, index) => ({ kind, label: KIND_LABELS[kind], total: counts.kinds[index]?.total ?? 0 })),
  ];
  return (
    <nav aria-label="Категорії фактів" className="flex flex-wrap gap-2 lg:sticky lg:top-4 lg:flex-col lg:gap-1 lg:self-start">
      {entries.map(({ kind, label, total }) => (
        <button
          key={label}
          type="button"
          aria-pressed={value === kind}
          aria-label={`${label} ${total}`}
          onClick={() => onChange(kind)}
          className={cn(
            "flex min-h-8 items-center justify-between gap-3 rounded-lg px-3 py-1.5 text-nav font-medium transition-colors duration-140 pointer-coarse:min-h-11",
            "border border-border bg-card hover:bg-accent lg:border-transparent lg:bg-transparent",
            "aria-pressed:border-transparent aria-pressed:bg-selected aria-pressed:text-selected-foreground",
          )}
        >
          <span>{label}</span>
          <span className="text-caption text-muted-foreground tabular-nums">{total}</span>
        </button>
      ))}
    </nav>
  );
}
