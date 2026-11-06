import { useLayoutEffect, useRef, useState } from "react";

import { photoName, type Photo } from "../../domain/photos";
import { AlertDialog, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogTitle } from "../components/alert-dialog";
import { Button } from "../components/button";
import { usePhotosServices } from "./PhotosServices";

interface DeletePhotoDialogProps {
  /** Фото, яке видаляємо; `null` — діалог закритий. */
  target: Photo | null;
  onClose(): void;
  /** Сервер підтвердив видалення (або фото вже нема). */
  onDeleted(): void;
  /** Куди віддати фокус після видалення: кнопка, що відкривала діалог, уже зникла зі сторінки. */
  focusAfterDelete(): void;
}

/** Видалення назавжди; збережені CV не змінюються. Помилка сервера лишає діалог відкритим. */
export function DeletePhotoDialog({ target, onClose, onDeleted, focusAfterDelete }: DeletePhotoDialogProps) {
  const opener = useRef<HTMLElement | null>(null);
  const deleted = useRef(false);

  // Діалог керований ззовні, тож Radix не знає, хто його відкрив: запамʼятовуємо кнопку до того, як фокус піде в діалог.
  useLayoutEffect(() => {
    if (target !== null && opener.current === null) {
      // Кнопку з фокусом у цей момент ставить браузер: це завжди елемент сторінки (або body).
      opener.current = document.activeElement as HTMLElement | null;
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
            photo={target}
            onDeleted={() => {
              deleted.current = true;
              onDeleted();
            }}
          />
        </AlertDialogContent>
      )}
    </AlertDialog>
  );
}

function DeleteBody({ photo, onDeleted }: { photo: Photo; onDeleted(): void }) {
  const services = usePhotosServices();
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  // Подвійний клік у межах одного кадру: стан ще старий, тож ворота — у ref.
  const inFlight = useRef(false);

  async function remove() {
    if (inFlight.current) {
      return;
    }
    inFlight.current = true;
    setPending(true);
    setFailure(null);
    const outcome = await services.remove(photo.id);
    if (outcome.ok) {
      onDeleted();
      return;
    }
    inFlight.current = false;
    setPending(false);
    setFailure(
      outcome.kind === "unauthorized" ? "Сесія завершилась. Увійди знову, щоб видалити фото." : "Не вдалося видалити фото. Спробуй ще раз.",
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <AlertDialogTitle>Видалити фото?</AlertDialogTitle>
        <AlertDialogDescription>Збережені CV не зміняться: їхні PDF лишаються з цим фото. У нові CV воно вже не потрапить.</AlertDialogDescription>
      </div>
      <blockquote className="rounded-lg bg-muted px-3 py-2 text-caption [overflow-wrap:anywhere]">{photoName(photo)}</blockquote>
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
          Видалити
        </Button>
      </div>
    </div>
  );
}
