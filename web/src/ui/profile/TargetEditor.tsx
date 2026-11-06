import { SENIORITIES } from "../../domain/profile";
import { levelLabel } from "../../domain/profileSummary";
import { Checkbox } from "../components/checkbox";
import { Field } from "../components/field";
import { Input } from "../components/input";
import { Textarea } from "../components/textarea";
import { EditorLayout } from "./EditorLayout";
import { useProfile } from "./ProfileProvider";
import { SectionFrame } from "./SectionFrame";

const KNOWN = ["roles", "seniority", "min_salary_eur", "target_domains"];

export function TargetEditor() {
  const api = useProfile().section("target");
  const { form, fieldErrors } = api;

  function toggle(level: (typeof SENIORITIES)[number], checked: boolean) {
    const next = checked ? [...form.seniority, level] : form.seniority.filter((item) => item !== level);
    api.change({ seniority: SENIORITIES.filter((item) => next.includes(item)) }, ["seniority"]);
  }

  return (
    <EditorLayout current="target">
      <SectionFrame
        api={api}
        title="Кар’єрна ціль"
        description="Побажання для оцінки відповідності: ким, на якому рівні й у якій галузі хочеш працювати."
        knownFields={KNOWN}
      >
        <Field label="Цільові ролі" hint="Одна роль на рядок." error={fieldErrors["roles"]}>
          {(control) => (
            <Textarea {...control} rows={4} value={form.roles} onChange={(event) => api.change({ roles: event.target.value }, ["roles"])} />
          )}
        </Field>
        <fieldset className="flex min-w-0 flex-col gap-1.5" aria-describedby={fieldErrors["seniority"] === undefined ? undefined : "seniority-error"}>
          <legend className="mb-1.5 text-nav font-medium">Рівень</legend>
          <div className="flex flex-wrap gap-x-5 gap-y-1">
            {SENIORITIES.map((level) => {
              const id = `seniority-${level}`;
              return (
                <div key={level} className="flex min-h-10 items-center gap-2 pointer-coarse:min-h-11">
                  <Checkbox id={id} checked={form.seniority.includes(level)} onCheckedChange={(checked) => toggle(level, checked === true)} />
                  <label htmlFor={id} className="text-nav">
                    {levelLabel(level)}
                  </label>
                </div>
              );
            })}
          </div>
          {fieldErrors["seniority"] === undefined ? null : (
            <p id="seniority-error" className="text-caption font-medium text-destructive">
              {fieldErrors["seniority"]}
            </p>
          )}
        </fieldset>
        <Field label="Мінімальна зарплата" hint="EUR брутто на рік" error={fieldErrors["min_salary_eur"]}>
          {(control) => (
            <Input
              {...control}
              inputMode="numeric"
              autoComplete="off"
              className="aria-invalid:border-destructive"
              value={form.minSalary}
              onChange={(event) => api.change({ minSalary: event.target.value }, ["min_salary_eur"])}
            />
          )}
        </Field>
        <Field label="Цільові галузі" hint="Одна галузь на рядок." error={fieldErrors["target_domains"]}>
          {(control) => (
            <Textarea
              {...control}
              rows={3}
              value={form.targetDomains}
              onChange={(event) => api.change({ targetDomains: event.target.value }, ["target_domains"])}
            />
          )}
        </Field>
      </SectionFrame>
    </EditorLayout>
  );
}
