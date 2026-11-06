import { ChevronRight } from "lucide-react";
import { useId, type ReactNode } from "react";

import { cn } from "../lib/cn";

interface RevealProps {
  label: string;
  open: boolean;
  onToggle(): void;
  children: ReactNode;
  className?: string;
}

/** Керований розкривний блок: кнопка з `aria-expanded`, клавіатура (Enter, пробіл) — безкоштовно. */
export function Reveal({ label, open, onToggle, children, className }: RevealProps) {
  const panel = useId();
  return (
    <div className={cn("min-w-0", className)}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={open ? panel : undefined}
        onClick={onToggle}
        className="inline-flex cursor-pointer items-center gap-1 rounded-sm py-2 text-left text-caption font-medium text-primary"
      >
        <ChevronRight aria-hidden="true" className={cn("size-4 shrink-0 transition-transform duration-140", open && "rotate-90")} />
        {label}
      </button>
      {open ? <div id={panel}>{children}</div> : null}
    </div>
  );
}
