import type { Onboarding, StepKey } from "../domain/onboarding";
import { OnboardingUnavailableError } from "../domain/onboardingErrors";
import type { OnboardingApi } from "../ports/onboardingApi";

export type LoadOnboardingOutcome = { ok: true; onboarding: Onboarding } | { ok: false };

export type DismissTipOutcome = { ok: true } | { ok: false };

export interface OnboardingServices {
  load(): Promise<LoadOnboardingOutcome>;
  /** @deprecated Підказки більше не показуємо. Найкращі зусилля: збій не заважає читати підказку. */
  markSeen(key: StepKey): Promise<void>;
  /** @deprecated Підказки більше не показуємо. */
  dismiss(key: StepKey): Promise<DismissTipOutcome>;
}

export function createOnboardingServices(api: OnboardingApi): OnboardingServices {
  return {
    async load() {
      try {
        return { ok: true, onboarding: await api.get() };
      } catch (error) {
        return failure(error);
      }
    },

    async markSeen(key) {
      try {
        await api.markSeen(key);
      } catch (error) {
        failure(error);
      }
    },

    async dismiss(key) {
      try {
        await api.dismiss(key);
        return { ok: true };
      } catch (error) {
        return failure(error);
      }
    },
  };
}

function failure(error: unknown): { ok: false } {
  if (error instanceof OnboardingUnavailableError) {
    return { ok: false };
  }
  throw error;
}
