import { createContext, use, type ReactNode } from "react";

import type { JobsServices } from "../../application/jobs";

const JobsServicesContext = createContext<JobsServices | null>(null);

export function JobsServicesProvider({ services, children }: { services: JobsServices; children: ReactNode }) {
  return <JobsServicesContext value={services}>{children}</JobsServicesContext>;
}

export function useJobsServices(): JobsServices {
  const services = use(JobsServicesContext);
  if (services === null) {
    throw new Error("useJobsServices потребує JobsServicesProvider");
  }
  return services;
}
