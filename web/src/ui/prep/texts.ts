import type { PrepProblem } from "../../application/prep";

/** Текст проблеми операції: `again` — що користувач зможе після нового входу, `unavailable` — загальний збій. */
export function problemText(problem: PrepProblem, again: string, unavailable: string): string {
  return problem === "unauthorized" ? `Сесія завершилась. Увійди знову, щоб ${again}.` : unavailable;
}
