import { BookOpen, BriefcaseBusiness, Inbox, Layers, Radio, SlidersHorizontal, type LucideIcon } from "lucide-react";

export const HOME = "/vacancies";
export const FACTS = "/facts";
export const REPLIES = "/replies";
export const PREP = "/prep";
export const SOURCES = "/sources";
export const PROFILE = "/profile";

export interface Section {
  to: string;
  label: string;
  icon: LucideIcon;
  group: "main" | "settings";
}

/** Розділи застосунку в порядку навігації; перший — стартовий. */
export const SECTIONS: readonly Section[] = [
  { to: "/vacancies", label: "Вакансії", icon: BriefcaseBusiness, group: "main" },
  { to: FACTS, label: "Факти", icon: Layers, group: "main" },
  { to: REPLIES, label: "Відповіді", icon: Inbox, group: "main" },
  { to: PREP, label: "Підготовка", icon: BookOpen, group: "main" },
  { to: SOURCES, label: "Джерела", icon: Radio, group: "settings" },
  { to: PROFILE, label: "Профіль", icon: SlidersHorizontal, group: "settings" },
];


export function sectionFor(pathname: string): Section | undefined {
  return SECTIONS.find(({ to }) => pathname === to || pathname.startsWith(`${to}/`));
}
