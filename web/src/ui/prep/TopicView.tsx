import { Link } from "react-router";
import { useState } from "react";

import {
  jobFullLabel,
  KIND_LABELS,
  progressText,
  remainingText,
  type Topic,
} from "../../domain/prep";
import { REQUESTS } from "../../domain/prompts";
import { DelegateToAgent } from "../agents/DelegateToAgent";
import { Button } from "../components/button";
import { usePageTitle } from "../lib/usePageTitle";
import { usePrepServices } from "./PrepServices";
import { ProgressBar } from "./ProgressBar";
import { StepItem, type SaveStepResult } from "./StepItem";
import { problemText } from "./texts";
import { TopicBadge } from "./TopicBadge";

const LINK = "inline-flex items-center text-primary [overflow-wrap:anywhere] hover:underline pointer-coarse:min-h-11";

interface TopicViewProps {
  topic: Topic;
  message: string;
  setMessage(message: string): void;
  /** Тему оновлено відповіддю сервера (після «виконано» чи «готово»). */
  onChange(topic: Topic): void;
  /** Тема чи крок зникли: сторінку треба завантажити наново. */
  onGone(): void;
}

/** Сторінка теми: опис, прогрес, вакансії з прогалинами, кроки, квіз і ручна готовність. */
export function TopicView({ topic, message, setMessage, onChange, onGone }: TopicViewProps) {
  usePageTitle(topic.title);
  const services = usePrepServices();
  const [readyBusy, setReadyBusy] = useState(false);
  const ready = topic.status === "ready";
  // Розкривається перший невиконаний крок на момент показу сторінки.
  const [initialNext] = useState(topic.nextStepId);

  async function saveStep(stepId: number, note: string): Promise<SaveStepResult> {
    setMessage("");
    const outcome = await services.completeStep(stepId, note);
    if (outcome.ok) {
      onChange(outcome.topic);
      setMessage("Збережено. Прогрес і залишок часу оновлено.");
      return { ok: true };
    }
    if (outcome.kind === "invalid") {
      return { ok: false, fieldError: Object.values(outcome.fieldErrors)[0] };
    }
    if (outcome.kind === "not-found") {
      setMessage("Цього кроку вже немає — тему оновлено.");
      onGone();
    } else {
      setMessage(problemText(outcome.kind, "зберегти нотатку", "Не вдалося зберегти. Спробуй ще раз."));
    }
    return { ok: false };
  }

  async function toggleReady() {
    setReadyBusy(true);
    setMessage("");
    const outcome = await services.setReady(topic.id, !ready);
    setReadyBusy(false);
    if (outcome.ok) {
      onChange(outcome.topic);
      setMessage(ready ? "Позначку знято. Готовність обчислено за кроками." : "Тему позначено готовою.");
    } else if (outcome.kind === "not-found") {
      onGone();
    } else {
      setMessage(problemText(outcome.kind, "змінити готовність", "Не вдалося змінити готовність. Спробуй ще раз."));
    }
  }

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <div className="flex flex-col gap-3">
        <Link to="/prep" className={`${LINK} self-start`}>
          ← Усі теми
        </Link>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <h1 className="min-w-0 text-page-title font-semibold tracking-tight [overflow-wrap:anywhere]">{topic.title}</h1>
          <TopicBadge status={topic.status} />
        </div>
        <p className="text-caption text-muted-foreground">{`${KIND_LABELS[topic.kind]} · тема #${topic.id}${topic.deadline === null ? "" : ` · дедлайн ${topic.deadline}`}`}</p>
        <p className="[overflow-wrap:anywhere]">{topic.summary}</p>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-baseline gap-2">
            <span className="sr-count">{topic.percent}%</span>
            <span>{`${progressText(topic)} кроків`}</span>
          </div>
          <span className="text-caption text-muted-foreground">{remainingText(topic)}</span>
        </div>
        <ProgressBar percent={topic.percent} label={topic.title} />
      </div>

      <details className="rounded-lg border border-border bg-card">
        <summary className="flex cursor-pointer items-center gap-2 p-3.5 font-medium pointer-coarse:min-h-11">
          Вакансії та прогалини <span className="sr-count">{topic.jobs.length}</span>
        </summary>
        <ul className="m-0 list-none p-0">
          {topic.jobs.map((job) => (
            <li key={job.jobId} className="min-w-0 border-t border-border px-3.5 py-3">
              <Link to={`/vacancies/${job.jobId}`} className={`${LINK} font-medium`}>
                {jobFullLabel(job)} <span className="sr-count ml-1">{job.score}/100</span>
              </Link>
              <p className="text-caption text-muted-foreground [overflow-wrap:anywhere]">{job.gap}</p>
            </li>
          ))}
        </ul>
      </details>

      <section aria-label="План теми" className="flex flex-col gap-3">
        <h2 className="text-section font-semibold">План теми</h2>
        {topic.steps.length === 0 ? (
          <>
            <h3 className="font-semibold">Плану ще немає</h3>
            <DelegateToAgent request={REQUESTS.plan(topic.id)} description="Агент складе план теми: вивчення → практика → перевірка." />
          </>
        ) : (
          <>
            <ol className="m-0 flex list-none flex-col gap-3 p-0">
              {topic.steps.map((step) => (
                <li key={step.id} className="min-w-0">
                  <StepItem step={step} initiallyOpen={step.id === initialNext} onSave={saveStep} />
                </li>
              ))}
            </ol>
            <DelegateToAgent request={REQUESTS.plan(topic.id)} description="Агент складе або оновить план теми." />
          </>
        )}
      </section>

      <section aria-label="Квіз теми" className="flex flex-col gap-3">
        <div>
          <h2 className="text-section font-semibold">Квіз</h2>
          <p className="text-caption text-muted-foreground">
            На повторення сьогодні <span className="sr-count">{topic.quiz.due}</span> · усього <span className="sr-count">{topic.quiz.total}</span>
          </p>
        </div>
        <div className="grid min-w-0 gap-3 md:grid-cols-2">
          <DelegateToAgent request={REQUESTS.questions(topic.id)} description="Агент складе питання квізу до теми." />
          {topic.quiz.total === 0 ? null : <DelegateToAgent request={REQUESTS.quiz(topic.id)} description="Агент проведе квіз на сьогодні з цієї теми." />}
        </div>
      </section>

      <section className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="font-semibold">{ready ? "Тему позначено готовою" : "Готовність до інтерв’ю"}</h3>
          <p className="text-caption text-muted-foreground">Остаточну готовність визначаєш ти.</p>
        </div>
        <Button type="button" variant={ready ? "secondary" : "default"} disabled={readyBusy} onClick={() => void toggleReady()}>
          {ready ? "Зняти позначку" : "Тема готова"}
        </Button>
      </section>

      <p role="status" aria-label="Результат" className="min-h-6 text-caption font-medium text-primary empty:hidden">
        {message}
      </p>
    </div>
  );
}
