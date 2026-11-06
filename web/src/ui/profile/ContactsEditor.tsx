import { useId } from "react";

import type { Contacts } from "../../domain/profile";
import { Field } from "../components/field";
import { Input } from "../components/input";
import { EditorLayout } from "./EditorLayout";
import { useProfile } from "./ProfileProvider";
import { SectionFrame } from "./SectionFrame";

interface FieldSpec {
  key: keyof Contacts;
  /** Назва поля в API: за нею сервер повертає помилку. */
  field: string;
  label: string;
  hint?: string;
  type?: "email" | "tel" | "url" | "text";
}

const FIELDS: readonly FieldSpec[] = [
  { key: "fullName", field: "full_name", label: "Ім’я латиницею" },
  { key: "city", field: "city", label: "Місто" },
  { key: "email", field: "email", label: "Email", type: "email" },
  { key: "phone", field: "phone", label: "Телефон", type: "tel" },
  { key: "linkedinUrl", field: "linkedin_url", label: "LinkedIn", type: "url" },
  { key: "githubUrl", field: "github_url", label: "GitHub", type: "url" },
  {
    key: "workAuthorization",
    field: "work_authorization",
    label: "Дозвіл на роботу",
    hint: "Короткий текст англійською для документів.",
  },
];

const KNOWN = FIELDS.map(({ field }) => field);

const joined = (...parts: string[]) => parts.filter((part) => part !== "").join(" · ");

export function ContactsEditor() {
  const api = useProfile().section("contacts");
  const { form, fieldErrors } = api;
  const previewId = useId();
  return (
    <EditorLayout current="contacts">
      <SectionFrame
        api={api}
        title="Контакти для CV"
        description="Ці дані потрапляють у шапку CV та супровідного листа."
        knownFields={KNOWN}
      >
        <div className="grid gap-5 md:grid-cols-2">
          {FIELDS.map(({ key, field, label, hint, type }) => (
            <Field key={key} label={label} hint={hint} error={fieldErrors[field]} className={key === "workAuthorization" ? "md:col-span-2" : undefined}>
              {(control) => (
                <Input
                  {...control}
                  type={type ?? "text"}
                  autoComplete="off"
                  className="aria-invalid:border-destructive"
                  value={form[key]}
                  onChange={(event) => api.change({ [key]: event.target.value }, [field])}
                />
              )}
            </Field>
          ))}
        </div>
        <section aria-labelledby={previewId} className="min-w-0 rounded-lg border border-border bg-background p-4">
          <h3 id={previewId} className="text-caption font-semibold tracking-wide text-muted-foreground uppercase">
            Попередній перегляд контактів
          </h3>
          <p className="mt-2 text-section font-semibold [overflow-wrap:anywhere]">{form.fullName === "" ? "Ім’я" : form.fullName}</p>
          <p className="text-caption text-muted-foreground [overflow-wrap:anywhere]">{joined(form.city, form.workAuthorization)}</p>
          <p className="text-caption text-muted-foreground [overflow-wrap:anywhere]">{joined(form.email, form.phone)}</p>
        </section>
      </SectionFrame>
    </EditorLayout>
  );
}
