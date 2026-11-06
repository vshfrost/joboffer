import type { ReactNode } from "react";

export function PageHeading({ title, subtitle }: { title: string; subtitle?: ReactNode }) {
  return (
    <div className="mb-6">
      <h1 className="text-page-title font-semibold tracking-tight">{title}</h1>
      {subtitle === undefined ? null : <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>}
    </div>
  );
}
