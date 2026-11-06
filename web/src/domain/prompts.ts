/** Тексти запитів до агента живуть на сервері (`GET /api/prompts`); клієнт підставляє лише номери вакансій і тем. */
import type { DocumentKind } from "./documents";

export const PROMPT_KEYS = [
  "onboarding/setup",
  "requests/analysis",
  "requests/triage",
  "requests/cv",
  "requests/cover_letter",
  "requests/plan",
  "requests/questions",
  "requests/quiz",
  "requests/quiz_topic",
  "requests/topics",
  "requests/job_prep",
  "requests/interview_kit",
  "requests/gaps",
  "requests/facts",
  "requests/add_job",
  "requests/apply",
] as const;
export type PromptKey = (typeof PROMPT_KEYS)[number];

/** Усі шаблони, як їх віддав сервер. */
export type Prompts = Readonly<Record<PromptKey, string>>;

/** Який шаблон і які номери в нього підставити: `{job_id}`, `{topic_id}`. */
export interface PromptRequest {
  key: PromptKey;
  values?: Readonly<Record<string, number>>;
}

/** Підпис, коли текст запиту не вдалося отримати: нічого не копіюється й не відкривається. */
export const PROMPT_UNAVAILABLE = "Не вдалося отримати текст запиту. Спробуй ще раз.";

/** Підставляє `{назва}` числами з `values`; позначка без значення лишається в тексті. */
export function fillPrompt(template: string, values: Readonly<Record<string, number>> = {}): string {
  return template.replace(/\{(\w+)\}/g, (placeholder, name: string) => (Object.hasOwn(values, name) ? String(values[name]) : placeholder));
}

/** Запити, якими кнопки просять текст у сервера: який шаблон і які номери в нього підставити. */
export const REQUESTS = {
  setup: { key: "onboarding/setup" } as PromptRequest,
  analysis: (jobId: number): PromptRequest => ({ key: "requests/analysis", values: { job_id: jobId } }),
  apply: (jobId: number): PromptRequest => ({ key: "requests/apply", values: { job_id: jobId } }),
  triage: { key: "requests/triage" } as PromptRequest,
  document: (kind: DocumentKind, jobId: number): PromptRequest => ({ key: kind === "cv" ? "requests/cv" : "requests/cover_letter", values: { job_id: jobId } }),
  plan: (topicId: number): PromptRequest => ({ key: "requests/plan", values: { topic_id: topicId } }),
  questions: (topicId: number): PromptRequest => ({ key: "requests/questions", values: { topic_id: topicId } }),
  quiz: (topicId?: number): PromptRequest => (topicId === undefined ? { key: "requests/quiz" } : { key: "requests/quiz_topic", values: { topic_id: topicId } }),
  topics: { key: "requests/topics" } as PromptRequest,
  jobPrep: (jobId: number): PromptRequest => ({ key: "requests/job_prep", values: { job_id: jobId } }),
  interviewKit: (jobId: number): PromptRequest => ({ key: "requests/interview_kit", values: { job_id: jobId } }),
  gaps: (jobId: number): PromptRequest => ({ key: "requests/gaps", values: { job_id: jobId } }),
  facts: { key: "requests/facts" } as PromptRequest,
  addJob: { key: "requests/add_job" } as PromptRequest,
};
