import type { Fact, FactDraft, OriginalCv } from "../domain/facts";

/** API фактів. Усі помилки — з `domain/factsErrors`. */
export interface FactsApi {
  /** Усі факти користувача за видами, всередині виду — в порядку додавання. Кидає FactsUnavailableError. */
  list(): Promise<Fact[]>;
  /** Оригінал CV; `null` — ще не збережено. Кидає FactsUnavailableError. */
  originalCv(): Promise<OriginalCv | null>;
  /** Підтверджує лише названі факти: усе або нічого. Кидає FactsValidationError, FactNotFoundError або FactsUnavailableError. */
  confirm(ids: readonly number[]): Promise<Fact[]>;
  /** Додає факт вручну: одразу підтверджений. Кидає FactsValidationError, FactsConflictError або FactsUnavailableError. */
  create(draft: FactDraft): Promise<Fact>;
  /** Змінює вид і текст (факт стає непідтвердженим). Кидає FactsValidationError, FactsConflictError, FactNotFoundError або FactsUnavailableError. */
  update(id: number, draft: FactDraft): Promise<Fact>;
  /** Видаляє назавжди. Кидає FactNotFoundError або FactsUnavailableError. */
  remove(id: number): Promise<void>;
}
