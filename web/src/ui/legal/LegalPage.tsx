import { CircleAlert } from "lucide-react";
import { useCallback } from "react";
import { Link } from "react-router";

import { LEGAL_TITLES, type LegalDoc } from "../../domain/legal";
import { Button } from "../components/button";
import { usePageTitle } from "../lib/usePageTitle";
import { useLoaded } from "../prep/useLoaded";
import { PageHeading } from "../pages/PageHeading";
import { useLegalServices } from "./LegalServices";

const PROBLEMS = {
  "not-found": "Документ не знайдено.",
  unavailable: "Не вдалося завантажити текст. Спробуй ще раз.",
} as const;

/** Публічна сторінка документа (без сесії): текст виводиться як текст, абзаци зберігаються. */
export function LegalPage({ doc }: { doc: LegalDoc }) {
  const title = LEGAL_TITLES[doc];
  usePageTitle(title);
  const { document } = useLegalServices();
  const load = useCallback(() => document(doc), [document, doc]);
  const { state, reload } = useLoaded(load);

  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-8 md:px-6">
      <div className="mb-6 flex items-center gap-2.5">
        <img src={`${import.meta.env.BASE_URL}brand/logo.svg`} alt="" width={32} height={32} className="size-8" />
        <span className="text-2xl font-semibold tracking-tight">joboffer</span>
      </div>
      <PageHeading title={title} subtitle={state.status === "ready" ? `Версія ${state.data.version}` : undefined} />
      {state.status === "loading" ? (
        <p role="status" className="text-nav text-muted-foreground">
          Завантаження…
        </p>
      ) : null}
      {state.status === "error" ? (
        <div
          role="alert"
          className="flex flex-col items-start gap-3 rounded-lg bg-status-danger px-3 py-2 text-caption text-status-danger-foreground"
        >
          <span className="flex items-start gap-2">
            <CircleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
            {PROBLEMS[state.problem]}
          </span>
          {state.problem === "unavailable" ? (
            <Button variant="secondary" size="sm" onClick={reload}>
              Спробувати ще раз
            </Button>
          ) : null}
        </div>
      ) : null}
      {state.status === "ready" ? (
        <div data-testid="legal-text" className="rounded-xl border border-border bg-card p-4 text-sm leading-relaxed break-words whitespace-pre-wrap md:p-6">
          {state.data.text}
        </div>
      ) : null}
      <Link to="/" className="mt-6 inline-block text-nav font-medium text-primary hover:underline">
        На головну
      </Link>
    </main>
  );
}
