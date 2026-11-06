import { Tooltip as TooltipPrimitive } from "radix-ui";
import type { ComponentProps } from "react";

import { cn } from "../lib/cn";

export const TooltipProvider = TooltipPrimitive.Provider;
export const Tooltip = TooltipPrimitive.Root;
export const TooltipTrigger = TooltipPrimitive.Trigger;

/** Підказка поруч із елементом: з'являється при наведенні й фокусі, не перехоплює фокус. */
export function TooltipContent({ className, ...props }: ComponentProps<typeof TooltipPrimitive.Content>) {
  return (
    <TooltipPrimitive.Portal>
      <TooltipPrimitive.Content
        sideOffset={6}
        className={cn("z-50 max-w-72 rounded-lg bg-foreground px-3 py-2 text-caption text-background shadow-overlay", className)}
        {...props}
      />
    </TooltipPrimitive.Portal>
  );
}
