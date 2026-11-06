import type { LucideIcon } from "lucide-react";
import { Link, NavLink } from "react-router";

import { cn } from "../lib/cn";
import { SECTIONS } from "../navigation";

const COUNTER_MAX = 99;
const PLURALS = new Intl.PluralRules("uk");
const NEW_FORMS: Record<string, string> = { one: "нова", few: "нові", many: "нових", other: "нових" };

export interface NavItemProps {
  to: string;
  label: string;
  icon: LucideIcon;
  /** Кількість нових елементів; без значення або 0 лічильника нема. */
  count?: number;
  onNavigate?: () => void;
  /** Завжди розгорнутий вигляд (меню на вузьких екранах); інакше іконки до lg, повний пункт від lg. */
  expanded?: boolean;
}

/** Пункт навігації. Назву задає `aria-label`, бо в компактній навігації текст приховано. */
export function NavItem({ to, label, icon: Icon, count = 0, onNavigate, expanded = false }: NavItemProps) {
  const hasCount = count > 0;
  const accessibleName = hasCount ? `${label}: ${count} ${NEW_FORMS[PLURALS.select(count)]}` : label;
  return (
    <NavLink
      to={to}
      aria-label={accessibleName}
      {...(onNavigate === undefined ? {} : { onClick: onNavigate })}
      className={({ isActive }) =>
        cn(
          "relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-nav transition-colors duration-140",
          "pointer-coarse:min-h-11",
          expanded ? "justify-start" : "justify-center lg:justify-start",
          isActive
            ? "bg-sidebar-accent font-semibold text-sidebar-accent-foreground"
            : "text-muted-foreground hover:bg-sidebar-accent",
        )
      }
    >
      <Icon aria-hidden="true" className="size-[18px] shrink-0" />
      <span className={expanded ? "inline" : "hidden lg:inline"}>{label}</span>
      {hasCount ? (
        <span
          className={cn(
            "tabular rounded-md bg-counter px-1.5 text-caption font-semibold text-counter-foreground",
            expanded ? "ml-auto" : "absolute -top-0.5 -right-0.5 lg:static lg:ml-auto",
          )}
        >
          {count > COUNTER_MAX ? `${COUNTER_MAX}+` : count}
        </span>
      ) : null}
    </NavLink>
  );
}

export function Brand({ onNavigate, expanded = false }: { onNavigate?: () => void; expanded?: boolean }) {
  return (
    <Link
      to="/"
      aria-label="joboffer"
      {...(onNavigate === undefined ? {} : { onClick: onNavigate })}
      className={cn("flex items-center gap-2.5 rounded-lg px-2", expanded ? "justify-start" : "justify-center lg:justify-start")}
    >
      <img src={`${import.meta.env.BASE_URL}brand/logo.svg`} alt="" width={28} height={28} className="size-7" />
      <span className={cn("text-xl font-semibold tracking-tight", expanded ? "inline" : "hidden lg:inline")}>joboffer</span>
    </Link>
  );
}

/** Лічильники нових елементів підставить реальне джерело даних; доти пункти без чисел. */
export function SidebarNav({ onNavigate, expanded = false }: { onNavigate?: () => void; expanded?: boolean }) {
  const items = (group: "main" | "settings") =>
    SECTIONS.filter((section) => section.group === group).map((section) => (
      <NavItem
        key={section.to}
        to={section.to}
        label={section.label}
        icon={section.icon}
        expanded={expanded}
        {...(onNavigate === undefined ? {} : { onNavigate })}
      />
    ));
  return (
    <nav aria-label="Головна навігація" className="flex flex-col gap-1">
      {items("main")}
      <p
        className={cn(
          "px-3 pt-6 pb-2 text-caption font-medium tracking-wider text-muted-foreground uppercase",
          expanded ? "block" : "hidden lg:block",
        )}
      >
        Налаштування
      </p>
      <hr className={cn("my-3 border-sidebar-border", expanded ? "hidden" : "lg:hidden")} />
      {items("settings")}
    </nav>
  );
}

/** Бічна навігація: 192 px на широких екранах, 64 px (лише іконки) на середніх; на вузьких — меню. */
export function Sidebar() {
  return (
    <aside className="sticky top-0 hidden h-dvh w-16 shrink-0 flex-col gap-8 border-r border-sidebar-border bg-sidebar px-2 py-6 md:flex lg:w-48 lg:px-4">
      <Brand />
      <SidebarNav />
    </aside>
  );
}
