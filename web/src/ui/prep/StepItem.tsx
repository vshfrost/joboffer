import { ExternalLink } from "lucide-react";
import { useState, type FormEvent } from "react";

import { STEP_KIND_LABELS, type Step } from "../../domain/prep";
import { Button } from "../components/button";
import { Field } from "../components/field";
import { Textarea } from "../components/textarea";
import { cn } from "../lib/cn";

/** Результат збереження кроку: помилка поля `note` (422) — текстом біля поля; решту повідомляє сторінка. */
export type SaveStepResult = { ok: true } | { ok: false; fieldError?: string | undefined };

interface StepItemProps {
  step: Step;
  /** Чи розкрити крок при першому показі (перший невиконаний). */
  initiallyOpen: boolean;
  onSave(stepId: number, note: string): Promise<SaveStepResult>;
}

/** Крок теми: розкривний, з описом, ресурсами, нотаткою виконаного і формою «Позначити виконаним» / «Зберегти нотатку». */
export function StepItem({ step, initiallyOpen, onSave }: StepItemProps) {
  // Початково розкритий крок лишається розкритим: далі стан веде сам `<details>`, а не новий «перший невиконаний».
  const [open] = useState(initiallyOpen);
  // Після збереження форма створюється наново: поле показує нотатку, яку тримає сервер (порожнє збереження стару лишає).
  const [saves, setSaves] = useState(0);
  const done = step.doneOn !== null;
  return (
    <details open={open} className="group rounded-lg border border-border bg-card">
      <summary
        className={cn(
          "flex cursor-pointer list-none items-start gap-3 p-3.5 [&::-webkit-details-marker]:hidden pointer-coarse:min-h-11",
          "after:ml-auto after:shrink-0 after:text-lg after:leading-5 after:text-muted-foreground after:content-['+'] group-open:after:content-['−']",
        )}
      >
        <span
          aria-hidden="true"
          className={cn("flex size-6 shrink-0 items-center justify-center rounded-full text-caption", done ? "bg-selected text-selected-foreground" : "bg-muted text-muted-foreground")}
        >
          {done ? "✓" : step.position}
        </span>
        <span className="min-w-0">
          <strong className="block font-semibold [overflow-wrap:anywhere]">{step.title}</strong>
          <span className="block text-caption text-muted-foreground">{`${STEP_KIND_LABELS[step.kind]} · ~${step.minutes} хв${done ? ` · виконано ${step.doneOn}` : ""}`}</span>
        </span>
      </summary>
      <div className="flex min-w-0 flex-col gap-3 px-3.5 pb-4 sm:pl-13">
        <p className="whitespace-pre-wrap [overflow-wrap:anywhere]">{step.details}</p>
        {step.resources.length === 0 ? null : (
          <ul className="m-0 flex list-none flex-col gap-1 p-0">
            {step.resources.map((resource) => (
              <li key={resource.url}>
                <a
                  href={resource.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-primary underline underline-offset-3 [overflow-wrap:anywhere] pointer-coarse:min-h-11"
                >
                  {resource.title}
                  <ExternalLink aria-hidden="true" className="size-3.5 shrink-0" />
                </a>
              </li>
            ))}
          </ul>
        )}
        {done ? <div className="border-l-2 border-border bg-background px-3 py-2 whitespace-pre-wrap [overflow-wrap:anywhere]">{step.note === "" ? "Без нотатки" : step.note}</div> : null}
        <NoteForm key={saves} step={step} done={done} onSave={onSave} onSaved={() => setSaves((count) => count + 1)} />
      </div>
    </details>
  );
}

interface NoteFormProps {
  step: Step;
  done: boolean;
  onSave(stepId: number, note: string): Promise<SaveStepResult>;
  onSaved(): void;
}

function NoteForm({ step, done, onSave, onSaved }: NoteFormProps) {
  const [draft, setDraft] = useState(step.note);
  const [error, setError] = useState<string | undefined>(undefined);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(undefined);
    const result = await onSave(step.id, draft);
    if (result.ok) {
      onSaved();
    } else {
      setBusy(false);
      setError(result.fieldError);
    }
  }

  return (
    <form onSubmit={(event) => void submit(event)} className="flex flex-col gap-2">
      <Field label="Нотатка (необов’язково)" hint="До 2000 символів" error={error}>
        {(control) => <Textarea {...control} name="note" value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Що зробив, що запам’ятав…" />}
      </Field>
      <div>
        <Button type="submit" disabled={busy} variant={done ? "secondary" : "default"}>
          {done ? "Зберегти нотатку" : "Позначити виконаним"}
        </Button>
      </div>
    </form>
  );
}
