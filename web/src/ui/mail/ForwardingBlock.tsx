import type { Forwarding } from "../../domain/mail";
import { Button } from "../components/button";
import { useCopy } from "./useCopy";

/** Код підтвердження пересилання Gmail у читалці його листа. Код і адреса — з листа, тож недовірені. */
export function ForwardingBlock({ forwarding }: { forwarding: Forwarding }) {
  const { message, copy } = useCopy();
  return (
    <div role="group" aria-label="Код підтвердження пересилання" className="flex flex-col gap-2 rounded-lg border border-border bg-muted p-4">
      {forwarding.linkOnly ? (
        <>
          <p className="text-nav font-medium">У цьому листі нема коду — Gmail надіслав лише посилання.</p>
          <p className="text-caption text-muted-foreground">Відкрий оригінал у службовій скриньці; посилання з тексту тут не використовуй.</p>
        </>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <code className="rounded-md bg-card px-3 py-1.5 text-section font-semibold tracking-widest">{forwarding.code}</code>
            <Button type="button" variant="secondary" onClick={() => void copy(forwarding.code, "Код скопійовано.", "Не вдалося скопіювати — виділи код вручну.")}>
              Копіювати код
            </Button>
          </div>
          <p role="status" className="text-caption text-muted-foreground empty:hidden">
            {message}
          </p>
        </>
      )}
      {forwarding.requestedBy === "" ? null : <p className="text-caption text-muted-foreground">{`Просить пересилати: ${forwarding.requestedBy}`}</p>}
      {forwarding.current ? null : (
        <p role="note" className="text-caption text-status-warning-foreground">
          Лист надійшов до зміни адреси: код для старої адреси.
        </p>
      )}
    </div>
  );
}
