import { useId } from "react";

import { uniqueCount } from "../../domain/profileForms";
import { plural } from "../../domain/profileSummary";
import { Textarea } from "../components/textarea";
import { cn } from "../lib/cn";
import { EditorLayout } from "./EditorLayout";
import { useProfile } from "./ProfileProvider";
import { SectionFrame } from "./SectionFrame";

const KNOWN = ["title_keywords", "title_exclude", "stop_words"];

interface RuleBlockProps {
  label: string;
  hint: string;
  /** Що показати, коли список порожній. */
  emptyLabel: string;
  value: string;
  error: string | undefined;
  /** Не перший у групі: відділяється рискою від попереднього. */
  separated?: boolean;
  onChange: (value: string) => void;
}

/** Один список правил: назва, лічильник, пояснення й поле «по слову на рядок». */
function RuleBlock({ label, hint, emptyLabel, value, error, separated = false, onChange }: RuleBlockProps) {
  const id = useId();
  const hintId = `${id}-hint`;
  const countId = `${id}-count`;
  const errorId = `${id}-error`;
  const count = uniqueCount(value);
  return (
    <section className={cn("flex min-w-0 flex-col gap-1.5", separated && "border-t border-border pt-5")}>
      <div className="flex items-center justify-between gap-2">
        <label htmlFor={id} className="text-nav font-medium">
          {label}
        </label>
        <span id={countId} className="rounded-md bg-muted px-2 py-0.5 text-caption text-muted-foreground tabular">
          {count === 0 ? emptyLabel : `${count} ${plural(count, "слово", "слова", "слів")}`}
        </span>
      </div>
      <p id={hintId} className="text-caption text-muted-foreground">
        {hint}
      </p>
      <Textarea
        id={id}
        rows={5}
        value={value}
        aria-invalid={error === undefined ? undefined : true}
        aria-describedby={[hintId, countId, error === undefined ? null : errorId].filter((part) => part !== null).join(" ")}
        onChange={(event) => onChange(event.target.value)}
      />
      <p className="text-caption text-muted-foreground">По одному слову на рядок.</p>
      {error === undefined ? null : (
        <p id={errorId} className="text-caption font-medium text-destructive">
          {error}
        </p>
      )}
    </section>
  );
}

export function RulesEditor() {
  const api = useProfile().section("rules");
  const { form, fieldErrors } = api;
  return (
    <EditorLayout current="rules">
      <SectionFrame
        api={api}
        title="Правила відбору"
        description="Що імпортувати з джерел, що відхиляти й що показувати нижче."
        knownFields={KNOWN}
      >
        <RuleBlock
          label="Імпортувати, якщо назва містить"
          hint="Достатньо збігу одного слова в назві. Порожньо — без обмеження."
          emptyLabel="Без обмеження"
          value={form.titleKeywords}
          error={fieldErrors["title_keywords"]}
          onChange={(titleKeywords) => api.change({ titleKeywords }, ["title_keywords"])}
        />
        <RuleBlock
          label="Не імпортувати"
          hint="Вакансії з будь-яким із цих слів у назві з джерел не імпортуються."
          emptyLabel="Порожньо"
          separated
          value={form.titleExclude}
          error={fieldErrors["title_exclude"]}
          onChange={(titleExclude) => api.change({ titleExclude }, ["title_exclude"])}
        />
        <RuleBlock
          label="Знижувати пріоритет"
          hint="Вакансії з цими словами опускаються вниз списку при аналізі, але з імпорту не виключаються."
          emptyLabel="Порожньо"
          separated
          value={form.stopWords}
          error={fieldErrors["stop_words"]}
          onChange={(stopWords) => api.change({ stopWords }, ["stop_words"])}
        />
      </SectionFrame>
    </EditorLayout>
  );
}
