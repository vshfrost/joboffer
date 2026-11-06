import { Link, useLocation } from "react-router";

import { VERDICT_LABELS, type TriageVerdict } from "../../domain/analysis";
import { jobTitle, madridDay, type JobSummary } from "../../domain/jobs";
import { StatusBadge } from "../applications/StatusBadge";
import { Badge } from "../components/badge";
import { Button } from "../components/button";
import { cn } from "../lib/cn";

/** Перенос довгих слів без обрізання змісту: повну назву видно завжди. */
const WRAP = "[overflow-wrap:anywhere]";

interface RowsProps {
  items: readonly JobSummary[];
  onHide(job: JobSummary): void;
  onRestore(job: JobSummary): void;
}

function useDetailsLink() {
  const { search } = useLocation();
  return (id: number) => ({ pathname: `/vacancies/${id}`, search });
}

function TitleLink({ job }: { job: JobSummary }) {
  const details = useDetailsLink();
  return (
    <Link to={details(job.id)} data-job-link={job.id} className={cn("min-w-0 font-medium text-foreground underline-offset-4 hover:underline", WRAP)}>
      {jobTitle(job)}
    </Link>
  );
}

function Company({ job }: { job: JobSummary }) {
  return <span className={cn(job.company === null && "text-muted-foreground", WRAP)}>{job.company ?? "Не вказано"}</span>;
}

function WaitingBadge({ job }: { job: JobSummary }) {
  return job.needsText ? <Badge tone="warning">Потрібен текст</Badge> : null;
}

/** Вакансія з джерела, яку ще не відкривали. */
function NewBadge({ job }: { job: JobSummary }) {
  return job.isNew ? <Badge tone="success">нове</Badge> : null;
}

/** Статус подачі текстом; вакансія без подачі його не має. */
function ApplicationBadge({ job }: { job: JobSummary }) {
  return job.status === null ? null : <StatusBadge status={job.status} />;
}

const VERDICT_TONES = { analyse: "success", maybe: "warning", skip: "neutral" } as const satisfies Record<TriageVerdict, string>;

/** Швидкий тріаж: вердикт словами й підписаний скор (вердикт без скору сервер не віддає); тріаж не є повним аналізом. */
function TriageCell({ job }: { job: JobSummary }) {
  if (job.triageVerdict === null) {
    return <span className="text-muted-foreground">Без тріажу</span>;
  }
  return (
    <div className="flex flex-col items-start gap-1">
      <Badge tone={VERDICT_TONES[job.triageVerdict]}>{VERDICT_LABELS[job.triageVerdict]}</Badge>
      <span className="tabular text-caption text-muted-foreground">{`Тріаж ${Number(job.triageScore)}/100`}</span>
    </div>
  );
}

/** Повний аналіз: підписаний скор (0 — теж оцінка) і «Не підходить», якщо фільтри профілю не пройдено. */
function AnalysisCell({ job }: { job: JobSummary }) {
  if (job.score === null) {
    return <span className="text-muted-foreground">Не проаналізовано</span>;
  }
  return (
    <div className="flex flex-col items-start gap-1">
      <span className="tabular font-medium">{`Аналіз ${job.score}%`}</span>
      {job.filtersPassed === false ? <Badge tone="danger">Не підходить</Badge> : null}
    </div>
  );
}

function CompanyAndSource({ job }: { job: JobSummary }) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <Company job={job} /> <span className={cn("text-caption text-muted-foreground", WRAP)}>{job.source}</span>
    </div>
  );
}

function RowAction({ job, onHide, onRestore, align }: { job: JobSummary; align: "start" | "end" } & Pick<RowsProps, "onHide" | "onRestore">) {
  const title = jobTitle(job);
  if (job.status !== null && !job.dismissed) {
    // Поданих вакансій не ховають: кнопка недоступна, причину видно поруч.
    return (
      <div className={cn("flex flex-col gap-1", align === "end" ? "items-end" : "items-start")}>
        <Button variant="secondary" size="sm" disabled aria-label={`Не цікаво: ${title}`}>
          Не цікаво
        </Button>
        <span className="text-caption text-muted-foreground">Є подача — не ховається</span>
      </div>
    );
  }
  return job.dismissed ? (
    <Button variant="secondary" size="sm" aria-label={`Повернути: ${title}`} onClick={() => onRestore(job)}>
      Повернути
    </Button>
  ) : (
    <Button variant="secondary" size="sm" aria-label={`Не цікаво: ${title}`} onClick={() => onHide(job)}>
      Не цікаво
    </Button>
  );
}

/** Desktop: таблиця. Назва — посилання на деталі; довгі значення переносяться. */
export function JobsTable({ items, onHide, onRestore }: RowsProps) {
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card">
      <table aria-label="Вакансії" className="w-full table-fixed border-collapse text-left text-sm">
        <thead className="bg-muted text-caption text-muted-foreground">
          <tr>
            <th scope="col" className="w-[26%] px-3 py-2.5 font-medium">
              Посада
            </th>
            <th scope="col" className="w-[17%] px-3 py-2.5 font-medium">
              Компанія
            </th>
            <th scope="col" className="w-[15%] px-3 py-2.5 font-medium">
              Тріаж
            </th>
            <th scope="col" className="w-[16%] px-3 py-2.5 font-medium">
              Аналіз
            </th>
            <th scope="col" className="tabular w-[11%] px-3 py-2.5 font-medium">
              Додано
            </th>
            <th scope="col" className="w-[15%] px-3 py-2.5 text-right font-medium">
              <span className="sr-only">Дія</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((job) => (
            <tr key={job.id} className="border-t border-border align-top">
              <td className="min-w-0 px-3 py-3.5">
                <div className="flex flex-col items-start gap-1.5">
                  <TitleLink job={job} />
                  <NewBadge job={job} />
          <WaitingBadge job={job} />
                  <ApplicationBadge job={job} />
                </div>
              </td>
              <td className="min-w-0 px-3 py-3.5">
                <CompanyAndSource job={job} />
              </td>
              <td className="min-w-0 px-3 py-3.5">
                <TriageCell job={job} />
              </td>
              <td className="min-w-0 px-3 py-3.5">
                <AnalysisCell job={job} />
              </td>
              <td className="tabular px-3 py-3.5 whitespace-nowrap text-muted-foreground">{madridDay(job.createdAt)}</td>
              <td className="px-3 py-3 text-right">
                <RowAction job={job} onHide={onHide} onRestore={onRestore} align="end" />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Mobile: ті самі дані карточками. */
export function JobCards({ items, onHide, onRestore }: RowsProps) {
  return (
    <ul aria-label="Вакансії" className="flex flex-col gap-3">
      {items.map((job) => (
        <li key={job.id} className="flex min-w-0 flex-col gap-2 rounded-xl border border-border bg-card p-4">
          <TitleLink job={job} />
          <NewBadge job={job} />
          <WaitingBadge job={job} />
          <ApplicationBadge job={job} />
          <p className="text-sm">
            <Company job={job} />
          </p>
          <p className={cn("tabular text-caption text-muted-foreground", WRAP)}>
            {job.source} · {madridDay(job.createdAt)}
          </p>
          <div className="flex flex-wrap items-start gap-x-6 gap-y-2">
            <TriageCell job={job} />
            <AnalysisCell job={job} />
          </div>
          <div className="mt-1">
            <RowAction job={job} onHide={onHide} onRestore={onRestore} align="start" />
          </div>
        </li>
      ))}
    </ul>
  );
}
