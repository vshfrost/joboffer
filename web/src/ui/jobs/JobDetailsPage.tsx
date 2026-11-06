import { ArrowLeft } from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router";

import { jobTitle, madridDay, parseJobNumber, type Job } from "../../domain/jobs";
import { Badge } from "../components/badge";
import { Button } from "../components/button";
import { Skeleton } from "../components/skeleton";
import { ApplicationPanel } from "../applications/ApplicationPanel";
import { useApplication } from "../applications/useApplication";
import { DocumentsPanel } from "../documents/DocumentsPanel";
import { usePageTitle } from "../lib/usePageTitle";
import { PageHeading } from "../pages/PageHeading";
import { AnalysisTabs, Fit } from "./AnalysisPanel";
import { DismissDialog, type DismissTarget } from "./DismissDialog";
import { InterviewKitBlock } from "./InterviewKitBlock";
import { JobPrepBlock } from "./JobPrepBlock";
import { useJobsServices } from "./JobsServices";
import { noticeOf } from "./navigationState";
import { useOpenedJob } from "./OpenedJob";
import { TriageNote } from "./TriageNote";
import { useAnalysis } from "./useAnalysis";
import { useJob } from "./useJob";

const WRAP = "[overflow-wrap:anywhere]";
const RESTORE_FAILED = "Не вдалося повернути вакансію. Спробуй ще раз.";

export function JobDetailsPage() {
  const params = useParams();
  const id = parseJobNumber(params["jobId"]);
  const { state, reload, refresh } = useJob(id);
  const opened = useOpenedJob();
  const { search, state: navigationState } = useLocation();
  const back = `/vacancies${search}`;
  const notice = noticeOf(navigationState);

  useEffect(() => {
    if (id !== null) {
      opened.remember(id);
    }
  }, [id, opened]);

  const title = state.status === "ready" ? jobTitle(state.job) : state.status === "not-found" ? "Вакансію не знайдено" : "Вакансія";
  usePageTitle(`${title} · Вакансії`);
  useEscapeToList(back);

  if (state.status === "not-found") {
    return (
      <>
        <PageHeading title="Вакансію не знайдено" subtitle="Такої вакансії нема." />
        <Button asChild>
          <Link to={back}>Усі вакансії</Link>
        </Button>
      </>
    );
  }
  return (
    <>
      <Link to={back} className="mb-6 inline-flex items-center gap-2 text-nav font-medium text-muted-foreground hover:text-foreground">
        <ArrowLeft aria-hidden="true" className="size-4" />
        Усі вакансії
      </Link>
      {notice === null ? null : (
        <p role="status" aria-label="Повідомлення" className="mb-6 w-fit rounded-lg bg-status-success px-3 py-2 text-caption font-medium text-status-success-foreground">
          {notice}
        </p>
      )}
      {state.status === "loading" ? <DetailsSkeleton /> : null}
      {state.status === "error" ? (
        <div role="alert" className="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-status-danger p-4 text-status-danger-foreground">
          <p className="text-nav font-medium">Не вдалося завантажити вакансію.</p>
          <Button variant="secondary" onClick={reload}>
            Спробувати ще раз
          </Button>
        </div>
      ) : null}
      {state.status === "ready" ? <Details job={state.job} refresh={refresh} search={search} /> : null}
    </>
  );
}

/** Escape повертає до списку, але не заважає діалогам і полям, що самі його опрацювали. */
function useEscapeToList(back: string) {
  const navigate = useNavigate();
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && !event.defaultPrevented && document.querySelector('[role="alertdialog"]') === null) {
        void navigate(back);
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [back, navigate]);
}

function Details({ job, refresh, search }: { job: Job; refresh(): Promise<void>; search: string }) {
  const services = useJobsServices();
  const [target, setTarget] = useState<DismissTarget | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const dismissed = job.dismissedAt !== null;
  const analysis = useAnalysis(job.id, !job.needsText);
  const application = useApplication(job.id);
  // Поданих не ховають; поки подачу не завантажено, її наявність невідома.
  const applied = application.state.status === "ready" && application.state.application !== null;
  const hideBlocked = application.state.status !== "ready" || applied;

  async function restore() {
    setFailure(null);
    const outcome = await services.restore(job.id);
    if (outcome.ok) {
      await refresh();
    } else {
      setFailure(RESTORE_FAILED);
    }
  }

  return (
    <article className="flex flex-col gap-8">
      <header className="flex flex-col gap-3">
        {job.company === null ? null : <p className={`text-nav text-muted-foreground ${WRAP}`}>{job.company}</p>}
        <h1 ref={headingRef} tabIndex={-1} className={`text-page-title font-semibold tracking-tight outline-none ${WRAP}`}>{jobTitle(job)}</h1>
        <div className="flex flex-wrap items-center gap-2">
          {job.needsText ? <Badge tone="warning">Потрібен текст</Badge> : null}
          {dismissed ? <Badge tone="neutral">{`Сховано: ${job.dismissReason ?? ""}`}</Badge> : null}
        </div>
        <dl className="flex flex-wrap gap-x-8 gap-y-2 text-sm">
          {job.location === null ? null : <Fact label="Локація">{job.location}</Fact>}
          <Fact label="Джерело">{job.source}</Fact>
          <Fact label="Додано">
            <span className="tabular">{madridDay(job.createdAt)}</span>
          </Fact>
          {job.url === null ? null : (
            <Fact label="Посилання">
              <a href={job.url} target="_blank" rel="noopener noreferrer" className={`text-primary underline underline-offset-4 ${WRAP}`}>
                {job.url}
              </a>
            </Fact>
          )}
        </dl>
        {job.triage === null ? null : <TriageNote triage={job.triage} />}
        <div>
          {dismissed ? (
            <Button variant="secondary" onClick={() => void restore()}>
              Повернути
            </Button>
          ) : (
            <Button variant="secondary" disabled={hideBlocked} onClick={() => setTarget({ id: job.id, title: jobTitle(job) })}>
              Не цікаво
            </Button>
          )}
          {applied && !dismissed ? (
            <p className="mt-2 text-caption text-muted-foreground">Є подача — вакансію не ховають. Керуй нею через статус подачі.</p>
          ) : null}
        </div>
        {failure === null ? null : (
          <p role="alert" className="rounded-lg bg-status-danger px-3 py-2 text-caption font-medium text-status-danger-foreground">
            {failure}
          </p>
        )}
      </header>
      <div className="flex flex-col gap-8 border-t border-border pt-8">
        <ApplicationPanel jobId={job.id} application={application} />
        <Section title="Відповідність профілю">
          <Fit job={job} state={analysis.state} onRetry={analysis.reload} />
        </Section>
        <Section title="Документи">
          <DocumentsPanel jobId={job.id} canRequest={!job.needsText} />
        </Section>
        <JobPrepBlock jobId={job.id} analysis={analysis.state.status} />
        <InterviewKitBlock jobId={job.id} />
      </div>
      {analysis.state.status === "ready" ? <AnalysisTabs job={job} analysis={analysis.state.analysis} /> : null}
      {analysis.state.status === "loading" ? null : analysis.state.status === "ready" ? null : job.text === null ? (
        <div className="flex max-w-prose flex-col items-start gap-3 rounded-xl border border-border bg-status-warning p-4 text-sm text-status-warning-foreground">
          <p>Опису ще нема. Відкрий вакансію в LinkedIn, скопіюй текст опису й додай вакансію з тим самим посиланням — текст допишеться сюди.</p>
          {job.url === null ? null : (
            <Button asChild variant="secondary" size="sm">
              <Link to={{ pathname: "/vacancies/new", search }} state={{ url: job.url }}>
                Додати текст опису
              </Link>
            </Button>
          )}
        </div>
      ) : (
        <section aria-labelledby="about-role" className="border-t border-border pt-8">
          <h2 id="about-role" className="mb-3 text-section font-semibold">
            Про роль
          </h2>
          <div className={`max-w-prose whitespace-pre-wrap ${WRAP}`}>{job.text}</div>
        </section>
      )}
      <DismissDialog
        target={target}
        onClose={() => setTarget(null)}
        onDismissed={() => {
          setTarget(null);
          void refresh();
        }}
        focusAfterDismiss={() => headingRef.current?.focus()}
        onApplied={application.reload}
      />
    </article>
  );
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <dt className="text-caption text-muted-foreground">{label}</dt>
      <dd className={WRAP}>{children}</dd>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  const id = useId();
  return (
    <section aria-labelledby={id} className="min-w-0">
      <h2 id={id} className="mb-3 text-section font-semibold">
        {title}
      </h2>
      {children}
    </section>
  );
}

function DetailsSkeleton() {
  return (
    <div role="status" aria-label="Завантажуємо вакансію" aria-busy="true" className="flex flex-col gap-4">
      <Skeleton className="h-4 w-32" />
      <Skeleton className="h-9 w-2/3" />
      <Skeleton className="h-4 w-1/3" />
      <Skeleton className="h-40 w-full" />
    </div>
  );
}
