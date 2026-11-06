import { ProfileUnavailableError, ProfileValidationError } from "../domain/profileErrors";
import type { FieldErrors, Profile, ProfileSection } from "../domain/profile";
import type { ProfileApi } from "../ports/profileApi";

export type LoadOutcome = { ok: true; profile: Profile } | { ok: false };

export type SaveOutcome =
  | { ok: true; profile: Profile }
  /** Сервер відхилив значення: тексти біля полів. */
  | { ok: false; kind: "invalid"; fieldErrors: FieldErrors }
  | { ok: false; kind: "unavailable" };

export interface ProfileServices {
  load(): Promise<LoadOutcome>;
  /** Зберігає один розділ; успіхом вважається лише відповідь сервера. */
  save<S extends ProfileSection>(section: S, value: Profile[S]): Promise<SaveOutcome>;
}

export function createProfileServices(api: ProfileApi): ProfileServices {
  return {
    async load() {
      try {
        return { ok: true, profile: await api.get() };
      } catch (error) {
        if (error instanceof ProfileUnavailableError) {
          return { ok: false };
        }
        throw error;
      }
    },

    async save(section, value) {
      try {
        return { ok: true, profile: await api.save(section, value) };
      } catch (error) {
        if (error instanceof ProfileValidationError) {
          return { ok: false, kind: "invalid", fieldErrors: { ...error.fieldErrors } };
        }
        if (error instanceof ProfileUnavailableError) {
          return { ok: false, kind: "unavailable" };
        }
        throw error;
      }
    },
  };
}
