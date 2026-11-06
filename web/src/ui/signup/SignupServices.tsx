import { createContext, use, type ComponentType, type ReactNode } from "react";

import type { SignupServices } from "../../application/signup";
import type { AltchaWidgetProps } from "./AltchaWidget";

interface SignupContext {
  services: SignupServices;
  /** Віджет ALTCHA: справжній у проді, двійник у тестах. */
  Widget: ComponentType<AltchaWidgetProps>;
  challengeUrl: string;
}

const Context = createContext<SignupContext | null>(null);

export function SignupServicesProvider({
  services,
  widget,
  challengeUrl,
  children,
}: {
  services: SignupServices;
  widget: ComponentType<AltchaWidgetProps>;
  challengeUrl: string;
  children: ReactNode;
}) {
  return <Context value={{ services, Widget: widget, challengeUrl }}>{children}</Context>;
}

export function useSignup(): SignupContext {
  const context = use(Context);
  if (context === null) {
    throw new Error("Реєстрація потребує SignupServicesProvider");
  }
  return context;
}
