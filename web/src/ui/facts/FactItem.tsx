import { memo } from "react";
import { Link } from "react-router";

import { KIND_LABELS, SOURCE_LABELS, type Fact, type FactDraft } from "../../domain/facts";
import { Badge } from "../components/badge";
import { Button } from "../components/button";
import { Checkbox } from "../components/checkbox";
import { FactEditor } from "./FactEditor";

interface FactItemProps {
  fact: Fact;
  selected: boolean;
  /** Чернетка, якщо факт зараз редагується. */
  draft: FactDraft | null;
  /** Обробники стабільні й беруть факт чи id: у списку з тисячі фактів перемальовується лише той, що змінився. */
  onSelect(id: number, selected: boolean): void;
  onConfirm(fact: Fact): void;
  onEdit(fact: Fact): void;
  onDraft(id: number, draft: FactDraft): void;
  onCancel(id: number): void;
  onDelete(fact: Fact): void;
  onSaved(fact: Fact): void;
  onGone(id: number): void;
}

/** Факт: чекбокс, ID, категорія, текстовий статус і дії; редактор розкривається на місці тексту. */
export const FactItem = memo(function FactItem({ fact, selected, draft, onSelect, onConfirm, onEdit, onDraft, onCancel, onDelete, onSaved, onGone }: FactItemProps) {
  return (
    <li aria-label={`Факт ${fact.id}`} className="min-w-0 rounded-xl border border-border bg-card p-4">
      <div className="flex items-start gap-3">
        <Checkbox aria-label={`Вибрати факт ${fact.id}`} checked={selected} onCheckedChange={(next) => onSelect(fact.id, next === true)} className="mt-0.5" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-caption text-muted-foreground">
            <span className="tabular-nums">#{fact.id}</span>
            <span>{KIND_LABELS[fact.kind]}</span>
            <Badge tone={fact.confirmed ? "success" : "warning"}>{fact.confirmed ? "Підтверджено" : "Потребує перевірки"}</Badge>
            <Badge>{SOURCE_LABELS[fact.source]}</Badge>
            {fact.source === "chat" && fact.jobId !== null ? (
              <Link to={`/vacancies/${fact.jobId}`} className="underline underline-offset-2">{`Вакансія #${fact.jobId}`}</Link>
            ) : null}
          </div>
          {draft === null ? (
            <>
              <p className="mt-2 text-base [overflow-wrap:anywhere]">{fact.text}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {fact.confirmed ? null : (
                  <Button size="sm" aria-label={`Підтвердити факт ${fact.id}`} onClick={() => onConfirm(fact)}>
                    Підтвердити
                  </Button>
                )}
                <Button size="sm" variant="secondary" data-edit-button={fact.id} aria-label={`Редагувати факт ${fact.id}`} onClick={() => onEdit(fact)}>
                  Редагувати
                </Button>
              </div>
            </>
          ) : (
            <FactEditor
              fact={fact}
              draft={draft}
              onDraft={(next) => onDraft(fact.id, next)}
              onCancel={() => onCancel(fact.id)}
              onDelete={() => onDelete(fact)}
              onSaved={onSaved}
              onGone={() => onGone(fact.id)}
            />
          )}
        </div>
      </div>
    </li>
  );
});
