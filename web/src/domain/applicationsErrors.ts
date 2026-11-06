/** Причини, з яких подача не завантажилась чи дія не вдалась. Порт кидає їх, application перетворює на результат. */

/** Сервер відхилив значення (422): тексти біля полів. */
export class ApplicationsValidationError extends Error {
  readonly fieldErrors: Readonly<Record<string, string>>;

  constructor(fieldErrors: Record<string, string>) {
    super("Подача не пройшла перевірку");
    this.fieldErrors = fieldErrors;
  }
}

/** Вакансії або подачі нема чи вони чужі (404): відповідь однакова. */
export class ApplicationNotFoundError extends Error {}

/** Сервер недоступний, відповів помилкою чи не за контрактом. */
export class ApplicationsUnavailableError extends Error {}
