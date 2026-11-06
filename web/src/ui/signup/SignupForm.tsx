import { useCallback, useId, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router";

import type { SignupFailure } from "../../application/signup";
import { retryMinutes } from "../../domain/session";
import type { SignupProgress } from "../../domain/signup";
import { Button } from "../components/button";
import { Checkbox } from "../components/checkbox";
import { Field } from "../components/field";
import { Input } from "../components/input";
import { useCountdown } from "../lib/useCountdown";
import { usePageTitle } from "../lib/usePageTitle";
import { useSignup } from "./SignupServices";
import { Notice, SignupFrame, type NoticeTone } from "./SignupFrame";
import { MAIL_UNAVAILABLE, UNAVAILABLE } from "./texts";

/** Поля форми, під якими показується відповідь сервера про них (імена — з API). */
const FIELD_NAMES = ["email", "password", "display_name", "terms_version"];

function noticeFor(failure: SignupFailure | null, waitSeconds: number): { tone: NoticeTone; text: string } | null {
  switch (failure?.kind) {
    case "fields": {
      const rest = failure.problems.filter(({ field }) => !FIELD_NAMES.includes(field));
      return rest.length === 0 ? null : { tone: "danger", text: rest.map(({ message }) => message).join(" ") };
    }
    case "challenge_failed":
      return { tone: "danger", text: "Перевірку не пройдено. Спробуй ще раз." };
    case "too_many_attempts":
      return waitSeconds > 0 ? { tone: "warning", text: `Забагато спроб, спробуй за ~${retryMinutes(waitSeconds)} хв` } : null;
    case "mail_unavailable":
      return { tone: "danger", text: MAIL_UNAVAILABLE };
    case "unavailable":
      return { tone: "danger", text: UNAVAILABLE };
    default:
      return null;
  }
}

/** Форма реєстрації за дійсним запрошенням: email, імʼя, пароль, згода й ALTCHA. Google тут нема. */
export function SignupForm({ invite, onInviteInvalid }: { invite: string; onInviteInvalid(): void }) {
  usePageTitle("Реєстрація");
  const { services, Widget, challengeUrl } = useSignup();
  const navigate = useNavigate();
  const { remaining, start } = useCountdown();
  const consentId = useId();
  const consentErrorId = useId();
  const missingId = useId();
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [website, setWebsite] = useState("");
  const [consent, setConsent] = useState(false);
  const [payload, setPayload] = useState<string | null>(null);
  const [widgetKey, setWidgetKey] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [failure, setFailure] = useState<SignupFailure | null>(null);
  const resetPayload = useCallback(() => {
    setPayload(null);
  }, []);

  const problems = failure?.kind === "fields" ? failure.problems : [];
  const problemAt = (field: string) => problems.find((problem) => problem.field === field)?.message;
  const consentProblem = problemAt("terms_version");
  const notice = noticeFor(failure, remaining);
  // Що саме не дає відправити: згода раніше за перевірку; під час відправлення й паузи кнопка вимкнена з інших причин.
  const missing = submitting || remaining > 0 ? null : !consent ? "Погодься з умовами користування" : payload === null ? "Дочекайся перевірки «я не робот»" : null;
  const blocked = submitting || remaining > 0 || !consent || payload === null;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setFailure(null);
    // Кнопка вимкнена без розв'язку, тож сюди з `payload === null` не потрапити.
    const result = await services.signup({ email, password, displayName, invite, altcha: payload as string, website });
    setSubmitting(false);
    if (result.ok) {
      const progress: SignupProgress = { signupId: result.signupId, email, invite };
      void navigate("/signup/verify", { state: progress });
      return;
    }
    // Розв'язок ALTCHA одноразовий і гаситься ще до решти перевірок: далі потрібна нова задача.
    setPayload(null);
    setWidgetKey((key) => key + 1);
    if (result.failure.kind === "invite_invalid") {
      onInviteInvalid();
      return;
    }
    if (result.failure.kind === "too_many_attempts") {
      start(result.failure.retryAfterSeconds);
    }
    setFailure(result.failure);
  }

  return (
    <SignupFrame title="Реєстрація" subtitle="Створи акаунт за запрошенням.">
      <form onSubmit={(event) => void submit(event)} className="relative mt-6 flex flex-col gap-4">
        <Field label="Email" error={problemAt("email")}>
          {(control) => (
            <Input
              {...control}
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => {
                setEmail(event.target.value);
              }}
            />
          )}
        </Field>
        <Field label="Імʼя (необовʼязково)" error={problemAt("display_name")}>
          {(control) => (
            <Input
              {...control}
              type="text"
              autoComplete="name"
              value={displayName}
              onChange={(event) => {
                setDisplayName(event.target.value);
              }}
            />
          )}
        </Field>
        <Field label="Пароль" hint="Від 8 символів: цифра, мала й велика літера, спецсимвол." error={problemAt("password")}>
          {(control) => (
            <Input
              {...control}
              type="password"
              autoComplete="new-password"
              required
              value={password}
              onChange={(event) => {
                setPassword(event.target.value);
              }}
            />
          )}
        </Field>
        <div aria-hidden="true" className="absolute -left-[9999px] size-0 overflow-hidden">
          <input
            type="text"
            name="website"
            tabIndex={-1}
            autoComplete="off"
            value={website}
            onChange={(event) => {
              setWebsite(event.target.value);
            }}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <div className="flex items-start gap-2.5">
            <Checkbox
              id={consentId}
              checked={consent}
              aria-invalid={consentProblem === undefined ? undefined : true}
              aria-describedby={consentProblem === undefined ? undefined : consentErrorId}
              onCheckedChange={(on) => {
                setConsent(on === true);
              }}
            />
            <label htmlFor={consentId} className="text-caption">
              Погоджуюсь з{" "}
              <Link to="/terms" className="text-primary hover:underline">
                Умовами користування
              </Link>{" "}
              та{" "}
              <Link to="/privacy" className="text-primary hover:underline">
                Політикою конфіденційності
              </Link>
            </label>
          </div>
          {consentProblem === undefined ? null : (
            <p id={consentErrorId} className="text-caption font-medium text-destructive">
              {consentProblem}
            </p>
          )}
        </div>
        <Widget key={widgetKey} challengeUrl={challengeUrl} onSolved={setPayload} onReset={resetPayload} />
        {notice === null ? null : <Notice tone={notice.tone}>{notice.text}</Notice>}
        <Button type="submit" disabled={blocked} loading={submitting} aria-describedby={missing === null ? undefined : missingId}>
          {submitting ? "Реєструємо…" : "Зареєструватися"}
        </Button>
        {missing === null ? null : (
          <p id={missingId} className="-mt-2 text-caption text-muted-foreground">
            {missing}
          </p>
        )}
      </form>
    </SignupFrame>
  );
}
