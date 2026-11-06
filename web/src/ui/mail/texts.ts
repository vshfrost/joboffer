import type { MailProblem } from "../../application/mail";

export const NOT_CONFIGURED = "Пошту не налаштовано: на сервері нема адреси скриньки застосунку.";

/** Текст проблеми операції: `again` — що користувач зможе після нового входу, `unavailable` — загальний збій. */
export function problemText(problem: MailProblem, again: string, unavailable: string): string {
  if (problem === "unauthorized") {
    return `Сесія завершилась. Увійди знову, щоб ${again}.`;
  }
  return problem === "not-configured" ? NOT_CONFIGURED : unavailable;
}
