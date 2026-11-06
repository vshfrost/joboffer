import { useEffect } from "react";
import { Navigate, useSearchParams } from "react-router";

import { safeNextPath } from "../../domain/session";
import { LoginPage } from "../pages/LoginPage";
import { useAuth } from "./AuthProvider";
import { LoadingScreen } from "./LoadingScreen";

/** `/login`: із сесією веде на `next` (лише внутрішній шлях), без неї показує форму. */
export function LoginRoute() {
  const { state, acknowledgeSignOut } = useAuth();
  const [params] = useSearchParams();

  useEffect(() => {
    acknowledgeSignOut();
  }, [acknowledgeSignOut]);

  if (state.status === "loading") {
    return <LoadingScreen />;
  }
  if (state.status === "authenticated") {
    return <Navigate to={safeNextPath(params.get("next"))} replace />;
  }
  return <LoginPage />;
}
