import { useState } from "react";

import { problemText } from "../mail/texts";
import {
  defaultJobId,
  effectText,
  jobLabel,
  NO_JOB_EFFECT,
  REPLY_TYPES,
  TYPE_LABELS,
  type ReplyDetail,
  type ReplyType,
} from "../../domain/replies";
import { AlertDialog, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogTitle } from "../components/alert-dialog";
import { Button } from "../components/button";
import { Field } from "../components/field";
import { Select } from "../components/select";
import { useRepliesServices } from "./RepliesServices";
import { useReviewPreview, type PreviewState } from "./useReviewPreview";

const NOT_FOUND = "Лист або подачу не знайдено. Онови сторінку.";

/** Текст ефекту розбору під полями: порахований сервером або причина, чому його нема. */
function effectLine(preview: PreviewState): string {
  if (preview.status === "loading") {
    return "Рахуємо ефект…";
  }
  if (preview.status === "error") {
    return "Не вдалося порахувати ефект розбору.";
  }
  return effectText(preview.status === "ready" ? preview.effect : NO_JOB_EFFECT);
}

interface FormErrors {
  type?: string | undefined;
  job?: string | undefined;
}

/**
 * Форма розбору нерозібраної відповіді: вакансія зі списку подач (або «Не про подачу»), тип із підказкою вибраною
 * наперед, превʼю ефекту. Розбір остаточний, тож відмова спершу просить окремого підтвердження.
 */
export function ReviewForm({ detail, onReviewed }: { detail: ReplyDetail; onReviewed(): void }) {
  const services = useRepliesServices();
  const { reply, applications } = detail;
  const [jobValue, setJobValue] = useState(() => String(defaultJobId(detail) ?? ""));
  const [type, setType] = useState<ReplyType>(reply.suggestedType);
  const [pending, setPending] = useState(false);
  const [errors, setErrors] = useState<FormErrors>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const jobId = jobValue === "" ? null : Number(jobValue);
  const preview = useReviewPreview(reply.id, type, jobId);

  function edit(change: () => void) {
    change();
    setErrors({});
    setFailure(null);
  }

  async function review() {
    setPending(true);
    setErrors({});
    setFailure(null);
    const outcome = await services.review(reply.id, { type, jobId });
    if (outcome.ok) {
      onReviewed();
      return;
    }
    setPending(false);
    if (outcome.kind === "invalid") {
      setErrors({ type: outcome.fieldErrors["type"], job: outcome.fieldErrors["job_id"] });
      setFailure(Object.entries(outcome.fieldErrors).find(([field]) => field !== "type" && field !== "job_id")?.[1] ?? null);
    } else {
      setFailure(outcome.kind === "not-found" ? NOT_FOUND : problemText(outcome.kind, "підтвердити розбір", "Не вдалося підтвердити розбір. Спробуй ще раз."));
    }
  }

  function confirmRejection() {
    setConfirming(false);
    void review();
  }

  return (
    <div role="group" aria-label="Розбір відповіді" className="flex flex-col gap-4 rounded-lg border border-border p-4">
      <h3 className="text-nav font-semibold">Підтвердити розбір</h3>
      <Field label="Вакансія" error={errors.job}>
        {(controls) => (
          <Select {...controls} value={jobValue} onChange={(event) => edit(() => setJobValue(event.target.value))}>
            <option value="">Не про подачу</option>
            {applications.map((application) => (
              <option key={application.jobId} value={application.jobId}>
                {jobLabel(application)}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <Field label="Тип відповіді" hint={`Підказка за ключовими словами: ${TYPE_LABELS[reply.suggestedType]}. Тип підтверджуєш ти.`} error={errors.type}>
        {(controls) => (
          <Select {...controls} value={type} onChange={(event) => edit(() => setType(event.target.value as ReplyType))}>
            {REPLY_TYPES.map((value) => (
              <option key={value} value={value}>
                {TYPE_LABELS[value]}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <p aria-live="polite" className="rounded-lg bg-muted px-3 py-2 text-caption">
        {effectLine(preview)}
      </p>
      {failure === null ? null : (
        <p role="alert" className="rounded-lg bg-status-danger px-3 py-2 text-caption font-medium text-status-danger-foreground">
          {failure}
        </p>
      )}
      <div>
        <Button type="button" disabled={pending || preview.status === "loading"} onClick={() => (type === "rejection" ? setConfirming(true) : void review())}>
          Підтвердити розбір
        </Button>
      </div>
      <AlertDialog open={confirming} onOpenChange={setConfirming}>
        <AlertDialogContent>
          <div className="flex flex-col gap-4">
            <div>
              <AlertDialogTitle>Позначити відповідь як відмову?</AlertDialogTitle>
              <AlertDialogDescription>{`${effectLine(preview)} Розбір остаточний: змінити його потім не можна.`}</AlertDialogDescription>
            </div>
            <div className="flex flex-wrap justify-end gap-2">
              <AlertDialogCancel asChild>
                <Button type="button" variant="secondary">
                  Скасувати
                </Button>
              </AlertDialogCancel>
              <Button type="button" variant="destructive" onClick={confirmRejection}>
                Так, це відмова
              </Button>
            </div>
          </div>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
