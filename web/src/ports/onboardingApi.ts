import type { Onboarding, StepKey } from "../domain/onboarding";

/** API перших кроків. Усі методи кидають OnboardingUnavailableError, якщо сервер не відповів як треба. */
export interface OnboardingApi {
  /** Кроки (за даними користувача) і стан підказок. */
  get(): Promise<Onboarding>;
  /** @deprecated Підказки більше не показуємо. Позначає підказку баченою; повтор нічого не міняє. */
  markSeen(key: StepKey): Promise<void>;
  /** @deprecated Підказки більше не показуємо. Ховає підказку (вона стає й баченою); повтор нічого не міняє. */
  dismiss(key: StepKey): Promise<void>;
}
