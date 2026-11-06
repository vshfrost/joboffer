import { createContext, use, type ReactNode } from "react";

import type { RepliesServices } from "../../application/replies";

const RepliesContext = createContext<RepliesServices | null>(null);

export function RepliesServicesProvider({ services, children }: { services: RepliesServices; children: ReactNode }) {
  return <RepliesContext value={services}>{children}</RepliesContext>;
}

export function useRepliesServices(): RepliesServices {
  const services = use(RepliesContext);
  if (services === null) {
    throw new Error("Відповіді потребують RepliesServicesProvider");
  }
  return services;
}
