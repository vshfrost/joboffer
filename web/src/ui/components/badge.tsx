import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";

import { cn } from "../lib/cn";

const badgeVariants = cva("inline-flex w-fit items-center rounded-md px-2 py-0.5 text-caption font-medium whitespace-nowrap", {
  variants: {
    tone: {
      neutral: "bg-status-neutral text-status-neutral-foreground",
      info: "bg-status-info text-status-info-foreground",
      warning: "bg-status-warning text-status-warning-foreground",
      success: "bg-status-success text-status-success-foreground",
      danger: "bg-status-danger text-status-danger-foreground",
    },
  },
  defaultVariants: { tone: "neutral" },
});

/** Позначка зі статусною парою «текст + фон»: зміст завжди в тексті, колір його лише підсилює. */
export function Badge({ className, tone, ...props }: ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}
