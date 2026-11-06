/** Причини, з яких документи вакансії не завантажились. Порт кидає їх, application перетворює на результат. */

/** Сесія завершилась (401): документи відкриваються лише з чинною сесією. */
export class DocumentsUnauthorizedError extends Error {}

/** Доступу до документів цієї вакансії нема (403). */
export class DocumentsForbiddenError extends Error {}

/** Вакансії нема або вона чужа (404): відповідь однакова. */
export class DocumentsNotFoundError extends Error {}

/** Сервер недоступний, відповів помилкою чи не за контрактом. */
export class DocumentsUnavailableError extends Error {}
