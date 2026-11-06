import type { Profile, ProfileSection } from "../domain/profile";

/** API профілю. Кожен розділ зберігається окремо; відповідь — профіль цілком. */
export interface ProfileApi {
  /** Кидає ProfileUnavailableError. */
  get(): Promise<Profile>;
  /** Кидає ProfileValidationError (422) або ProfileUnavailableError. */
  save<S extends ProfileSection>(section: S, value: Profile[S]): Promise<Profile>;
}
