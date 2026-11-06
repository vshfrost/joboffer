import { ChevronRight } from "lucide-react";
import { useId, useState, type ReactNode } from "react";

import { cn } from "../lib/cn";

interface DisclosureProps {
  /** Текст кнопки-заголовка; зміст показується лише розкритим. */
  label: string;
  children: ReactNode;
  className?: string;
}

/** Розкривний блок: кнопка з `aria-expanded` — відкривається клавіатурою (Enter, пробіл) і читається скрінрідером. */
export function Disclosure({ label, children, className }: DisclosureProps) {
  const [open, setOpen] = useState(false);
  const panel = useId();
  return (
    <div className={cn("min-w-0", className)}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={open ? panel : undefined}
        onClick={() => setOpen((current) => !current)}
        className="inline-flex cursor-pointer items-center gap-1 rounded-sm py-2 text-left text-caption font-medium text-primary"
      >
        <ChevronRight aria-hidden="true" className={cn("size-4 shrink-0 transition-transform duration-140", open && "rotate-90")} />
        {label}
      </button>
      {open ? <div id={panel}>{children}</div> : null}
    </div>
  );
}
