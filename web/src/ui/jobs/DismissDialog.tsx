import { useLayoutEffect, useRef, useState, type FormEvent } from "react";

import { DEFAULT_DISMISS_REASON } from "../../domain/jobs";
import { AlertDialog, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogTitle } from "../components/alert-dialog";
import { Button } from "../components/button";
import { Field } from "../components/field";
import { Input } from "../components/input";
import { useJobsServices } from "./JobsServices";

export interface DismissTarget {
  id: number;
  title: string;
}

interface DismissDialogProps {
  /** Вакансія, яку ховаємо; `null` — діалог закритий. */
  target: DismissTarget | null;
  onClose(): void;
  /** Сервер підтвердив приховування. `reason` — що ввів користувач. */
  onDismissed(target: DismissTarget, reason: string): void;
  /** Куди віддати фокус після успіху: кнопка, що відкривала діалог, уже зникла зі сторінки. */
  focusAfterDismiss(): void;
  /** Сервер відмовив: на вакансію вже є подача. Сторінка перечитує дані, щоб показати її. */
  onApplied?(): void;
}

export const APPLIED_REFUSED = "На вакансію є подача — поданих вакансій не ховають.";
export const DISMISS_FAILED = "Не вдалося сховати вакансію. Причину збережено — спробуй ще раз.";

/** «Не цікаво»: діалог із причиною. Помилка сервера лишає діалог відкритим і нічого не стирає. */
export function DismissDialog({ target, onClose, onDismissed, focusAfterDismiss, onApplied }: DismissDialogProps) {
  const opener = useRef<HTMLElement | null>(null);
  const dismissed = useRef(false);

  // Діалог керований ззовні, тож Radix не знає, хто його відкрив: запамʼятовуємо кнопку до того, як фокус піде в діалог.
  useLayoutEffect(() => {
    if (target !== null && opener.current === null) {
      opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    }
  }, [target]);

  return (
    <AlertDialog open={target !== null} onOpenChange={(open) => !open && onClose()}>
      {target === null ? null : (
        <AlertDialogContent
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            if (dismissed.current) {
              focusAfterDismiss();
            } else {
              opener.current?.focus();
            }
            dismissed.current = false;
            opener.current = null;
          }}
        >
          <DismissForm
            key={target.id}
            target={target}
            onDismissed={(done, reason) => {
              dismissed.current = true;
              onDismissed(done, reason);
            }}
            onApplied={onApplied}
          />
        </AlertDialogContent>
      )}
    </AlertDialog>
  );
}

function DismissForm({
  target,
  onDismissed,
  onApplied,
}: {
  target: DismissTarget;
  onDismissed: DismissDialogProps["onDismissed"];
  onApplied: DismissDialogProps["onApplied"];
}) {
  const services = useJobsServices();
  const [reason, setReason] = useState(DEFAULT_DISMISS_REASON);
  const [pending, setPending] = useState(false);
  const [reasonError, setReasonError] = useState<string | undefined>(undefined);
  const [general, setGeneral] = useState<string | undefined>(undefined);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (pending) {
      return;
    }
    setPending(true);
    setReasonError(undefined);
    setGeneral(undefined);
    const outcome = await services.dismiss([target.id], reason);
    if (outcome.ok) {
      onDismissed(target, reason);
      return;
    }
    setPending(false);
    if (outcome.kind === "applied") {
      setGeneral(APPLIED_REFUSED);
      onApplied?.();
    } else if (outcome.kind === "invalid") {
      const message = outcome.fieldErrors["reason"];
      if (message === undefined) {
        setGeneral(outcome.message);
      } else {
        setReasonError(message);
      }
    } else {
      setGeneral(DISMISS_FAILED);
    }
  }

  return (
    <form onSubmit={(event) => void submit(event)} className="flex flex-col gap-4">
      <div>
        <AlertDialogTitle>Сховати вакансію?</AlertDialogTitle>
        <AlertDialogDescription className="[overflow-wrap:anywhere]">
          «{target.title}» зникне зі списку. Її можна повернути у вкладці «Сховані».
        </AlertDialogDescription>
      </div>
      <Field label="Причина" error={reasonError}>
        {(controls) => <Input {...controls} value={reason} onChange={(event) => setReason(event.target.value)} autoComplete="off" />}
      </Field>
      {general === undefined ? null : (
        <p role="alert" className="rounded-lg bg-status-danger px-3 py-2 text-caption font-medium text-status-danger-foreground">
          {general}
        </p>
      )}
      <div className="flex justify-end gap-2">
        <AlertDialogCancel asChild>
          <Button type="button" variant="secondary">
            Скасувати
          </Button>
        </AlertDialogCancel>
        <Button type="submit" disabled={pending}>
          Сховати
        </Button>
      </div>
    </form>
  );
}
