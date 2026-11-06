import { ServiceUnavailableError } from "../domain/authErrors";
import { LegalNotFoundError } from "../domain/legalErrors";
import type { LegalApi } from "../ports/legalApi";
import type { ApiClient } from "./apiClient";

export function createHttpLegalApi(client: ApiClient): LegalApi {
  return {
    async document(doc) {
      const response = await client.request("GET", `/legal/${doc}`);
      if (response.status === 404) {
        throw new LegalNotFoundError(`Документ ${doc} не знайдено`);
      }
      const body = response.body as { version?: unknown; text?: unknown } | undefined;
      if (response.status !== 200 || typeof body?.version !== "string" || typeof body.text !== "string") {
        throw new ServiceUnavailableError(`Документ ${doc}: відповідь ${response.status}`);
      }
      return { doc, version: body.version, text: body.text };
    },
  };
}
