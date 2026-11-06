/** Причини, з яких операція з джерелами не вдалась. Порт кидає їх, application перетворює на результат. */

/** Сесія завершилась (401). */
export class SourcesUnauthorizedError extends Error {}

/** Джерела чи вакансії нема або вони чужі (404): відповідь однакова. */
export class SourcesNotFoundError extends Error {}

/** Сервер відхилив нове джерело (422): тексти біля полів; `message` — загальний текст. */
export class SourcesValidationError extends Error {
  readonly fieldErrors: Readonly<Record<string, string>>;

  constructor(message: string, fieldErrors: Record<string, string>) {
    super(message);
    this.fieldErrors = fieldErrors;
  }
}

/** Ліміт «Оновити зараз» вичерпано (429); `retryAfter` — секунди з `Retry-After`, якщо сервер їх надіслав. */
export class SourcesRefreshLimitError extends Error {
  readonly retryAfter: number | null;

  constructor(message: string, retryAfter: number | null) {
    super(message);
    this.retryAfter = retryAfter;
  }
}

/** Список «Уже не проходять фільтр» змінився відтоді, як користувач його бачив (409): нічого не сховано. */
export class SourcesFilteredChangedError extends Error {}

/** Сервер недоступний, відповів помилкою чи не за контрактом. */
export class SourcesUnavailableError extends Error {}
