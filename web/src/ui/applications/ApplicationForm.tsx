import { useEffect, useRef, useState, type FormEvent } from "react";

import type { ChangeApplicationOutcome } from "../../application/applications";
import {
  applicationInput,
  ATS_LABELS,
  ATS_PLATFORMS,
  CHANNEL_LABELS,
  CHANNELS,
  sameDraft,
  type Application,
  type ApplicationChannel,
  type ApplicationDraft,
  type AtsPlatform,
} from "../../domain/applications";
import { Button } from "../components/button";
import { Field } from "../components/field";
import { Input } from "../components/input";
import { Select } from "../components/select";
import { Textarea } from "../components/textarea";
import { useApplicationsServices } from "./ApplicationsServices";
import { LeaveGuard } from "./LeaveGuard";
import { Reveal } from "./Reveal";

export const SAVE_FAILED = "Не вдалося зберегти подачу. Введене збережено — спробуй ще раз.";
const JOB_GONE = "Вакансію не знайдено.";

interface ApplicationFormProps {
  jobId: number;
  /** Звідки форма стартує: порожня («Я подався») чи збережена («Змінити дані»). */
  initial: ApplicationDraft;
  /** Чи це зміна збереженої подачі. */
  editing: boolean;
  onSaved(application: Application): void;
  onCancel(): void;
}

/** Поля API, біля яких показуємо помилку; усе інше — загальним повідомленням. */
const FIELDS = ["channel", "applied_on", "ats", "company_domains", "company_emails"] as const;

/** «Я подався» / «Змінити дані»: фіксує вже виконану подачу, нічого не надсилає. Помилка сервера не стирає введене. */
export function ApplicationForm({ jobId, initial, editing, onSaved, onCancel }: ApplicationFormProps) {
  const services = useApplicationsServices();
  const [draft, setDraft] = useState(initial);
  const [pending, setPending] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [general, setGeneral] = useState<string | undefined>(undefined);
  const [contactsOpen, setContactsOpen] = useState(editing);
  const channelRef = useRef<HTMLSelectElement>(null);
  const submitting = useRef(false);

  useEffect(() => {
    channelRef.current?.focus();
  }, []);

  function change(patch: Partial<ApplicationDraft>) {
    setDraft((current) => ({ ...current, ...patch }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (submitting.current) {
      return;
    }
    submitting.current = true;
    setPending(true);
    setErrors({});
    setGeneral(undefined);
    const outcome = await services.save(jobId, applicationInput(draft));
    submitting.current = false;
    if (outcome.ok) {
      onSaved(outcome.application);
      return;
    }
    setPending(false);
    fail(outcome);
  }

  function fail(outcome: Exclude<ChangeApplicationOutcome, { ok: true }>) {
    if (outcome.kind === "invalid") {
      const known = Object.fromEntries(Object.entries(outcome.fieldErrors).filter(([field]) => FIELDS.some((candidate) => candidate === field)));
      setErrors(known);
      if (Object.keys(known).length < Object.keys(outcome.fieldErrors).length) {
        setGeneral(outcome.message);
      }
      // Помилку в полі під розкриттям не ховаємо.
      if (known["company_domains"] !== undefined || known["company_emails"] !== undefined) {
        setContactsOpen(true);
      }
      return;
    }
    setGeneral(outcome.kind === "not-found" ? JOB_GONE : SAVE_FAILED);
  }

  const title = editing ? "Змінити дані подачі" : "Я подався";
  return (
    <form aria-label={title} noValidate onSubmit={(event) => void submit(event)} className="flex flex-col gap-5">
      <LeaveGuard dirty={!sameDraft(draft, initial)} />
      <div>
        <h3 className="text-nav font-semibold">{title}</h3>
        <p className="mt-1 text-caption text-muted-foreground">Зафіксуйте вже виконану подачу. Ця форма не надсилає заявку роботодавцю.</p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Канал" error={errors["channel"]}>
          {(controls) => (
            <Select
              {...controls}
              ref={channelRef}
              value={draft.channel}
              onChange={(event) => change({ channel: event.target.value as "" | ApplicationChannel })}
            >
              <option value="">Обери канал</option>
              {CHANNELS.map((channel) => (
                <option key={channel} value={channel}>
                  {CHANNEL_LABELS[channel]}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label="Дата подачі" error={errors["applied_on"]}>
          {(controls) => <Input {...controls} type="date" value={draft.appliedOn} onChange={(event) => change({ appliedOn: event.target.value })} />}
        </Field>
        <Field label="ATS" hint="Необов’язково: через яку систему подавались." error={errors["ats"]} className="sm:col-span-2">
          {(controls) => (
            <Select {...controls} value={draft.ats} onChange={(event) => change({ ats: event.target.value as "" | AtsPlatform })}>
              <option value="">Не вказано</option>
              {ATS_PLATFORMS.map((platform) => (
                <option key={platform} value={platform}>
                  {ATS_LABELS[platform]}
                </option>
              ))}
            </Select>
          )}
        </Field>
      </div>
      <Reveal label="Домени й адреси email · необов’язково" open={contactsOpen} onToggle={() => setContactsOpen((current) => !current)}>
        <div className="mt-2 grid gap-4 sm:grid-cols-2">
          <Field label="Домени" hint="По одному значенню на рядок, наприклад company.example." error={errors["company_domains"]}>
            {(controls) => <Textarea {...controls} value={draft.domains} onChange={(event) => change({ domains: event.target.value })} className="min-h-20" />}
          </Field>
          <Field label="Адреси email" hint="По одній адресі на рядок, наприклад careers@company.example." error={errors["company_emails"]}>
            {(controls) => <Textarea {...controls} value={draft.emails} onChange={(event) => change({ emails: event.target.value })} className="min-h-20" />}
          </Field>
        </div>
      </Reveal>
      {general === undefined ? null : (
        <p role="alert" className="rounded-lg bg-status-danger px-3 py-2 text-caption font-medium text-status-danger-foreground">
          {general}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={pending}>
          {pending ? "Зберігаємо…" : "Зберегти подачу"}
        </Button>
        <Button type="button" variant="secondary" onClick={onCancel}>
          Скасувати
        </Button>
      </div>
    </form>
  );
}
