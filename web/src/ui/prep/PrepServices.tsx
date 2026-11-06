import { createContext, use, type ReactNode } from "react";

import type { PrepServices } from "../../application/prep";

const PrepContext = createContext<PrepServices | null>(null);

export function PrepServicesProvider({ services, children }: { services: PrepServices; children: ReactNode }) {
  return <PrepContext value={services}>{children}</PrepContext>;
}

export function usePrepServices(): PrepServices {
  const services = use(PrepContext);
  if (services === null) {
    throw new Error("Підготовка потребує PrepServicesProvider");
  }
  return services;
}
