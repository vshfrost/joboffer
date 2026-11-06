/** Короткі підсумки розділів для карток огляду. Порожній розділ — окремий стан, а не «0». */
import type { Contacts, Locations, Rules, Seniority, Target, WorkMode } from "./profile";

export interface Summary {
  /** Розділ не заповнений. */
  empty: boolean;
  lines: string[];
}

const MODE_LABELS: Record<WorkMode, string> = { remote: "Remote", hybrid: "Hybrid", onsite: "Офіс" };
const LEVEL_LABELS: Record<Seniority, string> = {
  junior: "Junior",
  middle: "Middle",
  senior: "Senior",
  lead: "Lead",
  principal: "Principal",
};
const VISIBLE_ITEMS = 2;

export function modeLabel(mode: WorkMode): string {
  return MODE_LABELS[mode];
}

export function levelLabel(level: Seniority): string {
  return LEVEL_LABELS[level];
}

/** Українська множина: 1 слово, 2 слова, 5 слів (11–14 — завжди «слів»). */
export function plural(count: number, one: string, few: string, many: string): string {
  const lastTwo = count % 100;
  const last = count % 10;
  if (lastTwo >= 11 && lastTwo <= 14) {
    return many;
  }
  if (last === 1) {
    return one;
  }
  return last >= 2 && last <= 4 ? few : many;
}

/** «65 000»: звичайний пробіл між тисячами, однаково в усіх середовищах. */
export function groupThousands(value: number): string {
  return String(value).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
}

/** Перші елементи через « · » і «ще N» для решти. */
function brief(items: string[], separator: string): string {
  const shown = items.slice(0, VISIBLE_ITEMS).join(separator);
  const rest = items.length - VISIBLE_ITEMS;
  return rest > 0 ? `${shown}${separator}ще ${rest}` : shown;
}

export function summarizeTarget(target: Target): Summary {
  const level = target.seniority.map(levelLabel).join(", ");
  const salary = target.minSalaryEur === null ? "" : `від ${groupThousands(target.minSalaryEur)} € брутто / рік`;
  const details = [level, salary].filter((part) => part !== "").join(" · ");
  const lines = [brief(target.roles, " · "), details].filter((line) => line !== "");
  return lines.length === 0 ? { empty: true, lines: ["Ціль ще не задано"] } : { empty: false, lines };
}

export function summarizeLocations(locations: Locations): Summary {
  if (locations.locations.length === 0) {
    return { empty: true, lines: ["Локації ще не додано"] };
  }
  const places = locations.locations.map(
    (location) => `${location.place} · ${location.workModes.map(modeLabel).join(", ")}`,
  );
  return { empty: false, lines: [brief(places, " / ")] };
}

export function summarizeRules(rules: Rules): Summary {
  const keywords = rules.titleKeywords.length;
  const excluded = rules.titleExclude.length;
  const stops = rules.stopWords.length;
  if (keywords + excluded + stops === 0) {
    return { empty: true, lines: ["Правила ще не задано"] };
  }
  const parts = [
    `${keywords} ${plural(keywords, "слово", "слова", "слів")} для пошуку`,
    `${excluded} ${plural(excluded, "виключення", "виключення", "виключень")}`,
    `${stops} ${plural(stops, "стоп-слово", "стоп-слова", "стоп-слів")}`,
  ];
  return { empty: false, lines: [parts.join(" · ")] };
}

export function summarizeContacts(contacts: Contacts): Summary {
  const lines = [contacts.fullName, contacts.email].filter((line) => line !== "");
  return lines.length === 0 ? { empty: true, lines: ["Контакти не вказано"] } : { empty: false, lines };
}
