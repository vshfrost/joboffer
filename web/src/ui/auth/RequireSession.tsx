import { Navigate, Outlet, useLocation } from "react-router";

import { useAuth } from "./AuthProvider";
import { LoadingScreen } from "./LoadingScreen";

/** Гард приватних маршрутів: без сесії веде на `/login?next=<шлях>`, після виходу — на `/login`. */
export function RequireSession() {
  const { state } = useAuth();
  const { pathname, search, hash } = useLocation();
  if (state.status === "loading") {
    return <LoadingScreen />;
  }
  if (state.status === "anonymous") {
    const target = state.justSignedOut ? "/login" : `/login?${new URLSearchParams({ next: `${pathname}${search}${hash}` })}`;
    return <Navigate to={target} replace />;
  }
  return <Outlet />;
}
