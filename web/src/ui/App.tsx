/** UI: React-компоненти. Дані отримують через порти з bootstrap, а не через прямий fetch. */
import { Navigate, Route, Routes } from "react-router";

import { LoginRoute } from "./auth/LoginRoute";
import { RequireSession } from "./auth/RequireSession";
import { LegalPage } from "./legal/LegalPage";
import { JobsArea } from "./jobs/JobsArea";
import { MailArea } from "./mail/MailArea";
import { AppShell } from "./layout/AppShell";
import { FactsPage } from "./facts/FactsPage";
import { FACTS, HOME, PREP, PROFILE, REPLIES, SOURCES } from "./navigation";
import { NotFoundPage } from "./pages/NotFoundPage";
import { PrepArea } from "./prep/PrepArea";
import { ProfileArea } from "./profile/ProfileArea";
import { RepliesArea } from "./replies/RepliesArea";
import { SignupPage } from "./signup/SignupPage";
import { VerifyPage } from "./signup/VerifyPage";
import { SourcesArea } from "./sources/SourcesArea";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginRoute />} />
      <Route path="/signup" element={<SignupPage />} />
      <Route path="/signup/verify" element={<VerifyPage />} />
      <Route path="/terms"element={<LegalPage doc="terms" />} />
      <Route path="/privacy" element={<LegalPage doc="privacy" />} />
      <Route element={<RequireSession />}>
        <Route element={<AppShell />}>
          <Route index element={<Navigate to={HOME} replace />} />
          <Route path={`${HOME}/*`} element={<JobsArea />} />
          <Route path={FACTS} element={<FactsPage />} />
          <Route path={REPLIES} element={<RepliesArea />} />
          <Route path={`${PREP}/*`} element={<PrepArea />} />
          <Route path={`${SOURCES}/*`} element={<SourcesArea />} />
          <Route path={`${PROFILE}/mail/*`} element={<MailArea />} />
          <Route path={`${PROFILE}/*`} element={<ProfileArea />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Route>
    </Routes>
  );
}
