/** Причини, з яких факти не завантажились чи дія не вдалась. Порт кидає їх, application перетворює на результат. */

/** Сервер відхилив значення (422): тексти біля полів і загальний текст. */
export class FactsValidationError extends Error {
  readonly fieldErrors: Readonly<Record<string, string>>;

  constructor(message: string, fieldErrors: Record<string, string>) {
    super(message);
    this.fieldErrors = fieldErrors;
  }
}

/** Такий текст уже є в іншому факті (409). */
export class FactsConflictError extends Error {}

/** Факту нема або він чужий (404): відповідь однакова. */
export class FactNotFoundError extends Error {}

/** Сервер недоступний, відповів помилкою чи не за контрактом. */
export class FactsUnavailableError extends Error {}
