import { useState } from "react";

import { madridDay, madridTime, type MailSettings } from "../../domain/mail";
import { Button } from "../components/button";
import { Skeleton } from "../components/skeleton";
import { useMail } from "./MailProvider";
import { RotateDialog } from "./RotateDialog";
import { problemText } from "./texts";
import { useCopy } from "./useCopy";

const SECTION = "flex flex-col gap-3 rounded-xl border border-border bg-card p-5 max-sm:p-4";
const ALERT = "flex flex-wrap items-center gap-3 rounded-xl border border-border bg-status-danger p-4 text-status-danger-foreground";

function stamp(iso: string): string {
  return `${madridDay(iso)} · ${madridTime(iso)}`;
}

/** Вкладка «Налаштування»: лише налаштування — адреса, інструкція Gmail, синк, зміна адреси. */
export function SettingsTab() {
  const { state, reload } = useMail();
  if (state.status === "loading") {
    return (
      <div role="status" aria-label="Завантажуємо налаштування…" className="flex flex-col gap-3">
        <Skeleton className="h-32" />
        <Skeleton className="h-32" />
      </div>
    );
  }
  if (state.status === "error") {
    return (
      <div role="alert" className={ALERT}>
        <p className="text-nav font-medium">{problemText(state.problem, "побачити налаштування пошти", "Не вдалося завантажити налаштування пошти.")}</p>
        {state.problem === "unavailable" ? (
          <Button type="button" variant="secondary" onClick={reload}>
            Спробувати ще раз
          </Button>
        ) : null}
      </div>
    );
  }
  return <Ready settings={state.settings} />;
}

function Ready({ settings }: { settings: MailSettings }) {
  const [result, setResult] = useState("");
  return (
    <div className="flex flex-col gap-4">
      <p role="status" aria-label="Результат" className="text-caption font-medium text-status-success-foreground empty:hidden">
        {result}
      </p>
      <AddressSection settings={settings} />
      <SyncSection settings={settings} />
      <section aria-label="Змінити адресу пересилання" className={SECTION}>
        <h2 className="text-section font-semibold">Змінити адресу пересилання</h2>
        <p className="text-caption text-muted-foreground">Стара адреса перестане працювати одразу. Після зміни потрібно оновити пересилання й фільтри Gmail.</p>
        <div>
          <RotateDialog onRotated={() => setResult("Адресу змінено. Онови пересилання й фільтри Gmail.")} />
        </div>
      </section>
    </div>
  );
}

function AddressSection({ settings }: { settings: MailSettings }) {
  const { message, copy } = useCopy();
  return (
    <section aria-label="Адреса для пересилання" className={SECTION}>
      <h2 className="text-section font-semibold">Адреса для пересилання</h2>
      <p>
        <code className="rounded-md bg-muted px-2 py-1 text-nav [overflow-wrap:anywhere]">{settings.address}</code>
      </p>
      {settings.rotatedAt === null ? null : <p className="text-caption text-muted-foreground">{`Адресу змінено ${stamp(settings.rotatedAt)} (Мадрид).`}</p>}
      <div>
        <Button type="button" variant="secondary" onClick={() => void copy(settings.address, "Адресу скопійовано.", "Не вдалося скопіювати — виділи адресу вручну.")}>
          Копіювати адресу
        </Button>
      </div>
      <p role="status" aria-label="Копіювання" className="text-caption text-muted-foreground empty:hidden">
        {message}
      </p>
      <details className="rounded-lg border border-border p-4">
        <summary className="cursor-pointer text-nav font-medium">Як налаштувати Gmail</summary>
        <ol className="mt-2 flex list-decimal flex-col gap-1 pl-5 text-caption text-muted-foreground">
          <li>У Gmail відкрий налаштування пересилання та додай цю адресу.</li>
          <li>Підтвердь пересилання. Якщо Gmail надіслав лише посилання — відкрий оригінал у службовій скриньці; не використовуй посилання з тексту тут.</li>
          <li>Створи фільтри для відповідей компаній і листів LinkedIn. Не пересилай усю скриньку.</li>
          <li>Перешли тестовий лист і перевір його у «Вхідних». Код підтвердження, якщо він є, з’явиться у «Вхідних». Старі листи автоматично не імпортуються.</li>
        </ol>
      </details>
    </section>
  );
}

function SyncSection({ settings }: { settings: MailSettings }) {
  const { manualAfterSync, queued, requesting, syncMessage, requestSync } = useMail();
  const left = manualAfterSync ?? settings.manual;
  return (
    <section aria-label="Синхронізація" className={SECTION}>
      <h2 className="text-section font-semibold">Синхронізація</h2>
      {settings.syncFailed ? (
        <p role="alert" className="rounded-lg bg-status-danger px-3 py-2 text-caption font-medium text-status-danger-foreground">
          {`Останній синк не вдався: ${settings.syncError}`}
        </p>
      ) : null}
      <p className="text-caption text-muted-foreground">
        {settings.syncedAt === null ? "Синк ще не було." : `Останній успішний синк: ${stamp(settings.syncedAt)} (Мадрид)`}
      </p>
      <p>{`Ручних запитів доступно: ${left.remaining} з ${left.limit} за 30 хв.`}</p>
      {left.nextAt === null ? null : <p className="text-caption text-muted-foreground">{`Наступний запит можна о ${madridTime(left.nextAt)} (Мадрид).`}</p>}
      <div>
        <Button type="button" disabled={queued || requesting || left.remaining === 0} onClick={() => void requestSync()}>
          {queued ? "Запит у черзі" : "Синхронізувати зараз"}
        </Button>
      </div>
      {syncMessage === "" ? null : (
        <p role="alert" className="text-caption font-medium text-status-danger-foreground">
          {syncMessage}
        </p>
      )}
      <p className="text-caption text-muted-foreground">Запит підхоплює серверний таймер. Нові листи з’являться після завершення синку.</p>
    </section>
  );
}
