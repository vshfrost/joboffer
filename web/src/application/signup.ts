import { TooManyAttemptsError } from "../domain/authErrors";
import type { Session } from "../domain/session";
import type { SignupDraft } from "../domain/signup";
import {
  ChallengeFailedError,
  CodeIncorrectError,
  FieldsRejectedError,
  InviteInvalidError,
  InviteUsedError,
  MailUnavailableError,
  SignupExpiredError,
  type FieldProblem,
} from "../domain/signupErrors";
import type { LegalApi } from "../ports/legalApi";
import type { SignupApi } from "../ports/signupApi";

export type InviteCheck = "valid" | "invalid" | "unavailable";

export type SignupFailure =
  | { kind: "fields"; problems: readonly FieldProblem[] }
  | { kind: "challenge_failed" }
  | { kind: "invite_invalid" }
  | { kind: "too_many_attempts"; retryAfterSeconds: number }
  | { kind: "mail_unavailable" }
  | { kind: "unavailable" };

export type SignupOutcome = { ok: true; signupId: string } | { ok: false; failure: SignupFailure };

export type VerifyFailure =
  | { kind: "code_incorrect"; attemptsLeft: number | null }
  | { kind: "expired" }
  | { kind: "invite_used" }
  | { kind: "unavailable" };

export type VerifyOutcome = { ok: true; session: Session } | { ok: false; failure: VerifyFailure };

export type ResendFailure =
  | { kind: "too_many_attempts"; retryAfterSeconds: number }
  | { kind: "expired" }
  | { kind: "mail_unavailable" }
  | { kind: "unavailable" };

export type ResendOutcome = { ok: true; signupId: string } | { ok: false; failure: ResendFailure };

export interface SignupServices {
  checkInvite(token: string): Promise<InviteCheck>;
  /** Версію умов, на яку погоджується користувач, бере з бекенду в момент відправлення. */
  signup(draft: SignupDraft): Promise<SignupOutcome>;
  verify(signupId: string, code: string): Promise<VerifyOutcome>;
  resend(signupId: string): Promise<ResendOutcome>;
}

/** Решта помилок порту — збій сервера чи мережі (ServiceUnavailableError). */
export function createSignupServices(api: SignupApi, legal: LegalApi): SignupServices {
  return {
    async checkInvite(token) {
      try {
        await api.checkInvite(token);
        return "valid";
      } catch (error) {
        return error instanceof InviteInvalidError ? "invalid" : "unavailable";
      }
    },

    async signup(draft) {
      let termsVersion: string;
      try {
        termsVersion = (await legal.document("terms")).version;
      } catch {
        return { ok: false, failure: { kind: "unavailable" } };
      }
      try {
        return { ok: true, signupId: await api.signup(draft, termsVersion) };
      } catch (error) {
        return { ok: false, failure: signupFailure(error) };
      }
    },

    async verify(signupId, code) {
      try {
        return { ok: true, session: await api.verify(signupId, code) };
      } catch (error) {
        return { ok: false, failure: verifyFailure(error) };
      }
    },

    async resend(signupId) {
      try {
        return { ok: true, signupId: await api.resend(signupId) };
      } catch (error) {
        return { ok: false, failure: resendFailure(error) };
      }
    },
  };
}

function signupFailure(error: unknown): SignupFailure {
  if (error instanceof FieldsRejectedError) {
    return { kind: "fields", problems: error.problems };
  }
  if (error instanceof ChallengeFailedError) {
    return { kind: "challenge_failed" };
  }
  if (error instanceof InviteInvalidError) {
    return { kind: "invite_invalid" };
  }
  if (error instanceof TooManyAttemptsError) {
    return { kind: "too_many_attempts", retryAfterSeconds: error.retryAfterSeconds };
  }
  if (error instanceof MailUnavailableError) {
    return { kind: "mail_unavailable" };
  }
  return { kind: "unavailable" };
}

function verifyFailure(error: unknown): VerifyFailure {
  if (error instanceof CodeIncorrectError) {
    return { kind: "code_incorrect", attemptsLeft: error.attemptsLeft };
  }
  if (error instanceof SignupExpiredError) {
    return { kind: "expired" };
  }
  if (error instanceof InviteUsedError) {
    return { kind: "invite_used" };
  }
  return { kind: "unavailable" };
}

function resendFailure(error: unknown): ResendFailure {
  if (error instanceof TooManyAttemptsError) {
    return { kind: "too_many_attempts", retryAfterSeconds: error.retryAfterSeconds };
  }
  if (error instanceof SignupExpiredError) {
    return { kind: "expired" };
  }
  if (error instanceof MailUnavailableError) {
    return { kind: "mail_unavailable" };
  }
  return { kind: "unavailable" };
}
