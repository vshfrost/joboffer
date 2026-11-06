import type { ComponentProps } from "react";

import { cn } from "../lib/cn";

/** Місце під вміст, що вантажиться; для читачів екрана його не існує — статус оголошує контейнер. */
export function Skeleton({ className, ...props }: ComponentProps<"div">) {
  return <div aria-hidden="true" className={cn("animate-pulse rounded-md bg-muted", className)} {...props} />;
}
