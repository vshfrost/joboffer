/** Юридичні документи: умови й політика. Текст — звичайний текст з абзацами, не розмітка. */

export const LEGAL_DOCS = ["terms", "privacy"] as const;
export type LegalDoc = (typeof LEGAL_DOCS)[number];

export interface LegalDocument {
  doc: LegalDoc;
  /** Номер версії редакції; бекенд — єдине джерело. */
  version: string;
  text: string;
}

export const LEGAL_TITLES: Record<LegalDoc, string> = {
  terms: "Умови користування",
  privacy: "Політика конфіденційності",
};
