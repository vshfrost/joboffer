import { createContext, use, type ReactNode } from "react";

import type { LegalServices } from "../../application/legal";

const LegalContext = createContext<LegalServices | null>(null);

export function LegalServicesProvider({ services, children }: { services: LegalServices; children: ReactNode }) {
  return <LegalContext value={services}>{children}</LegalContext>;
}

export function useLegalServices(): LegalServices {
  const services = use(LegalContext);
  if (services === null) {
    throw new Error("Юридичні сторінки потребують LegalServicesProvider");
  }
  return services;
}
