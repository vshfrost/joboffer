import type { LegalDoc, LegalDocument } from "../domain/legal";

/** API юридичних текстів; сесія не потрібна. Кидає LegalNotFoundError або ServiceUnavailableError. */
export interface LegalApi {
  document(doc: LegalDoc): Promise<LegalDocument>;
}
