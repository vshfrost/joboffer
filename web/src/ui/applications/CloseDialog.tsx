import { useLayoutEffect, useRef } from "react";

import type { ApplicationStatus } from "../../domain/applications";
import { AlertDialog, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogTitle } from "../components/alert-dialog";
import { Button } from "../components/button";

/** Лише закриття подачі питає підтвердження: це остаточний статус. */
export type ClosingStatus = Extract<ApplicationStatus, "rejected" | "withdrawn">;

const TEXTS: Record<ClosingStatus, { title: string; status: string }> = {
  rejected: { title: "Зафіксувати відмову?", status: "Відмова" },
  withdrawn: { title: "Відкликати подачу?", status: "Відкликано" },
};

interface CloseDialogProps {
  /** Який статус підтверджуємо; `null` — діалог закритий. */
  closing: ClosingStatus | null;
  pending: boolean;
  /** Збій сервера: діалог лишається відкритим і пояснює, що статус не змінено. */
  failure: string | null;
  onConfirm(): void;
  onClose(): void;
  /** Чи закрито подачу: тоді кнопка, що відкривала діалог, зникла, і фокус іде в `focusAfterClose`. */
  didClose(): boolean;
  focusAfterClose(): void;
}

/** Підтвердження закриття подачі. Закриття не видаляє вакансію й документи. */
export function CloseDialog({ closing, pending, failure, onConfirm, onClose, didClose, focusAfterClose }: CloseDialogProps) {
  const opener = useRef<HTMLElement | null>(null);

  // Діалог керований ззовні, тож Radix не знає, хто його відкрив: запамʼятовуємо кнопку до того, як фокус піде в діалог.
  useLayoutEffect(() => {
    if (closing !== null) {
      opener.current = document.activeElement as HTMLElement | null;
    }
  }, [closing]);

  return (
    <AlertDialog open={closing !== null} onOpenChange={(open) => !open && onClose()}>
      {closing === null ? null : (
        <AlertDialogContent
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            if (didClose()) {
              focusAfterClose();
            } else {
              opener.current?.focus();
            }
            opener.current = null;
          }}
        >
          <AlertDialogTitle>{TEXTS[closing].title}</AlertDialogTitle>
          <AlertDialogDescription>
            {`Подача отримає статус «${TEXTS[closing].status}». Це лише запис у joboffer: роботодавцю нічого не надсилається. Вакансія й документи залишаться.`}
          </AlertDialogDescription>
          {failure === null ? null : (
            <p role="alert" className="mt-3 rounded-lg bg-status-danger px-3 py-2 text-caption font-medium text-status-danger-foreground">
              {failure}
            </p>
          )}
          <div className="mt-5 flex flex-wrap justify-end gap-2">
            <AlertDialogCancel asChild>
              <Button type="button" variant="secondary">
                Скасувати
              </Button>
            </AlertDialogCancel>
            <Button type="button" variant="destructive" disabled={pending} onClick={onConfirm}>
              Підтвердити
            </Button>
          </div>
        </AlertDialogContent>
      )}
    </AlertDialog>
  );
}
