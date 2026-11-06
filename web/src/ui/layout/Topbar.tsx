import { CircleAlert, LogOut } from "lucide-react";
import { useState } from "react";
import { useLocation } from "react-router";

import { useAuth } from "../auth/AuthProvider";
import { Button } from "../components/button";
import { sectionFor } from "../navigation";
import { MobileNav } from "./MobileNav";

export function Topbar() {
  const { pathname } = useLocation();
  const { state, logout } = useAuth();
  const [logoutFailed, setLogoutFailed] = useState(false);
  const current = sectionFor(pathname)?.label ?? "Не знайдено";

  async function signOut() {
    setLogoutFailed(false);
    setLogoutFailed(!(await logout()));
  }

  return (
    <>
      <header className="flex h-14 items-center gap-3 border-b border-border bg-background px-4 md:px-6 lg:px-8">
        <MobileNav />
        <nav aria-label="Хлібні крихти" className="flex min-w-0 items-center gap-2 text-caption text-muted-foreground">
          <span className="hidden sm:inline">Робочий простір</span>
          <span aria-hidden="true" className="hidden sm:inline">
            /
          </span>
          <strong aria-current="page" className="truncate font-semibold text-foreground">
            {current}
          </strong>
        </nav>
        <div className="ml-auto flex min-w-0 items-center gap-1">
          {state.status === "authenticated" ? (
            <span className="truncate text-caption font-medium">{state.user.displayName}</span>
          ) : null}
          <Button variant="ghost" size="sm" aria-label="Вийти" onClick={() => void signOut()}>
            <LogOut aria-hidden="true" />
            <span className="hidden md:inline">Вийти</span>
          </Button>
        </div>
      </header>
      {logoutFailed ? (
        <div
          role="alert"
          className="flex items-start gap-2 bg-status-danger px-4 py-2 text-caption text-status-danger-foreground md:px-6 lg:px-8"
        >
          <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          <span>Не вдалося вийти. Спробуй ще раз.</span>
        </div>
      ) : null}
    </>
  );
}
