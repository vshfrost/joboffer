/** Причини, з яких вакансії не завантажились чи дія не вдалась. Порт кидає їх, application перетворює на результат. */

/** Сервер відхилив значення (422): тексти біля полів. */
export class JobsValidationError extends Error {
  readonly fieldErrors: Readonly<Record<string, string>>;

  constructor(fieldErrors: Record<string, string>) {
    super("Вакансії не пройшли перевірку");
    this.fieldErrors = fieldErrors;
  }
}

/** Вакансії нема або вона чужа (404): відповідь однакова. */
export class JobNotFoundError extends Error {}

/** Сервер недоступний, відповів помилкою чи не за контрактом. */
export class JobsUnavailableError extends Error {}

/** Вакансію ще не аналізовано (404 від `/jobs/{id}/analysis`): це стан даних, не збій. */
export class AnalysisNotFoundError extends Error {}

/** На вакансію вже є подача (409): поданих вакансій не ховають. */
export class JobAppliedError extends Error {}
