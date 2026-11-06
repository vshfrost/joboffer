/** Причини, з яких операція з відповідями не вдалась. Порт кидає їх, application перетворює на результат. */

/** Сесія завершилась (401). */
export class RepliesUnauthorizedError extends Error {}

/** Листа чи вакансії нема або вони чужі (404): відповідь однакова. */
export class RepliesNotFoundError extends Error {}

/** Сервер відхилив розбір (422): тексти біля полів `type` і `job_id`. */
export class RepliesValidationError extends Error {
  readonly fieldErrors: Readonly<Record<string, string>>;

  constructor(fieldErrors: Record<string, string>) {
    super("Розбір не пройшов перевірку");
    this.fieldErrors = fieldErrors;
  }
}

/** Сервер недоступний, відповів помилкою чи не за контрактом. */
export class RepliesUnavailableError extends Error {}
