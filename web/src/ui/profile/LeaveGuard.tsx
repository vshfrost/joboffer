import { useEffect, useRef } from "react";
import { useBlocker, type Blocker } from "react-router";

import { SECTION_LABELS } from "../../domain/profile";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogTitle,
} from "../components/alert-dialog";
import { Button } from "../components/button";
import { PROFILE } from "../navigation";
import { useProfile } from "./ProfileProvider";

/**
 * Незбережені зміни не можна втратити мовчки: вихід із профілю (інший розділ застосунку) питає
 * підтвердження, закриття чи перезавантаження вкладки — теж (beforeunload). Переходи між
 * розділами профілю не блокуються: чернетки переживають їх.
 */
export function LeaveGuard() {
  const { dirtySections } = useProfile();
  const dirty = dirtySections.length > 0;
  const blocker = useBlocker(
    ({ nextLocation }) =>
      dirty && nextLocation.pathname !== PROFILE && !nextLocation.pathname.startsWith(`${PROFILE}/`),
  );

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

  const names = dirtySections.map((section) => `«${SECTION_LABELS[section]}»`).join(", ");
  return blocker.state === "blocked" ? <LeaveDialog blocker={blocker} names={names} /> : null;
}

type Blocked = Extract<Blocker, { state: "blocked" }>;

/** Діалог показується лише поки навігацію заблоковано: `blocker` тут уже звужено до «blocked». */
function LeaveDialog({ blocker, names }: { blocker: Blocked; names: string }) {
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
        <AlertDialogDescription>{`Якщо піти зараз, зміни в розділах ${names} буде втрачено.`}</AlertDialogDescription>
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
