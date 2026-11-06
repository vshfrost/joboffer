import { Popover as PopoverPrimitive } from "radix-ui";
import type { ComponentProps } from "react";

import { cn } from "../lib/cn";
import { useMediaQuery } from "../lib/useMediaQuery";

export const Popover = PopoverPrimitive.Root;
export const PopoverTrigger = PopoverPrimitive.Trigger;
export const PopoverClose = PopoverPrimitive.Close;

const WIDE = "(min-width: 40rem)";

/**
 * Підказка біля елемента: не модальна, закривається Escape і кліком поза нею, фокус повертається на тригер.
 * На вузькому екрані (< 40rem) — картка внизу екрана: позицію обгортки Radix для `data-layout="bottom-card"` задає theme.css.
 */
export function PopoverContent({ className, children, ...props }: ComponentProps<typeof PopoverPrimitive.Content>) {
  const anchored = useMediaQuery(WIDE, true);
  return (
    <PopoverPrimitive.Portal>
      <PopoverPrimitive.Content
        data-layout={anchored ? "anchored" : "bottom-card"}
        sideOffset={8}
        collisionPadding={16}
        className={cn(
          "z-50 w-80 max-w-[calc(100vw-2rem)] animate-overlay-in rounded-xl border border-border bg-popover p-4 text-popover-foreground shadow-overlay",
          "data-[layout=bottom-card]:w-full data-[layout=bottom-card]:max-w-none",
          className,
        )}
        {...props}
      >
        {children}
      </PopoverPrimitive.Content>
    </PopoverPrimitive.Portal>
  );
}
