/** Чернетка «Кар’єрної цілі»: рядки з полів форми ↔ значення розділу. Контакти — самі рядки, перетворення не потребують. */
import {
  SENIORITIES,
  WORK_MODES,
  type FieldErrors,
  type Locations,
  type Rules,
  type Seniority,
  type Target,
  type WorkMode,
} from "./profile";

/** Значення полів «Кар’єрної цілі» так, як вони в формі. */
export interface TargetForm {
  /** Ролі: по одній на рядок. */
  roles: string;
  seniority: Seniority[];
  /** Мінімальна зарплата як її ввів користувач: допустимі пробіли й підкреслення. */
  minSalary: string;
  /** Галузі: по одній на рядок. */
  targetDomains: string;
}

export type FormParse<T> = { ok: true; value: T } | { ok: false; errors: FieldErrors };

export const SALARY_ERROR = "Мінімальна зарплата — ціле число в EUR, напр. 60000.";

/** Рядки багаторядкового поля: без пробілів по краях і без порожніх (повтори прибирає сервер). */
export function linesOf(text: string): string[] {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line !== "");
}

export function targetToForm(target: Target): TargetForm {
  return {
    roles: target.roles.join("\n"),
    seniority: SENIORITIES.filter((level) => target.seniority.includes(level)),
    minSalary: target.minSalaryEur === null ? "" : String(target.minSalaryEur),
    targetDomains: target.targetDomains.join("\n"),
  };
}

/** Річна брутто-зарплата в EUR; пробіли й підкреслення — роздільники тисяч. `undefined` — не ціле число. */
function parseSalary(text: string): number | null | undefined {
  const cleaned = text.replace(/[\s_]/g, "");
  if (cleaned === "") {
    return null;
  }
  const value = /^\d+$/.test(cleaned) ? Number(cleaned) : Number.NaN;
  return Number.isSafeInteger(value) ? value : undefined;
}

export function formToTarget(form: TargetForm): FormParse<Target> {
  const minSalaryEur = parseSalary(form.minSalary);
  if (minSalaryEur === undefined) {
    return { ok: false, errors: { min_salary_eur: SALARY_ERROR } };
  }
  return {
    ok: true,
    value: {
      roles: linesOf(form.roles),
      seniority: SENIORITIES.filter((level) => form.seniority.includes(level)),
      minSalaryEur,
      targetDomains: linesOf(form.targetDomains),
    },
  };
}

/** Рядок локації у формі. `key` — стабільна ідентичність рядка для React і фокусу, не дані профілю. */
export interface LocationRowForm {
  key: string;
  place: string;
  /** Синоніми: по одному на рядок. */
  aliases: string;
  workModes: WorkMode[];
}

export interface LocationsForm {
  workModes: WorkMode[];
  rows: LocationRowForm[];
  includeUnknownMode: boolean;
  relocation: boolean;
}

/** Правила відбору у формі: три списки, по одному слову на рядок. */
export interface RulesForm {
  titleKeywords: string;
  titleExclude: string;
  stopWords: string;
}

export function locationsToForm(locations: Locations): LocationsForm {
  return {
    workModes: orderedModes(locations.workModes),
    rows: locations.locations.map((location, index) => ({
      key: `saved-${index}`,
      place: location.place,
      aliases: location.aliases.join("\n"),
      workModes: orderedModes(location.workModes),
    })),
    includeUnknownMode: locations.includeUnknownMode,
    relocation: locations.relocation,
  };
}

function orderedModes(modes: WorkMode[]): WorkMode[] {
  return WORK_MODES.filter((mode) => modes.includes(mode));
}

/** Усі рядки йдуть на сервер як є (і порожні): індекс у помилці сервера збігається з рядком форми. */
export function formToLocations(form: LocationsForm): Locations {
  return {
    workModes: orderedModes(form.workModes),
    locations: form.rows.map((row) => ({
      place: row.place,
      aliases: linesOf(row.aliases),
      workModes: orderedModes(row.workModes),
    })),
    includeUnknownMode: form.includeUnknownMode,
    relocation: form.relocation,
  };
}

export function newLocationRow(key: string): LocationRowForm {
  return { key, place: "", aliases: "", workModes: [] };
}

export function rulesToForm(rules: Rules): RulesForm {
  return {
    titleKeywords: rules.titleKeywords.join("\n"),
    titleExclude: rules.titleExclude.join("\n"),
    stopWords: rules.stopWords.join("\n"),
  };
}

export function formToRules(form: RulesForm): Rules {
  return {
    titleKeywords: linesOf(form.titleKeywords),
    titleExclude: linesOf(form.titleExclude),
    stopWords: linesOf(form.stopWords),
  };
}

/** Скільки слів збереже сервер: без порожніх рядків і повторів (без урахування регістру). */
export function uniqueCount(text: string): number {
  return new Set(linesOf(text).map((line) => line.toLowerCase())).size;
}
