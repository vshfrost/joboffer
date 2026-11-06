/** Причини, з яких операція з поштою не вдалась. Порт кидає їх, application перетворює на результат. */

/** Сесія завершилась (401). */
export class MailUnauthorizedError extends Error {}

/** Пошту не налаштовано: на сервері нема адреси скриньки застосунку (503). */
export class MailNotConfiguredError extends Error {}

/** Листа нема або він чужий (404): відповідь однакова. */
export class MailNotFoundError extends Error {}

/** Ліміт синку вручну вичерпано (429); повідомлення — готовий текст для користувача. */
export class MailSyncLimitError extends Error {}

/** Сервер недоступний, відповів помилкою чи не за контрактом. */
export class MailUnavailableError extends Error {}
