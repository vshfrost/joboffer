import { Outlet } from "react-router";

import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

export function AppShell() {
  return (
    <div className="min-h-dvh md:flex">
      <a
        href="#content"
        className="sr-only z-50 rounded-lg bg-card px-4 py-2 text-nav font-medium focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
      >
        Перейти до змісту
      </a>
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar />
        <main id="content" tabIndex={-1} className="px-4 py-6 outline-none md:px-6 lg:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
