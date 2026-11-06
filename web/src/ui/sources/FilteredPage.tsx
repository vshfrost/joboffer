import { useId, useState } from "react";
import { Link } from "react-router";

import { FILTERED_REASON_TEXT, hideTitle, type FilteredJob } from "../../domain/sources";
import { AlertDialog, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogTitle } from "../components/alert-dialog";
import { Button } from "../components/button";
import { Checkbox } from "../components/checkbox";
import { Skeleton } from "../components/skeleton";
import { usePageTitle } from "../lib/usePageTitle";
import { PageHeading } from "../pages/PageHeading";
import { useSourcesServices } from "./SourcesServices";
import { problemText } from "./texts";
import { useFilteredJobs } from "./useFilteredJobs";

const ALERT = "flex flex-wrap items-center gap-3 rounded-xl border border-border bg-status-danger p-4 text-status-danger-foreground";
const CHANGED = "Список змінився: нічого не приховано. Перевір актуальний список і вибери вакансії знову.";

/** `/sources/filtered`: «Уже не проходять фільтр» — вакансії з джерел, які поточний профіль уже не взяв би; вибрані ховаються після підтвердження. */
export function FilteredPage() {
  usePageTitle("Уже не проходять фільтр");
  const services = useSourcesServices();
  const { state, reload, refetch, remove } = useFilteredJobs();
  const [picked, setPicked] = useState<readonly number[]>([]);
  const [confirming, setConfirming] = useState(false);
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState("");

  async function hide(numbers: readonly number[]) {
    setPending(true);
    const outcome = await services.dismiss(numbers);
    setPending(false);
    setConfirming(false);
    if (outcome.ok) {
      remove(numbers);
      setPicked([]);
      setMessage("Вибрані вакансії приховано.");
    } else if (outcome.kind === "changed") {
      setPicked([]);
      setMessage(CHANGED);
      await refetch();
    } else {
      setMessage(problemText(outcome.kind, "приховати вакансії", "Не вдалося приховати вакансії. Спробуй ще раз."));
    }
  }

  return (
    <>
      <Button asChild variant="secondary" className="mb-4">
        <Link to="/sources">← До джерел</Link>
      </Button>
      <PageHeading title="Уже не проходять фільтр" subtitle="Лише вакансії з джерел, без аналізу й подачі. Приховані зберігаються в базі." />
      <div className="flex flex-col gap-4">
        {state.status === "loading" ? (
          <div role="status" aria-label="Завантажуємо вакансії" className="flex flex-col gap-3">
            <Skeleton className="h-16" />
            <Skeleton className="h-16" />
            <Skeleton className="h-16" />
          </div>
        ) : state.status === "error" ? (
          <div role="alert" className={ALERT}>
            <p className="text-nav font-medium">{problemText(state.problem, "побачити вакансії", "Не вдалося завантажити вакансії.")}</p>
            {state.problem === "unavailable" ? (
              <Button type="button" variant="secondary" onClick={reload}>
                Спробувати ще раз
              </Button>
            ) : null}
          </div>
        ) : state.jobs.length === 0 ? (
          <div className="flex flex-col items-center gap-2 rounded-xl border border-border bg-card px-4 py-12 text-center">
            <h2 className="text-section font-semibold">Список порожній</h2>
            <p className="text-caption text-muted-foreground">Усі вакансії з джерел проходять фільтр профілю.</p>
          </div>
        ) : (
          <Picker jobs={state.jobs} picked={picked} onPick={setPicked} onHide={() => setConfirming(true)} />
        )}
        <p role="status" aria-label="Результат" className="min-h-6 text-caption font-medium text-primary empty:hidden">
          {message}
        </p>
      </div>
      <AlertDialog open={confirming} onOpenChange={setConfirming}>
        <AlertDialogContent>
          <div className="flex flex-col gap-4">
            <div>
              <AlertDialogTitle>{hideTitle(picked.length)}</AlertDialogTitle>
              <AlertDialogDescription>Вакансії зникнуть з основного списку з причиною «фільтр профілю». Дані залишаться в базі.</AlertDialogDescription>
            </div>
            <div className="flex flex-wrap justify-end gap-2">
              <AlertDialogCancel asChild>
                <Button type="button" variant="secondary">
                  Скасувати
                </Button>
              </AlertDialogCancel>
              <Button type="button" disabled={pending} onClick={() => void hide(picked)}>
                Так, приховати
              </Button>
            </div>
          </div>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

interface PickerProps {
  jobs: readonly FilteredJob[];
  picked: readonly number[];
  onPick(numbers: readonly number[]): void;
  onHide(): void;
}

/** Перелік з чекбоксами, «Вибрати всі» і кнопкою «Приховати вибрані · N» (неактивна, поки нічого не вибрано). Номери йдуть у порядку переліку. */
function Picker({ jobs, picked, onPick, onHide }: PickerProps) {
  const allId = useId();
  const all = picked.length === jobs.length;
  const toggle = (number: number, checked: boolean) => onPick(jobs.map((job) => job.number).filter((candidate) => (candidate === number ? checked : picked.includes(candidate))));
  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 pointer-coarse:min-h-11">
          <Checkbox id={allId} checked={all} onCheckedChange={(checked) => onPick(checked === true ? jobs.map((job) => job.number) : [])} />
          <label htmlFor={allId} className="text-nav font-medium">{`Вибрати всі · ${jobs.length}`}</label>
        </div>
        <span className="text-caption text-muted-foreground">{`Вибрано: ${picked.length}`}</span>
      </div>
      <ul className="overflow-hidden rounded-xl border border-border bg-card">
        {jobs.map((job) => (
          <JobRow key={job.number} job={job} checked={picked.includes(job.number)} onChange={(checked) => toggle(job.number, checked)} />
        ))}
      </ul>
      <div className="flex flex-wrap items-center gap-3">
        <Button type="button" disabled={picked.length === 0} onClick={onHide}>
          {`Приховати вибрані · ${picked.length}`}
        </Button>
        <span className="text-caption text-muted-foreground">Нічого не приховується автоматично.</span>
      </div>
    </>
  );
}

function JobRow({ job, checked, onChange }: { job: FilteredJob; checked: boolean; onChange(checked: boolean): void }) {
  const id = useId();
  return (
    <li className="flex gap-3 border-b border-border p-4 last:border-b-0 pointer-coarse:min-h-11">
      <Checkbox id={id} className="mt-0.5" checked={checked} onCheckedChange={(next) => onChange(next === true)} />
      <label htmlFor={id} className="min-w-0 flex-1 [overflow-wrap:anywhere]">
        <strong className="font-medium">{`#${job.number} · ${job.title ?? "(без посади)"}`}</strong>
        <small className="mt-1 block text-muted-foreground">{job.company ?? "(без компанії)"}</small>
        <small className="block">{FILTERED_REASON_TEXT[job.reason]}</small>
      </label>
    </li>
  );
}
