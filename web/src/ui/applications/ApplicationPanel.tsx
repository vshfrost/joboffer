import { useEffect, useId, useRef, useState, type ReactNode } from "react";

import type { ChangeApplicationOutcome } from "../../application/applications";
import {
  ATS_LABELS,
  CHANNEL_LABELS,
  draftOf,
  emptyDraft,
  isClosed,
  MOVE_LABELS,
  STATUS_LABELS,
  type Application,
  type ApplicationStatus,
} from "../../domain/applications";
import { REQUESTS } from "../../domain/prompts";
import { DelegateToAgent } from "../agents/DelegateToAgent";
import { Button } from "../components/button";
import { Skeleton } from "../components/skeleton";
import { ApplicationForm } from "./ApplicationForm";
import { useApplicationsServices } from "./ApplicationsServices";
import { CloseDialog, type ClosingStatus } from "./CloseDialog";
import { Reveal } from "./Reveal";
import { StatusBadge } from "./StatusBadge";
import type { ApplicationApi } from "./useApplication";

const WRAP = "[overflow-wrap:anywhere]";
const MOVE_FAILED = "Не вдалося змінити статус. Статус не змінено.";
const NOT_SET = "Не вказано";

/** Закриття (відмова, відкликання) питає підтвердження; решта переходів — одразу. */
function isClosing(status: ApplicationStatus): status is ClosingStatus {
  return status === "rejected" || status === "withdrawn";
}

interface ApplicationPanelProps {
  jobId: number;
  application: ApplicationApi;
}

/** Блок «Подача» в деталях вакансії: статус, лише дозволені переходи, усі дані під розкриттям, форма «Я подався». */
export function ApplicationPanel({ jobId, application }: ApplicationPanelProps) {
  const headingId = useId();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const refocus = useRef(false);
  const [message, setMessage] = useState("");
  const [formOpen, setFormOpen] = useState<"create" | "edit" | null>(null);

  // Після збереження форма зникає разом із фокусом: віддаємо його заголовку блоку.
  useEffect(() => {
    if (refocus.current && formOpen === null) {
      refocus.current = false;
      headingRef.current?.focus();
    }
  });

  function saved(next: Parameters<ApplicationApi["set"]>[0]) {
    application.set(next);
    setFormOpen(null);
    setMessage("Подачу збережено. Заявку роботодавцю не надсилали.");
    refocus.current = true;
  }

  return (
    <section aria-labelledby={headingId} className="min-w-0">
      <h2 id={headingId} ref={headingRef} tabIndex={-1} className="mb-3 text-section font-semibold outline-none">
        Подача
      </h2>
      <div className="flex min-w-0 flex-col gap-3 rounded-xl border border-border bg-card p-5">
        {application.state.status === "loading" ? (
          <div role="status" aria-label="Завантажуємо подачу" aria-busy="true" className="flex flex-col gap-3">
            <Skeleton className="h-6 w-28" />
            <Skeleton className="h-5 w-2/3" />
            <Skeleton className="h-9 w-48" />
          </div>
        ) : null}
        {application.state.status === "error" ? (
          <div role="alert" className="flex flex-wrap items-center gap-3 rounded-lg bg-status-danger p-3 text-status-danger-foreground">
            <div>
              <p className="text-nav font-medium">Не вдалося завантажити подачу.</p>
              <p className="text-caption">Статус не змінено.</p>
            </div>
            <Button variant="secondary" onClick={application.reload}>
              Спробувати подачу ще раз
            </Button>
          </div>
        ) : null}
        {application.state.status === "ready" ? (
          <Ready
            jobId={jobId}
            current={application.state.application}
            formOpen={formOpen}
            setFormOpen={setFormOpen}
            onSaved={saved}
            onMoved={(next, status) => {
              application.set(next);
              setMessage(`Статус змінено: «${STATUS_LABELS[status]}».`);
            }}
            focusHeading={() => headingRef.current?.focus()}
          />
        ) : null}
        <p role="status" aria-label="Результат подачі" className="text-caption font-medium text-status-success-foreground empty:hidden">
          {message}
        </p>
      </div>
    </section>
  );
}

interface ReadyProps {
  jobId: number;
  current: Application | null;
  formOpen: "create" | "edit" | null;
  setFormOpen(open: "create" | "edit" | null): void;
  onSaved(application: Application): void;
  onMoved(application: Application, status: ApplicationStatus): void;
  focusHeading(): void;
}

function Ready({ jobId, current, formOpen, setFormOpen, onSaved, onMoved, focusHeading }: ReadyProps) {
  if (current === null) {
    return formOpen === "create" ? (
      <ApplicationForm jobId={jobId} initial={emptyDraft()} editing={false} onSaved={onSaved} onCancel={() => setFormOpen(null)} />
    ) : (
      <div className="flex flex-col items-start gap-3">
        <div>
          <p className="text-nav font-medium">Подачу ще не зафіксовано</p>
          <p className="text-caption text-muted-foreground">Після відправлення заявки додайте канал і дату.</p>
        </div>
        <DelegateToAgent
          request={REQUESTS.apply(jobId)}
          description="Відкриє вакансію у твоєму браузері, знайде форму подачі й заповнить її. Надсилаєш заявку ти сам."
        />
        <Button onClick={() => setFormOpen("create")}>Я подався</Button>
      </div>
    );
  }
  if (formOpen === "edit") {
    return <ApplicationForm jobId={jobId} initial={draftOf(current)} editing onSaved={onSaved} onCancel={() => setFormOpen(null)} />;
  }
  return <Summary jobId={jobId} application={current} onEdit={() => setFormOpen("edit")} onMoved={onMoved} focusHeading={focusHeading} />;
}

interface SummaryProps {
  jobId: number;
  application: Application;
  onEdit(): void;
  onMoved(application: Application, status: ApplicationStatus): void;
  focusHeading(): void;
}

function Summary({ jobId, application, onEdit, onMoved, focusHeading }: SummaryProps) {
  const services = useApplicationsServices();
  const [pending, setPending] = useState(false);
  const [closing, setClosing] = useState<ClosingStatus | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const busy = useRef(false);
  const closedNow = useRef(false);

  async function move(status: ApplicationStatus) {
    if (busy.current) {
      return;
    }
    busy.current = true;
    setPending(true);
    setFailure(null);
    const outcome = await services.move(jobId, status);
    busy.current = false;
    setPending(false);
    if (outcome.ok) {
      closedNow.current = isClosing(status);
      setClosing(null);
      onMoved(outcome.application, status);
    } else {
      setFailure(problem(outcome));
    }
  }

  function choose(status: ApplicationStatus) {
    if (isClosing(status)) {
      setFailure(null);
      setClosing(status);
    } else {
      void move(status);
    }
  }

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <span className={`font-medium ${WRAP}`}>{CHANNEL_LABELS[application.channel]}</span>
          <p className={`text-caption text-muted-foreground ${WRAP}`}>
            {`Подано ${application.appliedOn}${application.ats === null ? "" : ` · ${ATS_LABELS[application.ats]}`}`}
          </p>
        </div>
        <StatusBadge status={application.status} />
      </div>
      {isClosed(application) ? (
        <p className="text-caption text-muted-foreground">Подачу закрито. Відмови сховано зі списку вакансій, відкликані подачі — на вкладці «У процесі».</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {application.allowedTransitions.map((status) => (
            <Button
              key={status}
              variant={isClosing(status) ? "ghost" : status === "interview" ? "default" : "secondary"}
              size="sm"
              disabled={pending}
              onClick={() => choose(status)}
              className={isClosing(status) ? "text-destructive" : undefined}
            >
              {MOVE_LABELS[status]}
            </Button>
          ))}
        </div>
      )}
      {failure === null || closing !== null ? null : (
        <p role="alert" className="rounded-lg bg-status-danger px-3 py-2 text-caption font-medium text-status-danger-foreground">
          {failure}
        </p>
      )}
      <Reveal label="Усі дані подачі" open={open} onToggle={() => setOpen((current) => !current)}>
        <Details application={application} onEdit={onEdit} />
      </Reveal>
      <CloseDialog
        closing={closing}
        pending={pending}
        failure={failure}
        didClose={() => closedNow.current}
        onConfirm={() => closing !== null && void move(closing)}
        onClose={() => {
          setClosing(null);
          setFailure(null);
        }}
        focusAfterClose={focusHeading}
      />
    </div>
  );
}

function problem(outcome: Exclude<ChangeApplicationOutcome, { ok: true }>): string {
  if (outcome.kind === "invalid") {
    return outcome.message;
  }
  return outcome.kind === "not-found" ? "Подачі нема — онови сторінку." : MOVE_FAILED;
}

function Details({ application, onEdit }: { application: Application; onEdit(): void }) {
  return (
    <div className="mt-1 flex flex-col gap-4">
      <dl className="grid gap-4 sm:grid-cols-2">
        <Row label="Канал">{CHANNEL_LABELS[application.channel]}</Row>
        <Row label="Дата подачі">{application.appliedOn}</Row>
        <Row label="ATS">{application.ats === null ? NOT_SET : ATS_LABELS[application.ats]}</Row>
        <Row label="Домени">{application.companyDomains.length === 0 ? NOT_SET : application.companyDomains.join(", ")}</Row>
        <Row label="Адреси email" wide>
          {application.companyEmails.length === 0 ? NOT_SET : application.companyEmails.join(", ")}
        </Row>
      </dl>
      <div>
        <Button variant="secondary" size="sm" onClick={onEdit}>
          Змінити дані
        </Button>
      </div>
    </div>
  );
}

function Row({ label, wide = false, children }: { label: string; wide?: boolean; children: ReactNode }) {
  return (
    <div className={`flex min-w-0 flex-col gap-0.5 ${wide ? "sm:col-span-2" : ""}`}>
      <dt className="text-caption text-muted-foreground">{label}</dt>
      <dd className={WRAP}>{children}</dd>
    </div>
  );
}
