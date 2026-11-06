import { useEffect, useRef, useState, type FormEvent } from "react";

import { FACT_KINDS, KIND_LABELS, type Fact, type FactDraft, type FactKind } from "../../domain/facts";
import { Button } from "../components/button";
import { Field } from "../components/field";
import { Select } from "../components/select";
import { Textarea } from "../components/textarea";
import { useFactsServices } from "./FactsServices";

export const ADD_FAILED = "Не вдалося додати факт. Чернетку збережено — спробуй ще раз.";

interface AddFactFormProps {
  /** Сервер прийняв факт: він уже підтверджений. */
  onAdded(fact: Fact): void;
  onCancel(): void;
}

/** Форма нового факту: вид і текст. Помилка сервера лишає форму й введене на місці. */
export function AddFactForm({ onAdded, onCancel }: AddFactFormProps) {
  const services = useFactsServices();
  const textRef = useRef<HTMLTextAreaElement>(null);
  const [draft, setDraft] = useState<FactDraft>({ kind: FACT_KINDS[0], text: "" });
  const [pending, setPending] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [general, setGeneral] = useState<string | null>(null);

  useEffect(() => {
    textRef.current?.focus();
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (pending) {
      return;
    }
    setPending(true);
    setFieldErrors({});
    setGeneral(null);
    const outcome = await services.create(draft);
    if (outcome.ok) {
      onAdded(outcome.fact);
      return;
    }
    setPending(false);
    if (outcome.kind === "invalid") {
      // Помилку поля показуємо біля нього; без розпізнаного поля — загальним текстом.
      const known = { ...(outcome.fieldErrors["kind"] === undefined ? {} : { kind: outcome.fieldErrors["kind"] }), ...(outcome.fieldErrors["text"] === undefined ? {} : { text: outcome.fieldErrors["text"] }) };
      setFieldErrors(known);
      setGeneral(Object.keys(known).length === 0 ? outcome.message : null);
    } else if (outcome.kind === "conflict") {
      setFieldErrors({ text: outcome.message });
    } else {
      setGeneral(ADD_FAILED);
    }
  }

  return (
    <form aria-label="Новий факт" onSubmit={(event) => void submit(event)} className="flex flex-col gap-4 rounded-xl border border-border bg-card p-4">
      <Field label="Категорія" error={fieldErrors["kind"]}>
        {(controls) => (
          <Select {...controls} value={draft.kind} onChange={(event) => setDraft({ ...draft, kind: event.target.value as FactKind })}>
            {FACT_KINDS.map((kind) => (
              <option key={kind} value={kind}>
                {KIND_LABELS[kind]}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <Field label="Формулювання факту" error={fieldErrors["text"]}>
        {(controls) => <Textarea {...controls} ref={textRef} value={draft.text} onChange={(event) => setDraft({ ...draft, text: event.target.value })} />}
      </Field>
      {general === null ? null : (
        <p role="alert" className="rounded-lg bg-status-danger px-3 py-2 text-caption font-medium text-status-danger-foreground">
          {general}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={pending}>
          Додати
        </Button>
        <Button type="button" variant="secondary" onClick={onCancel}>
          Скасувати
        </Button>
      </div>
    </form>
  );
}
