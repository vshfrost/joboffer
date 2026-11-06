import type { JobAnalysis } from "../domain/analysis";
import type { AddedJob, Job, JobList, JobsQuery, NewJobInput } from "../domain/jobs";

/** API вакансій. Усі помилки — з `domain/jobsErrors`. */
export interface JobsApi {
  /** Кидає JobsUnavailableError. */
  list(query: JobsQuery): Promise<JobList>;
  /** Кидає JobNotFoundError або JobsUnavailableError. */
  get(id: number): Promise<Job>;
  /** Збережений аналіз. Кидає AnalysisNotFoundError (аналізу ще нема) або JobsUnavailableError. */
  getAnalysis(id: number): Promise<JobAnalysis>;
  /** Ховає вакансії з причиною: усе або нічого. Кидає JobsValidationError (422) або JobsUnavailableError. */
  dismiss(ids: readonly number[], reason: string): Promise<void>;
  /** Повертає сховану вакансію в список. Кидає JobNotFoundError або JobsUnavailableError. */
  restore(id: number): Promise<void>;
  /** Додає вакансію (або знаходить наявну). Кидає JobsValidationError (422) або JobsUnavailableError. */
  add(input: NewJobInput): Promise<AddedJob>;
}
