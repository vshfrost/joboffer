import type { ComponentProps, Ref } from "react";

import { cn } from "../lib/cn";

/** Багаторядкове поле: межа `--input`, помилка — червона межа (разом із текстом помилки, не замість нього). */
export function Textarea({ className, ref, ...props }: ComponentProps<"textarea"> & { ref?: Ref<HTMLTextAreaElement> }) {
  return (
    <textarea
      ref={ref}
      className={cn(
        "min-h-24 w-full resize-y rounded-lg border border-input bg-card px-3 py-2 text-base text-foreground",
        "placeholder:text-muted-foreground aria-invalid:border-destructive disabled:bg-disabled disabled:text-disabled-foreground",
        className,
      )}
      {...props}
    />
  );
}
