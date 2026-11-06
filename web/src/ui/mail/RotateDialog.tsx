import { useState } from "react";

import { AlertDialog, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogTitle } from "../components/alert-dialog";
import { Button } from "../components/button";
import { useMail } from "./MailProvider";

/** Зміна адреси необоротна: стара перестає працювати одразу, тож спершу підтвердження. */
export function RotateDialog({ onRotated }: { onRotated(): void }) {
  const { rotate } = useMail();
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  async function confirm() {
    setPending(true);
    setFailure(null);
    const outcome = await rotate();
    setPending(false);
    if (outcome.ok) {
      setOpen(false);
      onRotated();
    } else {
      setFailure(outcome.message);
    }
  }

  return (
    <>
      <Button
        type="button"
        variant="secondary"
        onClick={() => {
          setFailure(null);
          setOpen(true);
        }}
      >
        Змінити адресу
      </Button>
      <AlertDialog open={open} onOpenChange={setOpen}>
        <AlertDialogContent>
          <div className="flex flex-col gap-4">
            <div>
              <AlertDialogTitle>Змінити адресу пересилання?</AlertDialogTitle>
              <AlertDialogDescription>Стара адреса перестане працювати одразу. Після зміни потрібно оновити пересилання й фільтри Gmail.</AlertDialogDescription>
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
                Змінити адресу
              </Button>
            </div>
          </div>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
