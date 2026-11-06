import type { InterviewKit, JobPrep, PrepOverview, Topic } from "../domain/prep";

/** API підготовки. Помилки — з `domain/prepErrors`; кожен метод може кинути PrepUnauthorizedError і PrepUnavailableError. */
export interface PrepApi {
  /** Теми за пріоритетом і загальні лічильники квізу. */
  topics(): Promise<PrepOverview>;
  /** Тема з кроками. Кидає PrepNotFoundError, коли теми нема або вона чужа. */
  topic(topicId: number): Promise<Topic>;
  /** Позначає крок виконаним (чи міняє нотатку виконаного); повертає тему. Кидає PrepValidationError (422): текст біля `note`; PrepNotFoundError. */
  completeStep(stepId: number, note: string): Promise<Topic>;
  /** Ставить чи знімає ручну позначку «тема готова»; повертає тему. Кидає PrepNotFoundError. */
  setReady(topicId: number, ready: boolean): Promise<Topic>;
  /** Теми вакансії й готовність до неї. Кидає PrepNotFoundError, коли вакансії нема. */
  jobPrep(jobId: number): Promise<JobPrep>;
  /** Остання версія пакета до інтерв'ю. Кидає PrepNotFoundError, коли пакета (чи вакансії) нема. */
  interviewKit(jobId: number): Promise<InterviewKit>;
}
