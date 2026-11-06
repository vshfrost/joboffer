import { useRef } from "react";

import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogTitle } from "../components/alert-dialog";
import { Button } from "../components/button";

interface UnsavedDialogProps {
  open: boolean;
  /** Чий факт у редакторі: «факту 4». */
  subject: string;
  onStay(): void;
  onDiscard(): void;
}

/** Незбережену чернетку не губимо мовчки: фільтр, інший факт чи навігація спершу питають. */
export function UnsavedDialog({ open, subject, onStay, onDiscard }: UnsavedDialogProps) {
  // «Відкинути зміни» теж закриває діалог: це закриття не має скасовувати дію.
  const discarding = useRef(false);
  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        if (!next && !discarding.current) {
          onStay();
        }
        discarding.current = false;
      }}
    >
      <AlertDialogContent>
        <AlertDialogTitle>Є незбережені зміни</AlertDialogTitle>
        <AlertDialogDescription>{`Якщо продовжити, зміни до ${subject} буде втрачено.`}</AlertDialogDescription>
        <div className="mt-5 flex flex-wrap justify-end gap-2">
          <AlertDialogCancel asChild>
            <Button variant="secondary">Залишитись</Button>
          </AlertDialogCancel>
          <AlertDialogAction asChild>
            <Button
              variant="destructive"
              onClick={() => {
                discarding.current = true;
                onDiscard();
              }}
            >
              Відкинути зміни
            </Button>
          </AlertDialogAction>
        </div>
      </AlertDialogContent>
    </AlertDialog>
  );
}
