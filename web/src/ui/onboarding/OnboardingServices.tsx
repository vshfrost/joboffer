import { createContext, use, type ReactNode } from "react";

import type { OnboardingServices } from "../../application/onboarding";

const OnboardingServicesContext = createContext<OnboardingServices | null>(null);

export function OnboardingServicesProvider({ services, children }: { services: OnboardingServices; children: ReactNode }) {
  return <OnboardingServicesContext value={services}>{children}</OnboardingServicesContext>;
}

export function useOnboardingServices(): OnboardingServices {
  const services = use(OnboardingServicesContext);
  if (services === null) {
    throw new Error("useOnboardingServices потребує OnboardingServicesProvider");
  }
  return services;
}
