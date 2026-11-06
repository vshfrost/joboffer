/** Клієнт у зборі: адаптери → сценарії → UI. Роутер дає той, хто монтує (main або тест). */
import { useState, type ComponentType } from "react";

import { createAgentsServices } from "../application/agents";
import { createApplicationsServices } from "../application/applications";
import { createAuthServices } from "../application/auth";
import { createDocumentsServices } from "../application/documents";
import { createFactsServices } from "../application/facts";
import { createJobsServices } from "../application/jobs";
import { createLegalServices } from "../application/legal";
import { createMailServices } from "../application/mail";
import { createOnboardingServices } from "../application/onboarding";
import { createPhotosServices } from "../application/photos";
import { createPrepServices } from "../application/prep";
import { createProfileServices } from "../application/profile";
import { createPromptsServices } from "../application/prompts";
import { createRepliesServices } from "../application/replies";
import { createSignupServices } from "../application/signup";
import { createSourcesServices } from "../application/sources";
import { createApiClient } from "../infrastructure/apiClient";
import { createCropperjsEngine } from "../infrastructure/cropperjsEngine";
import { createHttpAgentsApi } from "../infrastructure/httpAgentsApi";
import { createHttpApplicationsApi } from "../infrastructure/httpApplicationsApi";
import { createHttpAuthApi } from "../infrastructure/httpAuthApi";
import { createHttpDocumentsApi } from "../infrastructure/httpDocumentsApi";
import { createHttpFactsApi } from "../infrastructure/httpFactsApi";
import { createHttpJobsApi } from "../infrastructure/httpJobsApi";
import { createHttpLegalApi } from "../infrastructure/httpLegalApi";
import { createHttpMailApi } from "../infrastructure/httpMailApi";
import { createHttpOnboardingApi } from "../infrastructure/httpOnboardingApi";
import { createHttpPhotosApi } from "../infrastructure/httpPhotosApi";
import { createHttpPrepApi } from "../infrastructure/httpPrepApi";
import { createHttpProfileApi } from "../infrastructure/httpProfileApi";
import { createHttpPromptsApi } from "../infrastructure/httpPromptsApi";
import { createHttpRepliesApi } from "../infrastructure/httpRepliesApi";
import { createHttpSignupApi } from "../infrastructure/httpSignupApi";
import { createHttpSourcesApi } from "../infrastructure/httpSourcesApi";
import type { CropperEngine } from "../ports/cropper";
import { App } from "../ui/App";
import { AgentsServicesProvider } from "../ui/agents/AgentsServices";
import { ApplicationsServicesProvider } from "../ui/applications/ApplicationsServices";
import { AuthProvider } from "../ui/auth/AuthProvider";
import { DocumentsServicesProvider } from "../ui/documents/DocumentsServices";
import { FactsServicesProvider } from "../ui/facts/FactsServices";
import { JobsServicesProvider } from "../ui/jobs/JobsServices";
import { LegalServicesProvider } from "../ui/legal/LegalServices";
import { MailServicesProvider } from "../ui/mail/MailServices";
import { OnboardingServicesProvider } from "../ui/onboarding/OnboardingServices";
import { PhotosServicesProvider } from "../ui/photos/PhotosServices";
import { PrepServicesProvider } from "../ui/prep/PrepServices";
import { ProfileServicesProvider } from "../ui/profile/ProfileServices";
import { PromptsServicesProvider } from "../ui/prompts/PromptsServices";
import { RepliesServicesProvider } from "../ui/replies/RepliesServices";
import { AltchaWidget, type AltchaWidgetProps } from "../ui/signup/AltchaWidget";
import { SignupServicesProvider } from "../ui/signup/SignupServices";
import { SourcesServicesProvider } from "../ui/sources/SourcesServices";

export interface ClientProps {
  fetchFn: typeof fetch;
  /** Де бекенд: у dev Vite-проксі віддає `/api` бекенду, вирізаючи префікс. */
  apiBase?: string;
  /** Редактор кадрування фото: у проді cropperjs, у тестах двійник на межі. */
  cropper?: CropperEngine;
  /** Віджет ALTCHA на формі реєстрації: у проді справжній, у тестах двійник на межі. */
  altchaWidget?: ComponentType<AltchaWidgetProps>;
}

export function Client({ fetchFn, apiBase = "/api", cropper, altchaWidget = AltchaWidget }: ClientProps) {
  // Один набір сервісів на життя клієнта; адаптери ділять один HTTP-клієнт, а з ним і CSRF-токен.
  const [services] = useState(() => {
    const api = createApiClient(fetchFn, apiBase);
    return {
      auth: createAuthServices(createHttpAuthApi(api, apiBase)),
      profile: createProfileServices(createHttpProfileApi(api)),
      agents: createAgentsServices(createHttpAgentsApi(api)),
      prompts: createPromptsServices(createHttpPromptsApi(api)),
      onboarding: createOnboardingServices(createHttpOnboardingApi(api)),
      jobs: createJobsServices(createHttpJobsApi(api)),
      applications: createApplicationsServices(createHttpApplicationsApi(api)),
      facts: createFactsServices(createHttpFactsApi(api)),
      documents: createDocumentsServices(createHttpDocumentsApi(api, apiBase)),
      photos: createPhotosServices(createHttpPhotosApi(api, apiBase)),
      mail: createMailServices(createHttpMailApi(api)),
      replies: createRepliesServices(createHttpRepliesApi(api)),
      sources: createSourcesServices(createHttpSourcesApi(api)),
      prep: createPrepServices(createHttpPrepApi(api)),
      legal: createLegalServices(createHttpLegalApi(api)),
      signup: createSignupServices(createHttpSignupApi(api), createHttpLegalApi(api)),
      cropper: cropper ?? createCropperjsEngine(),
    };
  });
  return (
    <AuthProvider services={services.auth}>
      <ProfileServicesProvider services={services.profile}>
        <JobsServicesProvider services={services.jobs}>
          <ApplicationsServicesProvider services={services.applications}>
            <FactsServicesProvider services={services.facts}>
              <DocumentsServicesProvider services={services.documents}>
                <PhotosServicesProvider services={services.photos} cropper={services.cropper}>
                  <MailServicesProvider services={services.mail}>
                    <RepliesServicesProvider services={services.replies}>
                      <SourcesServicesProvider services={services.sources}>
                        <PrepServicesProvider services={services.prep}>
                          <LegalServicesProvider services={services.legal}>
                            <SignupServicesProvider
                              services={services.signup}
                              widget={altchaWidget}
                              challengeUrl={`${apiBase}/auth/challenge`}
                            >
                              <OnboardingServicesProvider services={services.onboarding}>
                                <AgentsServicesProvider services={services.agents}>
                                  <PromptsServicesProvider services={services.prompts}>
                                    <App />
                                  </PromptsServicesProvider>
                                </AgentsServicesProvider>
                              </OnboardingServicesProvider>
                            </SignupServicesProvider>
                          </LegalServicesProvider>
                        </PrepServicesProvider>
                      </SourcesServicesProvider>
                    </RepliesServicesProvider>
                  </MailServicesProvider>
                </PhotosServicesProvider>
              </DocumentsServicesProvider>
            </FactsServicesProvider>
          </ApplicationsServicesProvider>
        </JobsServicesProvider>
      </ProfileServicesProvider>
    </AuthProvider>
  );
}
