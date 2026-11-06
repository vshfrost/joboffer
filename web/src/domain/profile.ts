/** Профіль пошуку роботи: чотири розділи, кожен зберігається окремо. Значення збігаються з API (`/api/profile`). */

export type WorkMode = "remote" | "hybrid" | "onsite";
export type Seniority = "junior" | "middle" | "senior" | "lead" | "principal";

export const WORK_MODES: readonly WorkMode[] = ["remote", "hybrid", "onsite"];
export const SENIORITIES: readonly Seniority[] = ["junior", "middle", "senior", "lead", "principal"];

export interface Target {
  roles: string[];
  seniority: Seniority[];
  /** Річна брутто-зарплата в EUR; `null` — не вказано. */
  minSalaryEur: number | null;
  targetDomains: string[];
}

export interface SearchLocation {
  place: string;
  aliases: string[];
  workModes: WorkMode[];
}

export interface Locations {
  workModes: WorkMode[];
  locations: SearchLocation[];
  includeUnknownMode: boolean;
  relocation: boolean;
}

export interface Rules {
  titleKeywords: string[];
  titleExclude: string[];
  stopWords: string[];
}

export interface Contacts {
  fullName: string;
  email: string;
  phone: string;
  linkedinUrl: string;
  city: string;
  githubUrl: string;
  workAuthorization: string;
}

export interface Profile {
  target: Target;
  locations: Locations;
  rules: Rules;
  contacts: Contacts;
}

export type ProfileSection = keyof Profile;

export const SECTION_LABELS: Record<ProfileSection, string> = {
  target: "Кар’єрна ціль",
  locations: "Локації та формат",
  rules: "Правила відбору",
  contacts: "Контакти для CV",
};

export const SECTION_ORDER: readonly ProfileSection[] = ["target", "locations", "rules", "contacts"];

/** Помилки полів за шляхом поля з сервера (`min_salary_eur`, `locations.1.place`). */
export type FieldErrors = Record<string, string>;
