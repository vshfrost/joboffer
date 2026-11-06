import type { Session } from "../domain/session";
import type { SignupDraft } from "../domain/signup";

/** API реєстрації за запрошенням; сесія не потрібна. Збій сервера чи мережі — ServiceUnavailableError. */
export interface SignupApi {
  /** Кидає InviteInvalidError, TooManyAttemptsError. */
  checkInvite(token: string): Promise<void>;
  /**
   * Надсилає дані й просить код на пошту; повертає `signup_id`.
   * Кидає InviteInvalidError, ChallengeFailedError, FieldsRejectedError, TooManyAttemptsError, MailUnavailableError.
   */
  signup(draft: SignupDraft, termsVersion: string): Promise<string>;
  /** Кидає CodeIncorrectError, SignupExpiredError, InviteUsedError. Успіх відкриває сесію. */
  verify(signupId: string, code: string): Promise<Session>;
  /** Новий код; повертає `signup_id`. Кидає SignupExpiredError, TooManyAttemptsError, MailUnavailableError. */
  resend(signupId: string): Promise<string>;
}
