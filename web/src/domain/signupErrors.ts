/** Причини, з яких реєстрація не вдалася. Порт кидає їх, application перетворює на результат. */

/** Запрошення невідоме, прострочене чи використане (сервер їх не розрізняє). */
export class InviteInvalidError extends Error {}

/** Розв'язок ALTCHA не прийнято. */
export class ChallengeFailedError extends Error {}

/** Сервер відхилив поля форми (422): що не так і з яким полем. */
export class FieldsRejectedError extends Error {
  readonly problems: readonly FieldProblem[];

  constructor(problems: readonly FieldProblem[]) {
    super("Поля реєстрації відхилено");
    this.problems = problems;
  }
}

export interface FieldProblem {
  /** Імʼя поля в API (`email`, `password`…); порожнє, коли помилка стосується всієї форми. */
  field: string;
  message: string;
}

/** Лист із кодом не надіслано. */
export class MailUnavailableError extends Error {}

/** Код не підійшов; `attemptsLeft` — скільки спроб ще лишилось, якщо сервер це повідомив. */
export class CodeIncorrectError extends Error {
  readonly attemptsLeft: number | null;

  constructor(attemptsLeft: number | null) {
    super("Невірний код");
    this.attemptsLeft = attemptsLeft;
  }
}

/** Запит на реєстрацію невідомий, прострочений або вичерпав спроби коду. */
export class SignupExpiredError extends Error {}

/** Запрошення погасили, поки очікували код. */
export class InviteUsedError extends Error {}
