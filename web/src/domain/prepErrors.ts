/** Причини, з яких операція з підготовкою не вдалась. Порт кидає їх, application перетворює на результат. */

/** Сесія завершилась (401). */
export class PrepUnauthorizedError extends Error {}

/** Теми, кроку, вакансії чи пакета нема або вони чужі (404): відповідь однакова. */
export class PrepNotFoundError extends Error {}

/** Сервер відхилив значення (422): тексти біля полів; `message` — загальний текст. */
export class PrepValidationError extends Error {
  readonly fieldErrors: Readonly<Record<string, string>>;

  constructor(message: string, fieldErrors: Record<string, string>) {
    super(message);
    this.fieldErrors = fieldErrors;
  }
}

/** Сервер недоступний, відповів помилкою чи не за контрактом. */
export class PrepUnavailableError extends Error {}
