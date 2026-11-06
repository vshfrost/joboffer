/** Причини, з яких операція з фото не вдалась. Порт кидає їх, application перетворює на результат. */

/** Сесія завершилась (401). */
export class PhotosUnauthorizedError extends Error {}

/** Сервер відхилив кадр (422); повідомлення — готовий текст для користувача. */
export class PhotosRejectedError extends Error {}

/** Фото нема або воно чуже (404): відповідь однакова. */
export class PhotosNotFoundError extends Error {}

/** Сервер недоступний, відповів помилкою чи не за контрактом. */
export class PhotosUnavailableError extends Error {}
