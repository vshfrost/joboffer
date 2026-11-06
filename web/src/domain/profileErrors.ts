/** Причини, з яких профіль не завантажився чи не зберігся. Порт кидає їх, application перетворює на результат. */

/** Сервер відхилив значення (422): тексти біля полів. */
export class ProfileValidationError extends Error {
  readonly fieldErrors: Readonly<Record<string, string>>;

  constructor(fieldErrors: Record<string, string>) {
    super("Профіль не пройшов перевірку");
    this.fieldErrors = fieldErrors;
  }
}

/** Сервер недоступний, відповів помилкою чи не за контрактом. */
export class ProfileUnavailableError extends Error {}
