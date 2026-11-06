import { FileText } from "lucide-react";
import { useId } from "react";

import {
  atsBadge,
  atsStatus,
  KIND_LABELS,
  keywordSummary,
  madridDateTime,
  pagesText,
  photoMark,
  type DocumentKind,
  type DocumentsOfKind,
  type JobDocument,
} from "../../domain/documents";
import { REQUESTS } from "../../domain/prompts";
import { DelegateToAgent } from "../agents/DelegateToAgent";
import { Badge } from "../components/badge";
import { AtsReport } from "./AtsReport";
import { Disclosure } from "./Disclosure";
import { PdfAccess } from "./PdfAccess";

const WRAP = "[overflow-wrap:anywhere]";
const HISTORY_STATUS = { passed: "ATS: пройдено", issues: "ATS: є зауваження", "no-report": "Немає звіту ATS" } as const;

interface DocumentCardProps {
  kind: DocumentKind;
  jobId: number;
  versions: DocumentsOfKind;
  canRequest: boolean;
}

/** Картка одного виду документа: остання версія, її ATS-статус і запит нової версії; історія — у disclosure. */
export function DocumentCard({ kind, jobId, versions, canRequest }: DocumentCardProps) {
  const headingId = useId();
  const { latest, history } = versions;
  return (
    <section aria-labelledby={headingId} className="flex min-w-0 flex-col gap-4 rounded-xl border border-border bg-card p-5">
      <div className="flex items-center justify-between gap-2">
        <h3 id={headingId} className="text-section font-semibold">
          {KIND_LABELS[kind]}
        </h3>
        {latest === null ? null : <Badge tone="info">{`v${latest.version} · остання`}</Badge>}
      </div>
      {latest === null ? <Empty kind={kind} jobId={jobId} canRequest={canRequest} /> : <Latest kind={kind} jobId={jobId} document={latest} />}
      {history.length === 0 ? null : <History documents={history} />}
    </section>
  );
}

function Empty({ kind, jobId, canRequest }: { kind: DocumentKind; jobId: number; canRequest: boolean }) {
  return (
    <div className="flex flex-col gap-3">
      <p className="text-section font-semibold">{`${KIND_LABELS[kind]} ще немає`}</p>
      {canRequest ? (
        <DelegateToAgent request={REQUESTS.document(kind, jobId)} description={`Агент підготує ${KIND_LABELS[kind]} на основі аналізу вакансії та підтверджених фактів.`} />
      ) : (
        <p className="text-caption text-muted-foreground">Спершу додай текст вакансії — без нього документ не підготувати.</p>
      )}
    </div>
  );
}

function Latest({ kind, jobId, document }: { kind: DocumentKind; jobId: number; document: JobDocument }) {
  const badge = atsBadge(document.lint);
  const photo = photoMark(document);
  return (
    <>
      <span className="inline-flex w-fit rounded-lg bg-accent p-2 text-primary">
        <FileText aria-hidden="true" className="size-5" />
      </span>
      <p className={`text-sm font-medium ${WRAP}`}>{document.fileName}</p>
      <p className="text-caption text-muted-foreground">
        {document.lint === null ? null : <span className="block">{pagesText(document.lint.pages)}</span>}
        <span className="block">{`${madridDateTime(document.createdAt)} · Мадрид`}</span>
        {photo === null ? null : <span className="block">{photo}</span>}
      </p>
      <div>
        <PdfAccess document={document} />
      </div>
      <div className="flex min-w-0 flex-col gap-1 border-t border-border pt-4">
        <Badge tone={badge.tone}>{badge.text}</Badge>
        <p className={`text-caption text-muted-foreground ${WRAP}`}>{keywordSummary(document.lint)}</p>
        <AtsReport lint={document.lint} />
      </div>
      <DelegateToAgent request={REQUESTS.document(kind, jobId)} description="Агент підготує нову версію за актуальним аналізом і підтвердженими фактами." />
    </>
  );
}

function History({ documents }: { documents: JobDocument[] }) {
  return (
    <Disclosure label={`Попередні версії · ${documents.length}`} className="border-t border-border pt-1">
      <div className="flex flex-col">
        {documents.map((document) => (
          <div key={document.id} data-version={document.version} className="flex min-w-0 flex-col border-b border-border py-3 last:border-b-0">
            <div className="flex items-center justify-between gap-2">
              <div className="flex min-w-0 flex-col text-caption">
                <b>{`Версія ${document.version}`}</b>
                <small className="text-muted-foreground">{madridDateTime(document.createdAt)}</small>
                <small className="text-muted-foreground">{HISTORY_STATUS[atsStatus(document.lint)]}</small>
              </div>
              <PdfAccess document={document} compact />
            </div>
            <AtsReport lint={document.lint} />
          </div>
        ))}
      </div>
    </Disclosure>
  );
}
