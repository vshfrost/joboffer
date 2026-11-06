import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";

import type { InviteCheck } from "../../application/signup";
import { LoadingScreen } from "../auth/LoadingScreen";
import { InvalidLinkScreen, InviteUnavailableScreen } from "./Screens";
import { SignupForm } from "./SignupForm";
import { useSignup } from "./SignupServices";

type Gate = "loading" | InviteCheck;

/** `/signup?invite=…`: форма лише для дійсного запрошення; без нього чи з недійсним — екран помилки. */
export function SignupPage() {
  const { services } = useSignup();
  const [params] = useSearchParams();
  const invite = params.get("invite") ?? "";
  const [gate, setGate] = useState<Gate>(invite === "" ? "invalid" : "loading");

  useEffect(() => {
    if (invite === "") {
      return;
    }
    void services.checkInvite(invite).then(setGate);
  }, [services, invite]);

  if (gate === "loading") {
    return <LoadingScreen />;
  }
  if (gate === "invalid") {
    return <InvalidLinkScreen />;
  }
  if (gate === "unavailable") {
    return <InviteUnavailableScreen />;
  }
  return (
    <SignupForm
      invite={invite}
      onInviteInvalid={() => {
        setGate("invalid");
      }}
    />
  );
}
