import { createContext, use, type ReactNode } from "react";

import type { MailServices } from "../../application/mail";

const MailContext = createContext<MailServices | null>(null);

export function MailServicesProvider({ services, children }: { services: MailServices; children: ReactNode }) {
  return <MailContext value={services}>{children}</MailContext>;
}

export function useMailServices(): MailServices {
  const services = use(MailContext);
  if (services === null) {
    throw new Error("Пошта потребує MailServicesProvider");
  }
  return services;
}
