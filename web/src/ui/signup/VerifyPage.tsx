import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router";

import { RESEND_WAIT_SECONDS, parseSignupProgress, type SignupProgress } from "../../domain/signup";
import { PROFILE } from "../navigation";
import { useAuth } from "../auth/AuthProvider";
import { Button } from "../components/button";
import { Spinner } from "../components/spinner";
import { useCountdown } from "../lib/useCountdown";
import { usePageTitle } from "../lib/usePageTitle";
import { CodeField } from "./CodeField";
import { ExpiredScreen, InvalidLinkScreen } from "./Screens";
import { Notice, SignupFrame, type NoticeTone } from "./SignupFrame";
import { useSignup } from "./SignupServices";
import { MAIL_UNAVAILABLE, UNAVAILABLE } from "./texts";

/** `/signup/verify`: без активної реєстрації (стан переходу з форми) — той самий екран помилки, що й без запрошення. */
export function VerifyPage() {
  const progress = parseSignupProgress(useLocation().state);
  return progress === null ? <InvalidLinkScreen /> : <VerifyForm progress={progress} />;
}

type Phase = "form" | "invalid" | "expired";

function VerifyForm({ progress }: { progress: SignupProgress }) {
  usePageTitle("Підтвердження email");
  const { services } = useSignup();
  const { adopt } = useAuth();
  const navigate = useNavigate();
  const { remaining, start } = useCountdown();
  const [signupId, setSignupId] = useState(progress.signupId);
  const [phase, setPhase] = useState<Phase>("form");
  // Нове значення скидає поле коду: воно очищується й знову отримує фокус.
  const [fieldKey, setFieldKey] = useState(0);
  const [codeError, setCodeError] = useState<string | undefined>(undefined);
  const [verifying, setVerifying] = useState(false);
  const [resending, setResending] = useState(false);
  const [notice, setNotice] = useState<{ tone: NoticeTone; text: string } | null>(null);

  // Лист щойно пішов: сервер дозволить новий не раніше, ніж за хвилину.
  useEffect(() => {
    start(RESEND_WAIT_SECONDS);
  }, [start]);

  async function verify(code: string) {
    setVerifying(true);
    setCodeError(undefined);
    const result = await services.verify(signupId, code);
    if (result.ok) {
      adopt(result.session);
      void navigate(PROFILE, { replace: true });
      return;
    }
    setVerifying(false);
    const { failure } = result;
    if (failure.kind === "expired") {
      setPhase("expired");
    } else if (failure.kind === "invite_used") {
      setPhase("invalid");
    } else {
      setCodeError(
        failure.kind === "unavailable"
          ? UNAVAILABLE
          : failure.attemptsLeft === null
            ? "Невірний код."
            : `Невірний код. Залишилось спроб: ${failure.attemptsLeft}`,
      );
      setFieldKey((key) => key + 1);
    }
  }

  async function resend() {
    setResending(true);
    setNotice(null);
    const result = await services.resend(signupId);
    setResending(false);
    if (result.ok) {
      setSignupId(result.signupId);
      setNotice({ tone: "success", text: "Новий код надіслано" });
      setFieldKey((key) => key + 1);
      start(RESEND_WAIT_SECONDS);
      return;
    }
    const { failure } = result;
    if (failure.kind === "expired") {
      setPhase("expired");
    } else if (failure.kind === "too_many_attempts") {
      start(failure.retryAfterSeconds);
    } else {
      setNotice({ tone: "danger", text: failure.kind === "mail_unavailable" ? MAIL_UNAVAILABLE : UNAVAILABLE });
    }
  }

  if (phase === "invalid") {
    return <InvalidLinkScreen />;
  }
  if (phase === "expired") {
    return <ExpiredScreen invite={progress.invite} />;
  }
  return (
    <SignupFrame title="Підтверди email" subtitle={`Ми надіслали 6-цифровий код на ${progress.email}.`}>
      <div className="mt-6 flex flex-col gap-4">
        <CodeField key={fieldKey} error={codeError} disabled={verifying} onComplete={(code) => void verify(code)} />
        {verifying ? (
          <p role="status" aria-busy="true" className="flex items-center justify-center gap-2 text-caption text-muted-foreground">
            <Spinner />
            Перевіряємо…
          </p>
        ) : null}
        <Button type="button" variant="secondary" disabled={remaining > 0 || resending} onClick={() => void resend()}>
          {remaining > 0 ? `Надіслати ще раз через ${remaining} с` : "Надіслати код ще раз"}
        </Button>
        {notice === null ? null : <Notice tone={notice.tone}>{notice.text}</Notice>}
      </div>
    </SignupFrame>
  );
}
