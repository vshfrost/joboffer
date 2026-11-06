import { createContext, use, type ReactNode } from "react";

import type { DocumentsServices } from "../../application/documents";

const DocumentsServicesContext = createContext<DocumentsServices | null>(null);

export function DocumentsServicesProvider({ services, children }: { services: DocumentsServices; children: ReactNode }) {
  return <DocumentsServicesContext value={services}>{children}</DocumentsServicesContext>;
}

export function useDocumentsServices(): DocumentsServices {
  const services = use(DocumentsServicesContext);
  if (services === null) {
    throw new Error("useDocumentsServices потребує DocumentsServicesProvider");
  }
  return services;
}
