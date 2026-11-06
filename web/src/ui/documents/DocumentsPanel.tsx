import { Link } from "react-router";

import { splitByKind } from "../../domain/documents";
import { Button } from "../components/button";
import { Skeleton } from "../components/skeleton";
import { DocumentCard } from "./DocumentCard";
import { useJobDocuments, type DocumentsProblem } from "./useJobDocuments";

const MESSAGES: Record<Exclude<DocumentsProblem, "unavailable">, string> = {
  unauthorized: "Сесія завершилась. Увійди знову, щоб побачити документи.",
  forbidden: "Немає доступу до документів цієї вакансії.",
  "not-found": "Документи недоступні: вакансію не знайдено.",
};

interface DocumentsPanelProps {
  jobId: number;
  /** Чи можна готувати документ: вакансія має текст опису. */
  canRequest: boolean;
}

/** Блок «Документи» в деталях вакансії: дві картки — CV і Cover letter. Лише читає; нові версії готує Claude. */
export function DocumentsPanel({ jobId, canRequest }: DocumentsPanelProps) {
  const { state, reload } = useJobDocuments(jobId);
  if (state.status === "loading") {
    return (
      <div role="status" aria-label="Завантажуємо документи" aria-busy="true" className="grid gap-4 md:grid-cols-2">
        <Skeleton className="h-52 w-full" />
        <Skeleton className="h-52 w-full" />
      </div>
    );
  }
  if (state.status === "error") {
    return (
      <div role="alert" className="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-status-danger p-4 text-status-danger-foreground">
        {state.problem === "unavailable" ? (
          <>
            <div>
              <p className="text-nav font-medium">Не вдалося завантажити документи.</p>
              <p className="text-caption">Збережені версії не змінено.</p>
            </div>
            <Button variant="secondary" onClick={reload}>
              Спробувати документи ще раз
            </Button>
          </>
        ) : (
          <>
            <p className="text-nav font-medium">{MESSAGES[state.problem]}</p>
            {state.problem === "unauthorized" ? (
              <Button asChild variant="secondary">
                <Link to="/login">Увійти</Link>
              </Button>
            ) : null}
          </>
        )}
      </div>
    );
  }
  const versions = splitByKind(state.documents);
  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 md:grid-cols-2">
        <DocumentCard kind="cv" jobId={jobId} versions={versions.cv} canRequest={canRequest} />
        <DocumentCard kind="cl" jobId={jobId} versions={versions.cl} canRequest={canRequest} />
      </div>
      <p className="text-caption text-muted-foreground">
        «Остання» означає найновішу збережену версію, а не позначку про відправлення. Зауваження ATS не блокують відкриття PDF.
      </p>
    </div>
  );
}
