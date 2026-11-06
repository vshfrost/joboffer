import { useEffect, useRef } from "react";
import { useBlocker, type Blocker } from "react-router";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogTitle,
} from "../components/alert-dialog";
import { Button } from "../components/button";

/**
 * Незбережена форма подачі не губиться мовчки: перехід в інше місце питає підтвердження,
 * закриття чи перезавантаження вкладки — теж (beforeunload). Живе лише поки форма змінена.
 */
export function LeaveGuard({ dirty }: { dirty: boolean }) {
  const blocker = useBlocker(dirty);

  useEffect(() => {
    if (!dirty) {
      return;
    }
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  return blocker.state === "blocked" ? <LeaveDialog blocker={blocker} /> : null;
}

type Blocked = Extract<Blocker, { state: "blocked" }>;

function LeaveDialog({ blocker }: { blocker: Blocked }) {
  // «Піти без збереження» теж закриває діалог: це закриття не має скасовувати перехід.
  const leaving = useRef(false);
  return (
    <AlertDialog
      open
      onOpenChange={() => {
        if (!leaving.current) {
          blocker.reset();
        }
      }}
    >
      <AlertDialogContent>
        <AlertDialogTitle>Є незбережені зміни</AlertDialogTitle>
        <AlertDialogDescription>Якщо піти зараз, введені дані подачі буде втрачено.</AlertDialogDescription>
        <div className="mt-5 flex flex-wrap justify-end gap-2">
          <AlertDialogCancel asChild>
            <Button variant="secondary">Залишитись</Button>
          </AlertDialogCancel>
          <AlertDialogAction asChild>
            <Button
              variant="destructive"
              onClick={() => {
                leaving.current = true;
                blocker.proceed();
              }}
            >
              Піти без збереження
            </Button>
          </AlertDialogAction>
        </div>
      </AlertDialogContent>
    </AlertDialog>
  );
}
