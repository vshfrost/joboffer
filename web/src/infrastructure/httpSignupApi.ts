import { ServiceUnavailableError, TooManyAttemptsError } from "../domain/authErrors";
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
import type { SignupApi } from "../ports/signupApi";
import type { ApiClient, ApiResponse } from "./apiClient";
import { acceptSession, retryAfterSeconds } from "./httpAuthApi";

const GENERIC_REJECTION = "Перевір введені дані.";

/** Тіло помилки API: `{code, message, field_errors: [{field, message}], attempts_left?}`. */
interface ErrorBody {
  code?: unknown;
  message?: unknown;
  field_errors?: unknown;
  attempts_left?: unknown;
}

function errorBody(response: ApiResponse): ErrorBody | undefined {
  return response.body as ErrorBody | undefined;
}

export function createHttpSignupApi(client: ApiClient): SignupApi {
  return {
    async checkInvite(token) {
      const response = await client.request("GET", `/auth/signup/invite?invite=${encodeURIComponent(token)}`);
      if (response.status === 404) {
        throw new InviteInvalidError("Запрошення недійсне");
      }
      if (response.status === 429) {
        throw new TooManyAttemptsError(retryAfterSeconds(response.headers.get("Retry-After")));
      }
      if (response.status !== 200 || (response.body as { valid?: unknown } | undefined)?.valid !== true) {
        throw new ServiceUnavailableError(`Запрошення: відповідь ${response.status}`);
      }
    },

    async signup(draft, termsVersion) {
      const response = await client.request("POST", "/auth/signup", {
        email: draft.email,
        password: draft.password,
        display_name: draft.displayName,
        invite: draft.invite,
        terms_version: termsVersion,
        altcha: draft.altcha,
        website: draft.website,
      });
      if (response.status === 404) {
        throw new InviteInvalidError("Запрошення недійсне");
      }
      if (response.status === 422) {
        throw rejection(response);
      }
      return acceptedId(response, "Реєстрація");
    },

    async verify(signupId, code) {
      const response = await client.request("POST", "/auth/signup/verify", { signup_id: signupId, code });
      if (response.status === 201) {
        return acceptSession(client, response.body);
      }
      if (response.status === 409) {
        throw new InviteUsedError("Запрошення вже використано");
      }
      const body = errorBody(response);
      if (response.status === 422 && body?.code === "code_incorrect") {
        throw new CodeIncorrectError(typeof body.attempts_left === "number" ? body.attempts_left : null);
      }
      if (response.status === 422 && body?.code === "signup_expired") {
        throw new SignupExpiredError("Запит на реєстрацію прострочено");
      }
      throw new ServiceUnavailableError(`Код: відповідь ${response.status}`);
    },

    async resend(signupId) {
      const response = await client.request("POST", "/auth/signup/resend", { signup_id: signupId });
      if (response.status === 422 && errorBody(response)?.code === "signup_expired") {
        throw new SignupExpiredError("Запит на реєстрацію прострочено");
      }
      return acceptedId(response, "Повторний код");
    },
  };
}

/** 202 `{signup_id}` → id; 429 і 503 мають власні помилки; будь-що інше — збій. */
function acceptedId(response: ApiResponse, what: string): string {
  if (response.status === 429) {
    throw new TooManyAttemptsError(retryAfterSeconds(response.headers.get("Retry-After")));
  }
  if (response.status === 503 && errorBody(response)?.code !== "registration_closed") {
    throw new MailUnavailableError("Лист не надіслано");
  }
  const id = (response.body as { signup_id?: unknown } | undefined)?.signup_id;
  if (response.status !== 202 || typeof id !== "string") {
    throw new ServiceUnavailableError(`${what}: відповідь ${response.status}`);
  }
  return id;
}

/** 422 на реєстрації: невдала ALTCHA або поля форми; без переліку полів — одне повідомлення на всю форму. */
function rejection(response: ApiResponse): Error {
  const body = errorBody(response);
  if (body?.code === "challenge_failed") {
    return new ChallengeFailedError("Перевірку не пройдено");
  }
  const problems: FieldProblem[] = Array.isArray(body?.field_errors)
    ? (body.field_errors as FieldProblem[])
    : [];
  const message = typeof body?.message === "string" ? body.message : GENERIC_REJECTION;
  return new FieldsRejectedError(problems.length > 0 ? problems : [{ field: "", message }]);
}
