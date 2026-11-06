import { useEffect, useRef, useState, type FormEvent } from "react";
import { useBlocker, useNavigate, useSearchParams, type Blocker } from "react-router";

import {
  COMPANY_PLATFORMS,
  FEED_SOURCES,
  PLATFORM_LABELS,
  sourcesQueryParams,
  type CompanyPlatform,
  type FeedSource,
  type NewSource,
  type SourceKind,
  type SourcesTab,
} from "../../domain/sources";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogTitle } from "../components/alert-dialog";
import { Button } from "../components/button";
import { Field } from "../components/field";
import { Input } from "../components/input";
import { Select } from "../components/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/tabs";
import { usePageTitle } from "../lib/usePageTitle";
import { PageHeading } from "../pages/PageHeading";
import { useSourcesServices } from "./SourcesServices";
import { problemText } from "./texts";

const SLUG_HINT = "Остання частина адреси сторінки вакансій. Наприклад, jobs.ashbyhq.com/acme → acme.";
const QUERY_HINT = "Без пробілів. DOU: category=Python&remote · Djinni: primary_keyword=Python&exp_level=5y";
const QUERY_PLACEHOLDER: Record<FeedSource, string> = { dou: "category=Python&remote", djinni: "primary_keyword=Python" };

type FormErrors = Readonly<Record<string, string>>;

const TAB_BY_KIND: Record<SourceKind, SourcesTab> = { company: "companies", feed: "feeds" };

/** `/sources/new`: форма «Додати джерело» — компанія на ATS (з пробним запитом) або RSS-стрічка. */
export function AddSourcePage() {
  usePageTitle("Додати джерело");
  const services = useSourcesServices();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const origin: SourcesTab = params.get("tab") === "feeds" ? "feeds" : "companies";
  const [kind, setKind] = useState<SourceKind>(origin === "feeds" ? "feed" : "company");
  const [platform, setPlatform] = useState<CompanyPlatform>("greenhouse");
  const [feedSource, setFeedSource] = useState<FeedSource>("dou");
  const [key, setKey] = useState("");
  const [name, setName] = useState("");
  const [errors, setErrors] = useState<FormErrors>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const form = useRef<HTMLFormElement>(null);
  const done = useRef(false);

  const dirty = key.trim() !== "" || name.trim() !== "";
  const blocker = useBlocker(() => dirty && !done.current);
  useBeforeUnloadWarning(dirty);

  // Після відмови фокус іде на перше поле з помилкою.
  useEffect(() => {
    if (Object.keys(errors).length > 0) {
      form.current?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus();
    }
  }, [errors]);

  const back = origin === "feeds" ? "/sources?tab=feeds" : "/sources";

  function edit(change: () => void) {
    change();
    setErrors({});
    setFailure(null);
  }

  function switchKind(next: SourceKind) {
    edit(() => {
      setKind(next);
      setPlatform("greenhouse");
      setFeedSource("dou");
      setKey("");
      setName("");
    });
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setErrors({});
    setFailure(null);
    const input: NewSource =
      kind === "company" ? { kind, platform, slug: key.trim(), name: name.trim() } : { kind, source: feedSource, query: key.trim() };
    const outcome = await services.add(input);
    if (outcome.ok) {
      done.current = true;
      const search = sourcesQueryParams({ tab: TAB_BY_KIND[kind], q: "", status: "", open: outcome.source.id });
      void navigate(`/sources?${search}`, { state: { message: "Джерело додано. Перший прогін ще не виконувався." } });
      return;
    }
    setPending(false);
    if (outcome.kind === "invalid") {
      const known = kind === "company" ? ["platform", "slug", "name"] : ["source", "query"];
      const shown = Object.fromEntries(Object.entries(outcome.fieldErrors).filter(([field]) => known.includes(field)));
      setErrors(shown);
      // Помилка поза полями форми (наприклад, загальна перевірка запиту) не губиться.
      setFailure(Object.keys(shown).length === 0 ? outcome.message : null);
    } else {
      setFailure(problemText(outcome.kind, "додати джерело", "Не вдалося додати джерело. Спробуй ще раз."));
    }
  }

  return (
    <>
      <Button type="button" variant="secondary" className="mb-4" onClick={() => void navigate(back)}>
        ← До джерел
      </Button>
      <PageHeading title="Додати джерело" subtitle="Компанію перед додаванням перевіряє пробний запит до платформи." />
      <form ref={form} noValidate onSubmit={(event) => void submit(event)} className="flex max-w-xl flex-col gap-5 rounded-xl border border-border bg-card p-5 max-sm:p-4">
        <Tabs value={kind} onValueChange={(next) => switchKind(next as SourceKind)}>
          <TabsList aria-label="Тип нового джерела">
            <TabsTrigger value="company">Компанія</TabsTrigger>
            <TabsTrigger value="feed">RSS-стрічка</TabsTrigger>
          </TabsList>
          <TabsContent value="company" className="flex flex-col gap-5">
            <Field label="ATS-платформа" error={errors["platform"]}>
              {(controls) => (
                <Select {...controls} value={platform} onChange={(event) => edit(() => setPlatform(event.target.value as CompanyPlatform))}>
                  {COMPANY_PLATFORMS.map((value) => (
                    <option key={value} value={value}>
                      {PLATFORM_LABELS[value]}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <Field label="Слаг компанії" hint={SLUG_HINT} error={errors["slug"]}>
              {(controls) => <Input {...controls} value={key} placeholder="acme" autoComplete="off" onChange={(event) => edit(() => setKey(event.target.value))} />}
            </Field>
            <Field label="Назва компанії · необов’язково" hint="Без назви буде використано слаг." error={errors["name"]}>
              {(controls) => <Input {...controls} value={name} placeholder="Acme" autoComplete="off" onChange={(event) => edit(() => setName(event.target.value))} />}
            </Field>
          </TabsContent>
          <TabsContent value="feed" className="flex flex-col gap-5">
            <Field label="RSS-джерело" error={errors["source"]}>
              {(controls) => (
                <Select {...controls} value={feedSource} onChange={(event) => edit(() => setFeedSource(event.target.value as FeedSource))}>
                  {FEED_SOURCES.map((value) => (
                    <option key={value} value={value}>
                      {PLATFORM_LABELS[value]}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <Field label="Параметри запиту" hint={QUERY_HINT} error={errors["query"]}>
              {(controls) => (
                <Input {...controls} value={key} placeholder={QUERY_PLACEHOLDER[feedSource]} autoComplete="off" onChange={(event) => edit(() => setKey(event.target.value))} />
              )}
            </Field>
          </TabsContent>
        </Tabs>
        {failure === null ? null : (
          <p role="alert" className="rounded-lg bg-status-danger px-3 py-2 text-caption font-medium text-status-danger-foreground">
            {failure}
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          <Button type="submit" disabled={pending}>
            {kind === "company" ? "Перевірити й додати" : "Додати стрічку"}
          </Button>
          <Button type="button" variant="secondary" onClick={() => void navigate(back)}>
            Скасувати
          </Button>
        </div>
      </form>
      {blocker.state === "blocked" ? <CloseDialog blocker={blocker} /> : null}
    </>
  );
}

/** Закриття чи перезавантаження вкладки із заповненою формою просить підтвердження. */
function useBeforeUnloadWarning(active: boolean) {
  useEffect(() => {
    if (!active) {
      return;
    }
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [active]);
}

type Blocked = Extract<Blocker, { state: "blocked" }>;

function CloseDialog({ blocker }: { blocker: Blocked }) {
  // «Закрити» теж закриває діалог: це закриття не має скасовувати перехід.
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
        <AlertDialogTitle>Закрити форму?</AlertDialogTitle>
        <AlertDialogDescription>Введені дані не буде збережено.</AlertDialogDescription>
        <div className="mt-5 flex flex-wrap justify-end gap-2">
          <AlertDialogCancel asChild>
            <Button type="button" variant="secondary">
              Скасувати
            </Button>
          </AlertDialogCancel>
          <AlertDialogAction asChild>
            <Button
              type="button"
              onClick={() => {
                leaving.current = true;
                blocker.proceed();
              }}
            >
              Закрити
            </Button>
          </AlertDialogAction>
        </div>
      </AlertDialogContent>
    </AlertDialog>
  );
}
