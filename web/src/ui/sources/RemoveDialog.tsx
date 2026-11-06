import { useState } from "react";

import type { Source } from "../../domain/sources";
import { AlertDialog, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogTitle } from "../components/alert-dialog";
import { Button } from "../components/button";

export type RemoveResult = { ok: true } | { ok: false; message: string };

interface RemoveDialogProps {
  source: Source;
  /** Видаляє джерело; `ok: false` лишає діалог відкритим із текстом. */
  onConfirm(): Promise<RemoveResult>;
  onClose(): void;
}

/** Видалення необоротне для статистики джерела, тож спершу підтвердження; імпортовані вакансії лишаються. */
export function RemoveDialog({ source, onConfirm, onClose }: RemoveDialogProps) {
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  async function confirm() {
    setPending(true);
    setFailure(null);
    const result = await onConfirm();
    setPending(false);
    if (!result.ok) {
      setFailure(result.message);
    }
  }

  return (
    <AlertDialog open onOpenChange={() => onClose()}>
      <AlertDialogContent>
        <div className="flex flex-col gap-4">
          <div>
            <AlertDialogTitle>Видалити джерело?</AlertDialogTitle>
            <AlertDialogDescription>{`Джерело «${source.name}» та його статистику буде видалено. Імпортовані вакансії залишаться.`}</AlertDialogDescription>
          </div>
          {failure === null ? null : (
            <p role="alert" className="rounded-lg bg-status-danger px-3 py-2 text-caption font-medium text-status-danger-foreground">
              {failure}
            </p>
          )}
          <div className="flex flex-wrap justify-end gap-2">
            <AlertDialogCancel asChild>
              <Button type="button" variant="secondary">
                Скасувати
              </Button>
            </AlertDialogCancel>
            <Button type="button" variant="destructive" disabled={pending} onClick={() => void confirm()}>
              Так, видалити
            </Button>
          </div>
        </div>
      </AlertDialogContent>
    </AlertDialog>
  );
}
