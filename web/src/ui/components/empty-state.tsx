import type { ReactNode } from "react";

import { cn } from "../lib/cn";

interface EmptyStateProps {
  title: string;
  hint?: string;
  /** Що можна зробити далі (кнопка). */
  action?: ReactNode;
  className?: string;
}

/** Порожній стан: що саме порожньо і що буде далі. */
export function EmptyState({ title, hint, action, className }: EmptyStateProps) {
  return (
    <div className={cn("rounded-xl border border-border bg-card px-4 py-16 text-center", className)}>
      <p className="text-section font-semibold">{title}</p>
      {hint === undefined ? null : <p className="mx-auto mt-2 max-w-md text-caption text-muted-foreground">{hint}</p>}
      {action === undefined ? null : <div className="mt-4">{action}</div>}
    </div>
  );
}
