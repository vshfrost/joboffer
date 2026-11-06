import { useEffect, useRef, useState, type FormEvent, type Ref } from "react";
import { Link, useLocation, useNavigate } from "react-router";

import { ADD_NOTICES, NO_NEW_JOB, type NewJobInput } from "../../domain/jobs";
import { REQUESTS } from "../../domain/prompts";
import { DelegateToAgent } from "../agents/DelegateToAgent";
import { Button } from "../components/button";
import { Field } from "../components/field";
import { Input } from "../components/input";
import { Textarea } from "../components/textarea";
import { usePageTitle } from "../lib/usePageTitle";
import { PageHeading } from "../pages/PageHeading";
import { useJobsServices } from "./JobsServices";
import { prefilledUrl } from "./navigationState";

export const ADD_FAILED = "Не вдалося додати вакансію. Введене не втрачено — спробуй ще раз.";

type FieldName = keyof NewJobInput;
/** Порядок полів на сторінці: фокус після помилки йде на перше з них, де вона є. */
const ORDER: readonly FieldName[] = ["text", "url", "title", "company"];

/** `/vacancies/new`: текст обов'язковий, решта — за бажанням; правила й тексти помилок — на сервері. */
export function AddJobPage() {
  usePageTitle("Додати вакансію · Вакансії");
  const services = useJobsServices();
  const navigate = useNavigate();
  const location = useLocation();
  const [form, setForm] = useState<NewJobInput>(() => ({ ...NO_NEW_JOB, url: prefilledUrl(location.state) }));
  const [errors, setErrors] = useState<Partial<Record<FieldName, string>>>({});
  const [general, setGeneral] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [errorToken, setErrorToken] = useState(0);
  const inFlight = useRef(false);
  const refs = useRef<Partial<Record<FieldName, HTMLInputElement | HTMLTextAreaElement | null>>>({});
  const back = `/vacancies${location.search}`;

  // Помилка сервера — фокус на перше поле з помилкою (форма не губить введене).
  useEffect(() => {
    if (errorToken > 0) {
      const first = ORDER.find((field) => errors[field] !== undefined);
      if (first !== undefined) {
        refs.current[first]?.focus();
      }
    }
    // Лише нова відхилена спроба: правка поля не має красти фокус.
  }, [errorToken]);

  const change = (field: FieldName, value: string) => {
    setForm((current) => ({ ...current, [field]: value }));
    setErrors((current) => Object.fromEntries(Object.entries(current).filter(([name]) => name !== field)));
  };
  const ref = (field: FieldName) => (element: HTMLInputElement | HTMLTextAreaElement | null) => {
    refs.current[field] = element;
  };

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (inFlight.current) {
      return;
    }
    inFlight.current = true;
    setPending(true);
    setErrors({});
    setGeneral(null);
    const outcome = await services.add(form);
    if (outcome.ok) {
      void navigate({ pathname: `/vacancies/${outcome.added.id}`, search: location.search }, { state: { notice: ADD_NOTICES[outcome.added.outcome] } });
      return;
    }
    inFlight.current = false;
    setPending(false);
    if (outcome.kind === "invalid") {
      const known = Object.fromEntries(Object.entries(outcome.fieldErrors).filter(([field]) => ORDER.some((name) => name === field)));
      setErrors(known);
      setGeneral(Object.keys(known).length === 0 ? outcome.message : null);
      setErrorToken((token) => token + 1);
    } else {
      setGeneral(ADD_FAILED);
    }
  }

  return (
    <>
      <PageHeading title="Додати вакансію" subtitle="Встав текст опису — решту можна не вказувати." />
      <div className="mb-5 max-w-2xl">
        <DelegateToAgent request={REQUESTS.addJob} description="Агент попросить посилання чи текст вакансії, збереже її й запропонує аналіз" />
      </div>
      <form noValidate onSubmit={(event) => void submit(event)} className="flex max-w-2xl flex-col gap-5">
        <Field label="Текст опису" hint="Обов’язково. Встав повний текст вакансії." error={errors.text}>
          {(control) => (
            <Textarea
              {...control}
              ref={ref("text") as Ref<HTMLTextAreaElement>}
              aria-required="true"
              rows={10}
              value={form.text}
              onChange={(event) => change("text", event.target.value)}
              className="min-h-48"
            />
          )}
        </Field>
        <Field label="Посилання" hint="Необов’язково. Посилання LinkedIn на вакансію з алерту допише текст у неї." error={errors.url}>
          {(control) => (
            <Input
              {...control}
              ref={ref("url") as Ref<HTMLInputElement>}
              inputMode="url"
              autoComplete="off"
              value={form.url}
              onChange={(event) => change("url", event.target.value)}
              className="aria-invalid:border-destructive"
            />
          )}
        </Field>
        <div className="grid gap-5 md:grid-cols-2">
          <Field label="Назва" error={errors.title}>
            {(control) => (
              <Input {...control} ref={ref("title") as Ref<HTMLInputElement>} autoComplete="off" value={form.title} onChange={(event) => change("title", event.target.value)} />
            )}
          </Field>
          <Field label="Компанія" error={errors.company}>
            {(control) => (
              <Input {...control} ref={ref("company") as Ref<HTMLInputElement>} autoComplete="off" value={form.company} onChange={(event) => change("company", event.target.value)} />
            )}
          </Field>
        </div>
        {general === null ? null : (
          <p role="alert" className="rounded-lg bg-status-danger px-3 py-2 text-caption font-medium text-status-danger-foreground">
            {general}
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          <Button type="submit" disabled={pending}>
            Додати
          </Button>
          <Button asChild variant="secondary">
            <Link to={back}>Скасувати</Link>
          </Button>
        </div>
      </form>
    </>
  );
}
