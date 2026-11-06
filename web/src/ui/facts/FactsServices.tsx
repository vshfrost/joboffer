import { createContext, use, type ReactNode } from "react";

import type { FactsServices } from "../../application/facts";

const FactsServicesContext = createContext<FactsServices | null>(null);

export function FactsServicesProvider({ services, children }: { services: FactsServices; children: ReactNode }) {
  return <FactsServicesContext value={services}>{children}</FactsServicesContext>;
}

export function useFactsServices(): FactsServices {
  const services = use(FactsServicesContext);
  if (services === null) {
    throw new Error("useFactsServices потребує FactsServicesProvider");
  }
  return services;
}
