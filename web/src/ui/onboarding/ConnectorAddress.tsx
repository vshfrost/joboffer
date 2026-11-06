import { Copy } from "lucide-react";

import { useCopy } from "../mail/useCopy";

/** Адреса MCP joboffer і кнопка копіювання; результат копіювання — в `role="status"` для читача екрана. */
export function ConnectorAddress({ address }: { address: string }) {
  const { message, copy } = useCopy();
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <p className="text-caption text-muted-foreground">Адреса MCP-сервера joboffer</p>
      <div className="flex min-w-0 items-center gap-2 rounded-lg border border-border bg-background px-3 py-2">
        <code className="min-w-0 flex-1 text-caption [overflow-wrap:anywhere]">{address}</code>
        <button
          type="button"
          aria-label="Копіювати адресу MCP"
          title="Копіювати адресу"
          onClick={() => void copy(address, "Адресу скопійовано.", "Не вдалося скопіювати — виділи адресу вручну.")}
          className="inline-flex size-8 shrink-0 cursor-pointer items-center justify-center rounded-md text-muted-foreground hover:bg-accent pointer-coarse:size-11"
        >
          <Copy aria-hidden="true" className="size-4" />
        </button>
      </div>
      <p role="status" className="text-caption text-muted-foreground empty:hidden">
        {message}
      </p>
    </div>
  );
}
