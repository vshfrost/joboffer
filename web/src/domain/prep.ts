/** Підготовка до співбесід: теми за прогалинами вакансій, їхні кроки, прогрес і пакет до інтерв'ю. Теми й плани складає Claude, веб їх читає й веде прогрес. */

export type TopicKind = "tech" | "behavioral" | "domain";
export type TopicStatus = "new" | "planned" | "learning" | "practicing" | "ready";
export type StepKind = "learn" | "practice" | "check";
export type KitQuestionKind = "technical" | "behavioral";

/** Скільки питань квізу всього і скільки з них на повторенні сьогодні (за Мадридом). */
export interface QuizCount {
  total: number;
  due: number;
}

/** Вакансія теми: скор і прогалина, яку закриває тема. `title` / `company` можуть бути невідомі. */
export interface TopicJob {
  jobId: number;
  title: string | null;
  company: string | null;
  score: number;
  gap: string;
}

/** Тема в реєстрі. */
export interface TopicRow {
  id: number;
  slug: string;
  title: string;
  kind: TopicKind;
  summary: string;
  status: TopicStatus;
  percent: number;
  stepsDone: number;
  stepsTotal: number;
  minutesLeft: number;
  /** День `YYYY-MM-DD` або `null`. */
  deadline: string | null;
  priority: number;
  jobs: TopicJob[];
  quiz: QuizCount;
}

export interface StepResource {
  title: string;
  url: string;
}

export interface Step {
  id: number;
  position: number;
  kind: StepKind;
  title: string;
  minutes: number;
  /** Текст, не HTML. */
  details: string;
  resources: StepResource[];
  /** День виконання за Мадридом (від сервера); `null` — не виконано. */
  doneOn: string | null;
  note: string;
}

/** Сторінка теми: рядок реєстру + кроки. */
export interface Topic extends TopicRow {
  /** Перший невиконаний крок; `null` — кроків нема чи всі виконано. */
  nextStepId: number | null;
  steps: Step[];
}

export interface PrepOverview {
  topics: TopicRow[];
  quiz: QuizCount;
}

/** Підготовка до вакансії: готовність — середнє тем, `null` — тем нема. */
export interface JobPrep {
  readiness: number | null;
  topics: TopicRow[];
}

export interface KitQuestion {
  kind: KitQuestionKind;
  question: string;
  /** Тема з реєстру; `null` — питання не про тему. */
  topicId: number | null;
}

export interface KitStory {
  title: string;
  situation: string;
  task: string;
  action: string;
  result: string;
  factIds: number[];
}

/** Остання версія пакета до інтерв'ю вакансії. */
export interface InterviewKit {
  id: number;
  jobId: number;
  version: number;
  /** День створення за Мадридом (від сервера). */
  createdOn: string;
  questions: KitQuestion[];
  stories: KitStory[];
  companyQuestions: string[];
}

export const TOPIC_KINDS: readonly TopicKind[] = ["tech", "behavioral", "domain"];
export const TOPIC_STATUSES: readonly TopicStatus[] = ["new", "planned", "learning", "practicing", "ready"];
export const STEP_KINDS: readonly StepKind[] = ["learn", "practice", "check"];
export const KIT_QUESTION_KINDS: readonly KitQuestionKind[] = ["technical", "behavioral"];

export const KIND_LABELS: Record<TopicKind, string> = { tech: "Технічна", behavioral: "Поведінкова", domain: "Доменна" };
export const STATUS_LABELS: Record<TopicStatus, string> = { new: "Без плану", planned: "Заплановано", learning: "Вивчаю", practicing: "Практика", ready: "Готово" };
export const STEP_KIND_LABELS: Record<StepKind, string> = { learn: "Вивчення", practice: "Практика", check: "Перевірка" };

/** «Лишилось ~150 хв»; тема без кроків — «Плану ще немає», а не нуль хвилин. */
export function remainingText(topic: Pick<TopicRow, "stepsTotal" | "minutesLeft">): string {
  return topic.stepsTotal === 0 ? "Плану ще немає" : `Лишилось ~${topic.minutesLeft} хв`;
}

/** «2/5»: виконано з усіх кроків. */
export function progressText(topic: Pick<TopicRow, "stepsDone" | "stepsTotal">): string {
  return `${topic.stepsDone}/${topic.stepsTotal}`;
}

/** День дедлайну як є або «—». */
export function deadlineText(deadline: string | null): string {
  return deadline ?? "—";
}

/** Вакансія в списку: компанія, інакше назва, інакше номер. */
export function jobLabel(job: Pick<TopicJob, "jobId" | "title" | "company">): string {
  return job.company ?? job.title ?? `Вакансія #${job.jobId}`;
}

/** Вакансія на сторінці теми: «назва · компанія», що відомо, інакше номер. */
export function jobFullLabel(job: Pick<TopicJob, "jobId" | "title" | "company">): string {
  const known = [job.title, job.company].filter((part) => part !== null);
  return known.length === 0 ? `Вакансія #${job.jobId}` : known.join(" · ");
}

export const KIT_QUESTION_LABELS: Record<KitQuestionKind, string> = { technical: "Технічне", behavioral: "Поведінкове" };

/** Частини STAR-історії: літера, підпис і поле історії. */
export const STORY_PARTS = [
  { letter: "S", label: "Ситуація", field: "situation" },
  { letter: "T", label: "Завдання", field: "task" },
  { letter: "A", label: "Дії", field: "action" },
  { letter: "R", label: "Результат", field: "result" },
] as const satisfies readonly { letter: string; label: string; field: keyof KitStory }[];

/** Готовність до вакансії: «37%» або «—», коли тем нема (а не «0%»). */
export function readinessText(readiness: number | null): string {
  return readiness === null ? "—" : `${readiness}%`;
}

/** Прогалина, яку тема закриває для вакансії; порожня, якщо тема цю вакансію не згадує. */
export function gapOf(topic: Pick<TopicRow, "jobs">, jobId: number): string {
  return topic.jobs.find((job) => job.jobId === jobId)?.gap ?? "";
}
