import { ChevronDown } from "lucide-react";
import type { ComponentProps, Ref } from "react";

import { cn } from "../lib/cn";

/** Рідний `<select>` у стилі Pine: клавіатура й екранні читачі — безкоштовно, висота як у поля вводу. */
export function Select({ className, children, ref, ...props }: ComponentProps<"select"> & { ref?: Ref<HTMLSelectElement> }) {
  return (
    <div className="relative min-w-0">
      <select
        ref={ref}
        className={cn(
          "h-10 w-full appearance-none rounded-lg border border-input bg-card pr-9 pl-3 text-base text-foreground pointer-coarse:h-11",
          "disabled:bg-disabled disabled:text-disabled-foreground",
          className,
        )}
        {...props}
      >
        {children}
      </select>
      <ChevronDown aria-hidden="true" className="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-muted-foreground" />
    </div>
  );
}
