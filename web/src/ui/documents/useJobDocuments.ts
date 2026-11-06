import { useCallback, useEffect, useState } from "react";

import type { JobDocument } from "../../domain/documents";
import { useDocumentsServices } from "./DocumentsServices";

export type DocumentsProblem = "unauthorized" | "forbidden" | "not-found" | "unavailable";

export type DocumentsState = { status: "loading" } | { status: "error"; problem: DocumentsProblem } | { status: "ready"; documents: JobDocument[] };

export interface JobDocumentsApi {
  state: DocumentsState;
  reload(): void;
}

/** Версії документів вакансії. Лише читає: нові версії готує Claude через MCP, не цей хук. */
export function useJobDocuments(jobId: number): JobDocumentsApi {
  const services = useDocumentsServices();
  const [state, setState] = useState<DocumentsState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });
    void services.load(jobId).then((outcome) => {
      if (cancelled) {
        return;
      }
      setState(outcome.ok ? { status: "ready", documents: outcome.documents } : { status: "error", problem: outcome.kind });
    });
    return () => {
      cancelled = true;
    };
  }, [services, jobId, attempt]);

  const reload = useCallback(() => setAttempt((current) => current + 1), []);
  return { state, reload };
}
