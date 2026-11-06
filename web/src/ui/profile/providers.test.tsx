/** Захисні перевірки провайдерів профілю й огляд без сесії — те, чого не бачить жоден сценарій «зверху». */
import { render, renderHook, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import type { AgentsServices } from "../../application/agents";
import type { AuthServices } from "../../application/auth";
import type { OnboardingServices } from "../../application/onboarding";
import type { ProfileServices } from "../../application/profile";
import type { Profile } from "../../domain/profile";
import type { PhotosServices } from "../../application/photos";
import type { CropperEngine } from "../../ports/cropper";
import { AgentsServicesProvider } from "../agents/AgentsServices";
import { AuthProvider } from "../auth/AuthProvider";
import { OnboardingServicesProvider } from "../onboarding/OnboardingServices";
import { PhotosServicesProvider } from "../photos/PhotosServices";
import { ProfileArea } from "./ProfileArea";
import { ProfileProvider, useProfile, useProfileLoad } from "./ProfileProvider";
import { ProfileServicesProvider, useProfileServices } from "./ProfileServices";

const PROFILE: Profile = {
  target: { roles: ["SRE"], seniority: [], minSalaryEur: null, targetDomains: [] },
  locations: { workModes: [], locations: [], includeUnknownMode: true, relocation: false },
  rules: { titleKeywords: [], titleExclude: [], stopWords: [] },
  contacts: { fullName: "", email: "", phone: "", linkedinUrl: "", city: "", githubUrl: "", workAuthorization: "" },
};

const NEVER: ProfileServices = { load: () => new Promise(() => undefined), save: () => new Promise(() => undefined) };
const READY: ProfileServices = { load: () => Promise.resolve({ ok: true, profile: PROFILE }), save: () => new Promise(() => undefined) };

const PHOTOS: PhotosServices = {
  load: () => new Promise(() => undefined),
  upload: () => new Promise(() => undefined),
  remove: () => new Promise(() => undefined),
  imageUrl: (id) => `/api/photos/${id}.jpg`,
};
const CROPPER: CropperEngine = { mount: () => new Promise(() => undefined) };
// Огляд містить картку «Перші кроки»: їй потрібні сервіси онбордингу й агентів, яких цей тест не перевіряє.
const ONBOARDING: OnboardingServices = {
  load: () => new Promise(() => undefined),
  markSeen: () => Promise.resolve(),
  dismiss: () => Promise.resolve({ ok: true }),
};
const AGENTS: AgentsServices = { load: () => new Promise(() => undefined) };

const ANONYMOUS: AuthServices = {
  login: () => Promise.resolve({ ok: false, failure: { kind: "unavailable" } }),
  currentSession: () => Promise.resolve(null),
  logout: () => Promise.resolve(true),
  providers: () => Promise.resolve({ google: false }),
  googleStartUrl: () => "/start",
};

// React друкує кинуту помилку хука в console.error: тут вона очікувана.
beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => undefined);
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe("хуки без провайдера", () => {
  test("useProfileServices", () => {
    expect(() => renderHook(() => useProfileServices())).toThrow("useProfileServices потребує ProfileServicesProvider");
  });

  test("useProfileLoad", () => {
    expect(() => renderHook(() => useProfileLoad())).toThrow("useProfileLoad потребує ProfileProvider");
  });

  test("useProfile, поки профіль не завантажено", () => {
    const wrapper = ({ children }: { children: ReactNode }) => (
      <ProfileServicesProvider services={NEVER}>
        <ProfileProvider>{children}</ProfileProvider>
      </ProfileServicesProvider>
    );
    expect(() => renderHook(() => useProfile(), { wrapper })).toThrow("Профіль ще не завантажено");
  });
});

describe("огляд без сесії", () => {
  test("людини в огляді нема, але картки є", async () => {
    const router = createMemoryRouter([{ path: "/profile/*", element: <ProfileArea /> }], { initialEntries: ["/profile"] });
    render(
      <AuthProvider services={ANONYMOUS}>
        <ProfileServicesProvider services={READY}>
          <OnboardingServicesProvider services={ONBOARDING}>
            <AgentsServicesProvider services={AGENTS}>
              <PhotosServicesProvider services={PHOTOS} cropper={CROPPER}>
                <RouterProvider router={router} />
              </PhotosServicesProvider>
            </AgentsServicesProvider>
          </OnboardingServicesProvider>
        </ProfileServicesProvider>
      </AuthProvider>,
    );
    expect(await screen.findByRole("heading", { level: 2, name: "Кар’єрна ціль" })).toBeDefined();
    expect(screen.queryByText("TU")).toBeNull();
    expect(document.querySelector('[aria-hidden="true"].rounded-full')).toBeNull();
  });
});
