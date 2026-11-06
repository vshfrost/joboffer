import { useId, type ReactNode } from "react";

import { cn } from "../lib/cn";

export interface FieldControlProps {
  id: string;
  "aria-describedby": string | undefined;
  "aria-invalid": true | undefined;
}

interface FieldProps {
  label: string;
  hint?: string | undefined;
  error?: string | undefined;
  className?: string | undefined;
  /** Рендерить сам елемент керування з потрібними id та aria. */
  children: (props: FieldControlProps) => ReactNode;
}

/** Підпис над полем, підказка й текст помилки під ним; усе повʼязано з полем через id та aria. */
export function Field({ label, hint, error, className, children }: FieldProps) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy = [hint === undefined ? null : hintId, error === undefined ? null : errorId].filter((value) => value !== null);
  return (
    <div className={cn("flex min-w-0 flex-col gap-1.5", className)}>
      <label htmlFor={id} className="text-nav font-medium">
        {label}
      </label>
      {children({ id, "aria-describedby": describedBy.length === 0 ? undefined : describedBy.join(" "), "aria-invalid": error === undefined ? undefined : true })}
      {hint === undefined ? null : (
        <p id={hintId} className="text-caption text-muted-foreground">
          {hint}
        </p>
      )}
      {error === undefined ? null : (
        <p id={errorId} className="text-caption font-medium text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}
