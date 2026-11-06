import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";

// SPA живе в корені origin; API — тим самим origin під /api.
export default defineConfig(({ mode }) => {
  // API_PROXY_TARGET: compose дає http://app:8797; scripts/web.sh run dev — хост машини.
  // AGENT_PROXY_TARGET — агент (MCP + OAuth): у dev, як і в проді, він на тому ж origin, що й веб.
  const env = loadEnv(mode, ".", "");
  const agent = { target: env.AGENT_PROXY_TARGET ?? "http://host.docker.internal:8798" };
  return {
    base: "/",
    plugins: [react(), tailwindcss()],
    server: {
      host: "0.0.0.0",
      port: 5174,
      strictPort: true,
      proxy: {
        "/api": {
          target: env.API_PROXY_TARGET ?? "http://host.docker.internal:8797",
          rewrite: (path) => path.replace(/^\/api/, ""),
        },
        "/mcp": agent,
        "/.well-known/oauth-protected-resource": agent,
        "/.well-known/oauth-authorization-server": agent,
      },
    },
    build: {
      outDir: "dist",
      sourcemap: true,
      // Воркер ALTCHA (< 4 КБ) Vite інакше вкладає як data:-URL, а CSP дозволяє воркери лише з 'self' і blob:.
      assetsInlineLimit: (filePath) => (filePath.endsWith("/altcha/dist_external/worker.js") ? false : undefined),
    },
    test: {
      environment: "jsdom",
      setupFiles: ["./vitest.setup.ts"],
      // theme.test.ts читає theme.css сирим текстом (?raw); без цього Vitest підміняє CSS порожнім рядком.
      css: { include: [/theme\.css\?raw$/] },
      // Покриття міряється для профілю (рішення власника 2026-10-21), для тріажу й аналізу вакансій (B6), документів (B7), пошти і відповідей (B9), джерел (K47), підготовки (K54), юридичних сторінок (K62), перших кроків і popover (K64), реєстрації (K60), агентів і кнопок запитів (K71), текстів запитів із сервера:
      // поріг 100 % у CI (`--coverage`).
      coverage: {
        provider: "v8",
        include: [
          "src/domain/profile*.ts",
          "src/application/profile.ts",
          "src/infrastructure/httpProfileApi.ts",
          "src/ui/profile/**",
          "src/ui/components/{alert-dialog,checkbox,field,textarea}.tsx",
          "src/domain/analysis.ts",
          "src/domain/jobs.ts",
          "src/application/jobs.ts",
          "src/infrastructure/httpJobsApi.ts",
          "src/ui/jobs/{AnalysisPanel,MatchScore,TriageNote,useAnalysis,filters,FilterControls,TabBadge,JobRows,JobPrepBlock,InterviewKitBlock,usePrepExpanded}.{ts,tsx}",
          "src/domain/applications*.ts",
          "src/application/applications.ts",
          "src/infrastructure/httpApplicationsApi.ts",
          "src/ui/applications/**",
          "src/domain/documents*.ts",
          "src/application/documents.ts",
          "src/infrastructure/httpDocumentsApi.ts",
          "src/ui/documents/**",
          "src/domain/photos*.ts",
          "src/application/photos.ts",
          "src/infrastructure/httpPhotosApi.ts",
          "src/ui/photos/**",
          "src/domain/mail*.ts",
          "src/application/mail.ts",
          "src/infrastructure/httpMailApi.ts",
          "src/ui/mail/**",
          "src/domain/replies*.ts",
          "src/application/replies.ts",
          "src/infrastructure/httpRepliesApi.ts",
          "src/ui/replies/**",
          "src/domain/sources*.ts",
          "src/application/sources.ts",
          "src/infrastructure/httpSourcesApi.ts",
          "src/ui/sources/**",
          "src/domain/prep*.ts",
          "src/application/prep.ts",
          "src/infrastructure/httpPrepApi.ts",
          "src/ui/prep/**",
          "src/ui/components/tooltip.tsx",
          "src/domain/legal*.ts",
          "src/application/legal.ts",
          "src/infrastructure/httpLegalApi.ts",
          "src/ui/legal/**",
          "src/domain/signup*.ts",
          "src/application/signup.ts",
          "src/infrastructure/httpSignupApi.ts",
          "src/ui/signup/**",
          "src/domain/onboarding*.ts",
          "src/application/onboarding.ts",
          "src/infrastructure/httpOnboardingApi.ts",
          "src/ui/onboarding/**",
          "src/ui/components/popover.tsx",
          "src/domain/agents*.ts",
          "src/application/agents.ts",
          "src/infrastructure/httpAgentsApi.ts",
          "src/ui/agents/**",
          "src/domain/prompts*.ts",
          "src/application/prompts.ts",
          "src/infrastructure/httpPromptsApi.ts",
          "src/ui/prompts/**",
        ],
        exclude: ["**/*.test.{ts,tsx}"],
        reporter: ["text"],
        thresholds: { lines: 100, functions: 100, branches: 100, statements: 100 },
      },
    },
  };
});
