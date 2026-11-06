import type { LegalDoc, LegalDocument } from "../domain/legal";
import { LegalNotFoundError } from "../domain/legalErrors";
import type { LegalApi } from "../ports/legalApi";

export type LegalOutcome = { ok: true; value: LegalDocument } | { ok: false; kind: "not-found" | "unavailable" };

export interface LegalServices {
  document(doc: LegalDoc): Promise<LegalOutcome>;
}

export function createLegalServices(api: LegalApi): LegalServices {
  return {
    async document(doc) {
      try {
        return { ok: true, value: await api.document(doc) };
      } catch (error) {
        return { ok: false, kind: error instanceof LegalNotFoundError ? "not-found" : "unavailable" };
      }
    },
  };
}
