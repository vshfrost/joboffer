import type { FilteredJob, NewSource, RefreshState, Source, SourceKind, SourcesOverview } from "../domain/sources";

/** API джерел вакансій. Помилки — з `domain/sourcesErrors`; кожен метод може кинути SourcesUnauthorizedError і SourcesUnavailableError. */
export interface SourcesApi {
  /** Компанії, стрічки, ліміт «Оновити зараз» і скільки вакансій уже не проходять фільтр. */
  overview(): Promise<SourcesOverview>;
  /** Додає джерело (для компанії сервер робить пробний запит до платформи). Кидає SourcesValidationError (422): тексти біля полів. */
  add(input: NewSource): Promise<Source>;
  /** Вмикає чи вимикає джерело. Кидає SourcesNotFoundError, коли джерела нема або воно чуже. */
  setEnabled(kind: SourceKind, id: string, enabled: boolean): Promise<Source>;
  /** Видаляє джерело; імпортовані вакансії лишаються. Кидає SourcesNotFoundError. */
  remove(kind: SourceKind, id: string): Promise<void>;
  /** Ставить «Оновити зараз» у чергу. Кидає SourcesRefreshLimitError, коли ліміт вичерпано (429). */
  requestRefresh(): Promise<RefreshState>;
  /** Вакансії з джерел, що за поточним профілем уже не проходять фільтр. */
  filtered(): Promise<FilteredJob[]>;
  /** Ховає вибрані вакансії; повертає, скільки сховано. Кидає SourcesFilteredChangedError (409): нічого не сховано. */
  dismiss(numbers: readonly number[]): Promise<number>;
}
