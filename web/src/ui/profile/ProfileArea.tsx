import type { ReactNode } from "react";
import { Route, Routes } from "react-router";

import { Button } from "../components/button";
import { NotFoundPage } from "../pages/NotFoundPage";
import { PageHeading } from "../pages/PageHeading";
import { usePageTitle } from "../lib/usePageTitle";
import { ContactsEditor } from "./ContactsEditor";
import { LeaveGuard } from "./LeaveGuard";
import { LocationsEditor } from "./LocationsEditor";
import { Overview } from "./Overview";
import { ProfileProvider, useProfileLoad } from "./ProfileProvider";
import { PhotosEditor } from "../photos/PhotosEditor";
import { PhotosProvider } from "../photos/PhotosProvider";
import { RulesEditor } from "./RulesEditor";
import { TargetEditor } from "./TargetEditor";

function Gate({ children }: { children: ReactNode }) {
  const { load, reload } = useProfileLoad();
  usePageTitle("Профіль");
  if (load.status === "ready") {
    return children;
  }
  return (
    <>
      <PageHeading title="Профіль" />
      {load.status === "loading" ? (
        <p role="status" className="text-caption text-muted-foreground">
          Завантажуємо профіль…
        </p>
      ) : (
        <div role="alert" className="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-status-danger p-4 text-status-danger-foreground">
          <p className="text-nav font-medium">Не вдалося завантажити профіль.</p>
          <Button variant="secondary" onClick={reload}>
            Спробувати ще раз
          </Button>
        </div>
      )}
    </>
  );
}

/** `/profile/*`: профіль завантажується один раз за візит, чернетки живуть, поки відкрита ця область. */
export function ProfileArea() {
  return (
    <ProfileProvider>
      <Gate>
        <LeaveGuard />
        <PhotosProvider>
        <Routes>
          <Route index element={<Overview />} />
          <Route path="target" element={<TargetEditor />} />
          <Route path="locations" element={<LocationsEditor />} />
          <Route path="rules" element={<RulesEditor />} />
          <Route path="contacts" element={<ContactsEditor />} />
          <Route path="photos" element={<PhotosEditor />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
        </PhotosProvider>
      </Gate>
    </ProfileProvider>
  );
}
