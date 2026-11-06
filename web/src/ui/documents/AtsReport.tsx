import type { LintReport } from "../../domain/documents";
import { pagesText } from "../../domain/documents";
import { Disclosure } from "./Disclosure";

const WRAP = "[overflow-wrap:anywhere]";

/** Повний ATS-звіт версії за вимогою: зауваження, сторінки, що є й чого нема з ключових слів. Звіт — знімок на момент збереження. */
export function AtsReport({ lint }: { lint: LintReport | null }) {
  return (
    <Disclosure label="Розгорнути звіт ATS" className="mt-1">
      <div className="flex flex-col gap-2 rounded-lg bg-background p-3 text-caption">
        {lint === null ? <p>Ця версія не має збереженого звіту. Це не означає, що перевірку пройдено.</p> : <Report lint={lint} />}
      </div>
    </Disclosure>
  );
}

function Report({ lint }: { lint: LintReport }) {
  return (
    <>
      <p className="font-semibold">{lint.issues.length === 0 ? "Технічних зауважень немає" : "Потребує уваги"}</p>
      {lint.issues.map((issue) => (
        <p key={`${issue.code}:${issue.message}`} className={WRAP}>{`⚠ ${issue.message}`}</p>
      ))}
      <p>{`${pagesText(lint.pages)} · Звіт збережено разом із цією версією.`}</p>
      {lint.keywords === null ? (
        <p>Покриття ключових слів не рахувалося: вакансію не аналізовано.</p>
      ) : (
        <>
          <Keywords title="Є у документі" words={lint.keywords.covered} tone="found" />
          <Keywords title="Не знайдено" words={lint.keywords.missing} tone="missing" />
          <p className="text-muted-foreground">Покриття ключових слів не визначає статус ATS. Не додавайте навички, яких не підтверджують ваші факти.</p>
        </>
      )}
    </>
  );
}

function Keywords({ title, words, tone }: { title: string; words: string[]; tone: "found" | "missing" }) {
  const style = tone === "found" ? "bg-status-success text-status-success-foreground" : "bg-status-warning text-status-warning-foreground";
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <p className="font-semibold">{title}</p>
      <p className="flex min-w-0 flex-wrap gap-1">
        {words.length === 0 ? (
          <span className="text-muted-foreground">—</span>
        ) : (
          words.map((word) => (
            <span key={word} className={`rounded px-1.5 py-0.5 text-xs ${style} ${WRAP}`}>
              {word}
            </span>
          ))
        )}
      </p>
    </div>
  );
}
