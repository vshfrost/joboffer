import { Loader2 } from "lucide-react";

import { cn } from "../lib/cn";

/** Індикатор очікування: єдиний для входу, реєстрації й екрана завантаження. Декоративний — текст поруч каже, що відбувається. */
export function Spinner({ className }: { className?: string }) {
  return <Loader2 aria-hidden="true" className={cn("animate-spin", className)} />;
}
