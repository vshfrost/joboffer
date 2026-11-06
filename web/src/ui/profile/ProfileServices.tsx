import { createContext, use, type ReactNode } from "react";

import type { ProfileServices } from "../../application/profile";

const ProfileServicesContext = createContext<ProfileServices | null>(null);

export function ProfileServicesProvider({ services, children }: { services: ProfileServices; children: ReactNode }) {
  return <ProfileServicesContext value={services}>{children}</ProfileServicesContext>;
}

export function useProfileServices(): ProfileServices {
  const services = use(ProfileServicesContext);
  if (services === null) {
    throw new Error("useProfileServices потребує ProfileServicesProvider");
  }
  return services;
}
