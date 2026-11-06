/** Причини, з яких вхід чи вихід не вдався. Порт кидає їх, application перетворює на результат. */

export class InvalidCredentialsError extends Error {}

export class TooManyAttemptsError extends Error {
  readonly retryAfterSeconds: number;

  constructor(retryAfterSeconds: number) {
    super("Забагато спроб входу");
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

/** Сервер недоступний або відповів не за контрактом. */
export class ServiceUnavailableError extends Error {}
