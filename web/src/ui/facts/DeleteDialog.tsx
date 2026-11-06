import { useLayoutEffect, useRef, useState } from "react";

import type { Fact } from "../../domain/facts";
import { AlertDialog, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogTitle } from "../components/alert-dialog";
import { Button } from "../components/button";
import { useFactsServices } from "./FactsServices";

export const DELETE_FAILED = "Не вдалося видалити факт. Спробуй ще раз.";

interface DeleteDialogProps {
  /** Факт, який видаляємо; `null` — діалог закритий. */
  target: Fact | null;
  onClose(): void;
  /** Сервер підтвердив видалення (або факту вже нема). */
  onDeleted(fact: Fact, existed: boolean): void;
  /** Куди віддати фокус після видалення: кнопка, що відкривала діалог, уже зникла зі сторінки. */
  focusAfterDelete(): void;
}

/** Видалення назавжди: відновлення нема, тож діалог каже про це прямо. Помилка сервера лишає діалог відкритим. */
export function DeleteDialog({ target, onClose, onDeleted, focusAfterDelete }: DeleteDialogProps) {
  const opener = useRef<HTMLElement | null>(null);
  const deleted = useRef(false);

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
            if (deleted.current) {
              focusAfterDelete();
            } else {
              opener.current?.focus();
            }
            deleted.current = false;
            opener.current = null;
          }}
        >
          <DeleteBody
            key={target.id}
            fact={target}
            onDeleted={(done, existed) => {
              deleted.current = true;
              onDeleted(done, existed);
            }}
          />
        </AlertDialogContent>
      )}
    </AlertDialog>
  );
}

function DeleteBody({ fact, onDeleted }: { fact: Fact; onDeleted: DeleteDialogProps["onDeleted"] }) {
  const services = useFactsServices();
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  async function remove() {
    if (pending) {
      return;
    }
    setPending(true);
    setFailure(null);
    const outcome = await services.remove(fact.id);
    if (outcome.ok) {
      onDeleted(fact, true);
    } else if (outcome.kind === "not-found") {
      onDeleted(fact, false);
    } else {
      setPending(false);
      setFailure(DELETE_FAILED);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <AlertDialogTitle>{`Видалити факт ${fact.id} назавжди?`}</AlertDialogTitle>
        <AlertDialogDescription>Відновити його не можна. Факт зникне з бібліотеки й більше не потрапить у CV.</AlertDialogDescription>
      </div>
      <blockquote className="rounded-lg bg-muted px-3 py-2 text-caption [overflow-wrap:anywhere]">{fact.text}</blockquote>
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
        <Button type="button" variant="destructive" disabled={pending} onClick={() => void remove()}>
          Видалити назавжди
        </Button>
      </div>
    </div>
  );
}
