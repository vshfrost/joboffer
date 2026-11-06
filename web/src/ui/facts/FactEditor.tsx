import { useEffect, useRef, useState, type FormEvent } from "react";

import { FACT_KINDS, KIND_LABELS, type Fact, type FactDraft, type FactKind } from "../../domain/facts";
import { Button } from "../components/button";
import { Field } from "../components/field";
import { Select } from "../components/select";
import { Textarea } from "../components/textarea";
import { useFactsServices } from "./FactsServices";

export const SAVE_FAILED = "Не вдалося зберегти зміни. Чернетку збережено — спробуй ще раз.";

interface FactEditorProps {
  fact: Fact;
  draft: FactDraft;
  onDraft(draft: FactDraft): void;
  onCancel(): void;
  onDelete(): void;
  /** Сервер прийняв зміни: `fact` уже непідтверджений. */
  onSaved(fact: Fact): void;
  /** Факту вже нема (404): редактор закрити, список оновити. */
  onGone(): void;
}

/** Редактор розкривається на місці запису. Помилка сервера лишає чернетку й редактор відкритими. */
export function FactEditor({ fact, draft, onDraft, onCancel, onDelete, onSaved, onGone }: FactEditorProps) {
  const services = useFactsServices();
  const textRef = useRef<HTMLTextAreaElement>(null);
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
    const outcome = await services.update(fact.id, draft);
    if (outcome.ok) {
      onSaved(outcome.fact);
      return;
    }
    if (outcome.kind === "not-found") {
      onGone();
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
      setGeneral(SAVE_FAILED);
    }
  }

  return (
    <form aria-label={`Редагування факту ${fact.id}`} onSubmit={(event) => void submit(event)} className="mt-3 flex flex-col gap-4">
      <Field label="Категорія" error={fieldErrors["kind"]}>
        {(controls) => (
          <Select {...controls} value={draft.kind} onChange={(event) => onDraft({ ...draft, kind: event.target.value as FactKind })}>
            {FACT_KINDS.map((kind) => (
              <option key={kind} value={kind}>
                {KIND_LABELS[kind]}
              </option>
            ))}
          </Select>
        )}
      </Field>
      <Field label="Формулювання факту" error={fieldErrors["text"]}>
        {(controls) => <Textarea {...controls} ref={textRef} value={draft.text} onChange={(event) => onDraft({ ...draft, text: event.target.value })} />}
      </Field>
      <p className="text-caption text-muted-foreground">Після збереження факт стане непідтвердженим — його потрібно підтвердити знову.</p>
      {general === null ? null : (
        <p role="alert" className="rounded-lg bg-status-danger px-3 py-2 text-caption font-medium text-status-danger-foreground">
          {general}
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={pending}>
          Зберегти
        </Button>
        <Button type="button" variant="secondary" onClick={onCancel}>
          Скасувати
        </Button>
        <Button type="button" variant="ghost" className="text-destructive sm:ml-auto" onClick={onDelete}>
          Видалити
        </Button>
      </div>
    </form>
  );
}
