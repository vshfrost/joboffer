import { Link, useSearchParams } from "react-router";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/tabs";
import { TooltipProvider } from "../components/tooltip";
import { usePageTitle } from "../lib/usePageTitle";
import { PageHeading } from "../pages/PageHeading";
import { InboxTab } from "./InboxTab";
import { MailProvider } from "./MailProvider";
import { SettingsTab } from "./SettingsTab";

/** `/profile/mail`: «Вхідні» й «Налаштування» пошти. Вкладка живе в адресі (`?tab=settings`). */
export function MailArea() {
  return (
    <TooltipProvider delayDuration={0}>
      <MailProvider>
        <MailPage />
      </MailProvider>
    </TooltipProvider>
  );
}

function MailPage() {
  usePageTitle("Пошта");
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") === "settings" ? "settings" : "inbox";
  return (
    <>
      <PageHeading title="Пошта" subtitle="Профіль / Пошта" />
      <Link to="/profile" className="mb-4 inline-flex h-10 items-center rounded-lg border border-border bg-card px-3 text-nav font-medium pointer-coarse:h-11">
        ← Огляд профілю
      </Link>
      <Tabs value={tab} onValueChange={(next) => setParams(next === "settings" ? new URLSearchParams({ tab: "settings" }) : new URLSearchParams())}>
        <TabsList aria-label="Розділи пошти">
          <TabsTrigger value="inbox">Вхідні</TabsTrigger>
          <TabsTrigger value="settings">Налаштування</TabsTrigger>
        </TabsList>
        <TabsContent value="inbox">
          <InboxTab />
        </TabsContent>
        <TabsContent value="settings">
          <SettingsTab />
        </TabsContent>
      </Tabs>
    </>
  );
}
