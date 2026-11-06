import { useEffect, useId, useRef, type FormEvent, type ReactNode } from "react";
import { useLocation } from "react-router";

import { Button } from "../components/button";
import { FIELDS_INVALID, type EditableSection, type SectionApi } from "./ProfileProvider";

type FrameApi = Pick<SectionApi<EditableSection>, "dirty" | "saving" | "saved" | "general" | "fieldErrors" | "errorToken" | "cancel" | "save">;

interface SectionFrameProps {
  api: FrameApi;
  title: string;
  description: string;
  /** Поля сервера, що мають власне місце у формі; помилки решти йдуть у загальне повідомлення. */
  knownFields: readonly string[];
  children: ReactNode;
}

function statusText(api: FrameApi): string {
  if (api.saving) {
    return "Зберігаємо…";
  }
  if (api.dirty) {
    return "Є незбережені зміни";
  }
  return api.saved ? "Збережено" : "Немає незбережених змін";
}

const FIRST_CONTROL = 'textarea, input, [role="checkbox"], select';

/** Форма розділу: заголовок, поля, статус і «Скасувати» / «Зберегти зміни» окремо для кожного редактора. */
export function SectionFrame({ api, title, description, knownFields, children }: SectionFrameProps) {
  const headingId = useId();
  const formRef = useRef<HTMLFormElement>(null);
  const { state } = useLocation();
  const opened = (state as { focus?: boolean } | null)?.focus === true;

  // Розділ відкрито карткою огляду: фокус на перше поле.
  useEffect(() => {
    if (opened) {
      formRef.current?.querySelector<HTMLElement>(FIRST_CONTROL)?.focus();
    }
  }, [opened]);

  // Сервер чи клієнт відхилив значення: фокус на перше поле з помилкою.
  useEffect(() => {
    if (api.errorToken > 0) {
      formRef.current?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus();
    }
  }, [api.errorToken]);

  const unplaced = Object.entries(api.fieldErrors)
    .filter(([field]) => !knownFields.includes(field))
    .map(([, message]) => message);
  const alert =
    api.general ?? (Object.keys(api.fieldErrors).length === 0 ? null : [FIELDS_INVALID, ...unplaced].join(" "));

  function submit(event: FormEvent) {
    event.preventDefault();
    void api.save();
  }

  return (
    <form ref={formRef} noValidate aria-labelledby={headingId} onSubmit={submit} className="flex flex-col gap-5">
      <header className="border-b border-border pb-4">
        <h2 id={headingId} className="text-xl font-semibold">
          {title}
        </h2>
        <p className="mt-1 text-caption text-muted-foreground">{description}</p>
      </header>
      {alert === null ? null : (
        <p role="alert" className="rounded-lg bg-status-danger px-3 py-2 text-caption font-medium text-status-danger-foreground">
          {alert}
        </p>
      )}
      {children}
      <footer className="flex flex-wrap items-center gap-3 border-t border-border pt-4">
        <p role="status" className="basis-full text-caption text-muted-foreground">
          {statusText(api)}
        </p>
        <Button type="button" variant="secondary" disabled={!api.dirty || api.saving} onClick={api.cancel}>
          Скасувати
        </Button>
        <Button type="submit" disabled={!api.dirty || api.saving}>
          Зберегти зміни
        </Button>
      </footer>
    </form>
  );
}
