import { madridDay } from "../../domain/jobs";
import type { CvState } from "./useFactLibrary";

/** Оригінал CV, з якого Claude розібрав факти: згорнутий, текст лише як текст. */
export function OriginalCvPanel({ cv }: { cv: CvState }) {
  if (cv.status === "loading") {
    return null;
  }
  if (cv.status === "error") {
    return <p className="text-caption text-muted-foreground">Не вдалося завантажити оригінальний CV.</p>;
  }
  if (cv.cv === null) {
    return <p className="text-caption text-muted-foreground">Оригінальний CV ще не збережено.</p>;
  }
  const summary = ["Оригінальний CV", cv.cv.fileName, madridDay(cv.cv.savedAt)].filter((part) => part !== null).join(" · ");
  return (
    <details className="group rounded-xl border border-border bg-card px-4 py-3">
      <summary className="cursor-pointer text-nav font-medium">{summary}</summary>
      <pre className="mt-3 max-h-96 overflow-auto font-sans text-caption whitespace-pre-wrap [overflow-wrap:anywhere]">{cv.cv.text}</pre>
    </details>
  );
}
