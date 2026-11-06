import type { ReactNode } from "react";
import { Link, useNavigate } from "react-router";

import { SECTION_LABELS, SECTION_ORDER, type ProfileSection } from "../../domain/profile";
import { cn } from "../lib/cn";
import { usePageTitle } from "../lib/usePageTitle";
import { PageHeading } from "../pages/PageHeading";
import { useProfile } from "./ProfileProvider";

/** Розділи локального меню: чотири секції профілю й галерея фото (її зберігають окремо від профілю). */
export type EditorSection = ProfileSection | "photos";
const NAV_ORDER: readonly EditorSection[] = [...SECTION_ORDER, "photos"];
const NAV_LABELS: Record<EditorSection, string> = { ...SECTION_LABELS, photos: "Фото для CV" };

const LINK = "flex min-h-10 items-center gap-2 rounded-lg px-3 py-2 text-caption transition-colors duration-140 pointer-coarse:min-h-11";

/** Редактор розділу замість огляду: локальне меню розділів і панель зі змістом. */
export function EditorLayout({ current, children }: { current: EditorSection; children: ReactNode }) {
  const label = NAV_LABELS[current];
  const { dirtySections } = useProfile();
  const navigate = useNavigate();
  usePageTitle(`${label} · Профіль`);
  return (
    <>
      <PageHeading title={label} subtitle={`Профіль / ${label}`} />
      <div className="grid gap-6 lg:grid-cols-[9.25rem_minmax(0,1fr)] lg:items-start">
        <nav aria-label="Розділи профілю" className="hidden flex-wrap gap-1 sm:flex lg:grid">
          <Link to="/profile" state={{ from: current }} className={cn(LINK, "text-primary hover:bg-accent lg:mb-4")}>
            ← Огляд профілю
          </Link>
          {NAV_ORDER.map((section) => (
            <Link
              key={section}
              to={`/profile/${section}`}
              aria-current={section === current ? "page" : undefined}
              className={cn(
                LINK,
                section === current
                  ? "bg-selected font-medium text-selected-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground",
              )}
            >
              {NAV_LABELS[section]}
              {section !== "photos" && dirtySections.includes(section) ? (
                <>
                  <span className="sr-only">, є незбережені зміни</span>
                  <span aria-hidden="true" className="ml-auto text-primary">
                    •
                  </span>
                </>
              ) : null}
            </Link>
          ))}
        </nav>
        <div className="min-w-0">
          <div className="mb-4 flex items-center gap-2 sm:hidden">
            <Link to="/profile" state={{ from: current }} className="flex h-10 items-center rounded-lg border border-border bg-card px-3 text-nav font-medium pointer-coarse:h-11">
              ← Огляд
            </Link>
            <select
              aria-label="Розділ профілю"
              value={current}
              onChange={(event) => void navigate(`/profile/${event.target.value}`)}
              className="h-10 min-w-0 flex-1 rounded-lg border border-input bg-card px-3 text-base pointer-coarse:h-11"
            >
              {NAV_ORDER.map((section) => (
                <option key={section} value={section}>
                  {NAV_LABELS[section]}
                </option>
              ))}
            </select>
          </div>
          <section aria-label={label} className="min-w-0 rounded-xl border border-border bg-card p-6 max-sm:p-4">
            {children}
          </section>
        </div>
      </div>
    </>
  );
}
