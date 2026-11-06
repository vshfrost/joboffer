import { Plus, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { WORK_MODES, type WorkMode } from "../../domain/profile";
import { newLocationRow, type LocationRowForm } from "../../domain/profileForms";
import { modeLabel } from "../../domain/profileSummary";
import { Button } from "../components/button";
import { Checkbox } from "../components/checkbox";
import { Field } from "../components/field";
import { Input } from "../components/input";
import { Textarea } from "../components/textarea";
import { EditorLayout } from "./EditorLayout";
import { useProfile } from "./ProfileProvider";
import { SectionFrame } from "./SectionFrame";

/** Ключі нових рядків унікальні за все життя сторінки: чернетка переживає перемонтування редактора. */
let rowCounter = 0;
const freshKey = () => `new-${(rowCounter += 1)}`;

type Focus = { kind: "place"; key: string } | { kind: "add" };

function toggled(modes: WorkMode[], mode: WorkMode, on: boolean): WorkMode[] {
  const next = on ? [...modes, mode] : modes.filter((item) => item !== mode);
  return WORK_MODES.filter((item) => next.includes(item));
}

function outsideGlobal(row: LocationRowForm, global: WorkMode[]): WorkMode[] {
  return global.length === 0 ? [] : row.workModes.filter((mode) => !global.includes(mode));
}

function ModeChoices({
  idPrefix,
  modes,
  onChange,
}: {
  idPrefix: string;
  modes: WorkMode[];
  onChange: (next: WorkMode[]) => void;
}) {
  return (
    <div className="flex flex-wrap gap-x-5 gap-y-1">
      {WORK_MODES.map((mode) => {
        const id = `${idPrefix}-${mode}`;
        return (
          <div key={mode} className="flex min-h-10 items-center gap-2 pointer-coarse:min-h-11">
            <Checkbox id={id} checked={modes.includes(mode)} onCheckedChange={(on) => onChange(toggled(modes, mode, on === true))} />
            <label htmlFor={id} className="text-nav">
              {modeLabel(mode)}
            </label>
          </div>
        );
      })}
    </div>
  );
}

export function LocationsEditor() {
  const api = useProfile().section("locations");
  const { form, fieldErrors } = api;
  const places = useRef(new Map<string, HTMLInputElement>());
  const addButton = useRef<HTMLButtonElement>(null);
  const [focus, setFocus] = useState<Focus | null>(null);

  // Фокус після додавання чи видалення рядка: рядки вже перемальовано.
  useEffect(() => {
    if (focus === null) {
      return;
    }
    (focus.kind === "add" ? addButton.current : places.current.get(focus.key))?.focus();
    setFocus(null);
  }, [focus, form.rows]);

  function changeRow(index: number, patch: Partial<LocationRowForm>, cleared: string) {
    const rows = form.rows.map((row, position) => (position === index ? { ...row, ...patch } : row));
    api.change({ rows }, [`locations.${index}.${cleared}`]);
  }

  function addRow() {
    const row = newLocationRow(freshKey());
    api.change({ rows: [...form.rows, row] }, ["locations"]);
    setFocus({ kind: "place", key: row.key });
  }

  function removeRow(index: number) {
    const rows = form.rows.filter((_, position) => position !== index);
    // Рядки після видаленого зсунулись: їхні помилки за старими індексами більше не стосуються.
    api.change({ rows }, ["locations", ...Object.keys(fieldErrors).filter((field) => field.startsWith("locations."))]);
    const next = rows[Math.min(index, rows.length - 1)];
    setFocus(next === undefined ? { kind: "add" } : { kind: "place", key: next.key });
  }

  const known = [
    "work_modes",
    "locations",
    ...form.rows.flatMap((_, index) => ["place", "aliases", "work_modes"].map((part) => `locations.${index}.${part}`)),
  ];

  return (
    <EditorLayout current="locations">
      <SectionFrame
        api={api}
        title="Локації та формат"
        description="Спочатку обери доступні формати, потім — потрібні формати для кожного місця."
        knownFields={known}
      >
        <fieldset className="flex min-w-0 flex-col gap-1.5" aria-describedby="global-modes-hint global-modes-error">
          <legend className="mb-1.5 text-nav font-medium">Загальні формати</legend>
          <ModeChoices idPrefix="global" modes={form.workModes} onChange={(next) => api.change({ workModes: next }, ["work_modes"])} />
          <p id="global-modes-hint" className="text-caption text-muted-foreground">
            Загальні формати — окремий фільтр: вакансія з іншим форматом не проходить.
          </p>
          {fieldErrors["work_modes"] === undefined ? null : (
            <p id="global-modes-error" className="text-caption font-medium text-destructive">
              {fieldErrors["work_modes"]}
            </p>
          )}
        </fieldset>

        <div className="flex flex-col gap-3">
          <div>
            <h3 className="text-section font-semibold">Де шукаю</h3>
            <p className="text-caption text-muted-foreground">Для кожної локації можна обрати свій формат роботи.</p>
          </div>
          {form.rows.length === 0 ? (
            <p className="text-caption text-muted-foreground">Локацій ще нема — місце пошук не обмежує.</p>
          ) : null}
          {form.rows.map((row, index) => {
            const number = index + 1;
            const where = `locations.${index}`;
            const modesError = fieldErrors[`${where}.work_modes`];
            const outside = outsideGlobal(row, form.workModes);
            const modesErrorId = `${row.key}-modes-error`;
            const outsideId = `${row.key}-modes-outside`;
            const describedBy = [modesError === undefined ? null : modesErrorId, outside.length === 0 ? null : outsideId].filter(
              (id) => id !== null,
            );
            return (
              <fieldset key={row.key} className="grid min-w-0 gap-3 rounded-lg border border-border p-3">
                <legend className="px-1 text-nav font-medium">{`Локація ${number}`}</legend>
                <Field label="Місце" error={fieldErrors[`${where}.place`]}>
                  {(control) => (
                    <Input
                      {...control}
                      ref={(element) => {
                        if (element === null) {
                          places.current.delete(row.key);
                        } else {
                          places.current.set(row.key, element);
                        }
                      }}
                      autoComplete="off"
                      className="aria-invalid:border-destructive"
                      value={row.place}
                      onChange={(event) => changeRow(index, { place: event.target.value }, "place")}
                    />
                  )}
                </Field>
                <Field label="Синоніми" hint="Інші мови й написання, по одному на рядок." error={fieldErrors[`${where}.aliases`]}>
                  {(control) => (
                    <Textarea
                      {...control}
                      rows={2}
                      className="min-h-16"
                      value={row.aliases}
                      onChange={(event) => changeRow(index, { aliases: event.target.value }, "aliases")}
                    />
                  )}
                </Field>
                <fieldset className="min-w-0" aria-describedby={describedBy.length === 0 ? undefined : describedBy.join(" ")}>
                  <legend className="mb-1 text-nav font-medium">Формати місця</legend>
                  <ModeChoices
                    idPrefix={row.key}
                    modes={row.workModes}
                    onChange={(next) => changeRow(index, { workModes: next }, "work_modes")}
                  />
                  {outside.length === 0 ? null : (
                    <p id={outsideId} className="mt-1 text-caption text-muted-foreground">
                      {`${outside.length === 1 ? "Формат" : "Формати"} ${outside.map((mode) => `«${modeLabel(mode)}»`).join(", ")} ${
                        outside.length === 1 ? "не входить" : "не входять"
                      } до загальних форматів угорі.`}
                    </p>
                  )}
                  {modesError === undefined ? null : (
                    <p id={modesErrorId} className="mt-1 text-caption font-medium text-destructive">
                      {modesError}
                    </p>
                  )}
                </fieldset>
                <div>
                  <Button type="button" variant="ghost" size="sm" aria-label={`Видалити локацію ${number}`} onClick={() => removeRow(index)}>
                    <Trash2 aria-hidden="true" />
                    Видалити
                  </Button>
                </div>
              </fieldset>
            );
          })}
          <div className="flex flex-col items-start gap-1.5">
            <Button ref={addButton} type="button" variant="secondary" onClick={addRow}>
              <Plus aria-hidden="true" />
              Додати локацію
            </Button>
            {fieldErrors["locations"] === undefined ? null : (
              <p className="text-caption font-medium text-destructive">{fieldErrors["locations"]}</p>
            )}
          </div>
        </div>

        <div className="flex flex-col gap-1">
          {(
            [
              ["includeUnknownMode", "Брати вакансії з невідомим форматом, якщо локація підходить"],
              ["relocation", "Розглядаю релокейт"],
            ] as const
          ).map(([key, label]) => (
            <div key={key} className="flex min-h-10 items-center gap-2 pointer-coarse:min-h-11">
              <Checkbox id={`flag-${key}`} checked={form[key]} onCheckedChange={(on) => api.change({ [key]: on === true })} />
              <label htmlFor={`flag-${key}`} className="text-nav">
                {label}
              </label>
            </div>
          ))}
        </div>
      </SectionFrame>
    </EditorLayout>
  );
}
