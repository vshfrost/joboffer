import { STEP_KEYS, type Onboarding, type OnboardingStep, type OnboardingTip, type StepKey } from "../domain/onboarding";
import { OnboardingUnavailableError } from "../domain/onboardingErrors";
import type { OnboardingApi } from "../ports/onboardingApi";
import type { ApiClient, ApiResponse } from "./apiClient";

const CONTRACT = "Відповідь сервера не за контрактом";

export function createHttpOnboardingApi(client: ApiClient): OnboardingApi {
  return {
    async get() {
      const response = await requestOrUnavailable(() => client.request("GET", "/onboarding"));
      throwForStatus(response, 200);
      return readOnboarding(response.body);
    },

    async markSeen(key) {
      throwForStatus(await requestOrUnavailable(() => client.request("POST", `/onboarding/tips/${key}/seen`)), 204);
    },

    async dismiss(key) {
      throwForStatus(await requestOrUnavailable(() => client.request("POST", `/onboarding/tips/${key}/dismiss`)), 204);
    },
  };
}

function throwForStatus(response: ApiResponse, success: number): void {
  if (response.status !== success) {
    throw new OnboardingUnavailableError(`Онбординг: відповідь ${response.status}`);
  }
}

async function requestOrUnavailable<T>(call: () => Promise<T>): Promise<T> {
  try {
    return await call();
  } catch {
    throw new OnboardingUnavailableError("Мережа недоступна");
  }
}

function record(value: unknown): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new OnboardingUnavailableError(CONTRACT);
  }
  return value as Record<string, unknown>;
}

function list(value: unknown): unknown[] {
  if (!Array.isArray(value)) {
    throw new OnboardingUnavailableError(CONTRACT);
  }
  return value;
}

function flag(value: unknown): boolean {
  if (typeof value !== "boolean") {
    throw new OnboardingUnavailableError(CONTRACT);
  }
  return value;
}

function stepKey(value: unknown): StepKey {
  const found = STEP_KEYS.find((key) => key === value);
  if (found === undefined) {
    throw new OnboardingUnavailableError(CONTRACT);
  }
  return found;
}

function readStep(item: unknown): OnboardingStep {
  const value = record(item);
  return { key: stepKey(value["key"]), done: flag(value["done"]), optional: flag(value["optional"]) };
}

function readTip(item: unknown): OnboardingTip {
  const value = record(item);
  return { key: stepKey(value["key"]), seen: flag(value["seen"]), dismissed: flag(value["dismissed"]) };
}

function readOnboarding(body: unknown): Onboarding {
  const value = record(body);
  return {
    steps: list(value["steps"]).map(readStep),
    tips: list(value["tips"]).map(readTip),
    complete: flag(value["complete"]),
  };
}
