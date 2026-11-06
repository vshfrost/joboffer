import type { ComponentProps, Ref } from "react";

import { cn } from "../lib/cn";

/** Поле вводу: 40 px (44 px на touch), межа `--input`, focus-контур — глобальний. */
export function Input({ className, ref, ...props }: ComponentProps<"input"> & { ref?: Ref<HTMLInputElement> }) {
  return (
    <input
      ref={ref}
      className={cn(
        "h-10 w-full rounded-lg border border-input bg-card px-3 text-base text-foreground pointer-coarse:h-11",
        "placeholder:text-muted-foreground disabled:bg-disabled disabled:text-disabled-foreground",
        className,
      )}
      {...props}
    />
  );
}
