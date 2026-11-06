import { createContext, use, type ReactNode } from "react";

import type { SourcesServices } from "../../application/sources";

const SourcesContext = createContext<SourcesServices | null>(null);

export function SourcesServicesProvider({ services, children }: { services: SourcesServices; children: ReactNode }) {
  return <SourcesContext value={services}>{children}</SourcesContext>;
}

export function useSourcesServices(): SourcesServices {
  const services = use(SourcesContext);
  if (services === null) {
    throw new Error("Джерела потребують SourcesServicesProvider");
  }
  return services;
}
