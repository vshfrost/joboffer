import type { KeyboardEvent, MouseEvent, ReactNode, Ref } from "react";

import { SUMMARY } from "../jobs/blockStyles";
import { cn } from "../lib/cn";

interface CollapsibleBlockProps {
  title: string;
  /** Праворуч у заголовку, видно й у згорнутому стані. */
  aside?: ReactNode;
  expanded: boolean;
  onToggle(): void;
  titleId?: string;
  /** Якщо задано, заголовок можна фокусувати програмно. */
  titleRef?: Ref<HTMLElement>;
  children: ReactNode;
}

/** Блок у картці, що згортається до заголовка. Станом керує викликач. */
export function CollapsibleBlock({ title, aside, expanded, onToggle, titleId, titleRef, children }: CollapsibleBlockProps) {
  // Згортанням керуємо самі: у jsdom і в частини браузерів Enter/Space на <summary> не перемикають <details> надійно, а aria-expanded має збігатися зі станом.
  function onClick(event: MouseEvent) {
    event.preventDefault();
    onToggle();
  }
  function onKeyDown(event: KeyboardEvent) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onToggle();
    }
  }
  function onKeyUp(event: KeyboardEvent) {
    // Пробіл спрацьовує на keydown; браузер не має додати власний клік на keyup.
    if (event.key === " ") {
      event.preventDefault();
    }
  }

  return (
    <details open={expanded} className="group min-w-0 rounded-xl border border-border bg-card">
      <summary aria-expanded={expanded} onClick={onClick} onKeyDown={onKeyDown} onKeyUp={onKeyUp} className={cn(SUMMARY, "justify-between p-4")}>
        <strong id={titleId} ref={titleRef} tabIndex={titleRef === undefined ? undefined : -1} className="text-section font-semibold outline-none">
          {title}
        </strong>
        {aside}
      </summary>
      <div className="px-4 pb-4">{children}</div>
    </details>
  );
}
