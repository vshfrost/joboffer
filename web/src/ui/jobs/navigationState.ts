/** Що сторінки вакансій передають одна одній через `location.state`: усе недовірене, тож перевіряється. */

function field(state: unknown, key: string): string | undefined {
  if (typeof state !== "object" || state === null) {
    return undefined;
  }
  const value = (state as Record<string, unknown>)[key];
  return typeof value === "string" ? value : undefined;
}

/** Повідомлення про результат додавання, яке деталі показують один раз. */
export function noticeOf(state: unknown): string | null {
  return field(state, "notice") ?? null;
}

/** Посилання, яке форма «Додати вакансію» має підставити (дописування тексту у вакансію з алерту). */
export function prefilledUrl(state: unknown): string {
  return field(state, "url") ?? "";
}
