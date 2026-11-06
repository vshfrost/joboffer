import { createContext, use, type ReactNode } from "react";

import type { ApplicationsServices } from "../../application/applications";

const ApplicationsServicesContext = createContext<ApplicationsServices | null>(null);

export function ApplicationsServicesProvider({ services, children }: { services: ApplicationsServices; children: ReactNode }) {
  return <ApplicationsServicesContext value={services}>{children}</ApplicationsServicesContext>;
}

export function useApplicationsServices(): ApplicationsServices {
  const services = use(ApplicationsServicesContext);
  if (services === null) {
    throw new Error("useApplicationsServices потребує ApplicationsServicesProvider");
  }
  return services;
}
