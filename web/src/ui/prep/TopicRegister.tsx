import { Link } from "react-router";

import { deadlineText, jobLabel, KIND_LABELS, progressText, remainingText, type TopicRow } from "../../domain/prep";
import { cn } from "../lib/cn";
import { useMediaQuery } from "../lib/useMediaQuery";
import { ProgressBar } from "./ProgressBar";
import { TopicBadge } from "./TopicBadge";

/** Від цієї ширини (40rem, `sm`) реєстр — таблиця, нижче — картки. */
const TABLE = "(min-width: 40rem)";
const LINK = "inline-flex max-w-full items-center gap-1 text-left text-primary [overflow-wrap:anywhere] pointer-coarse:min-h-11";

/** Реєстр тем за пріоритетом сервера: таблиця на широкому екрані, список карток на вузькому — той самий зміст, один DOM. */
export function TopicRegister({ topics }: { topics: readonly TopicRow[] }) {
  const table = useMediaQuery(TABLE, true);
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card">
      {table ? (
        <table aria-label="Список тем" className="w-full table-fixed border-collapse text-nav">
          <thead>
            <tr className="bg-muted text-left text-caption font-medium text-muted-foreground">
              <th scope="col" className="w-[32%] p-3">
                Тема · за пріоритетом
              </th>
              <th scope="col" className="w-[24%] p-3">
                Прогрес
              </th>
              <th scope="col" className="w-[14%] p-3">
                Дедлайн
              </th>
              <th scope="col" className="w-[30%] p-3">
                Вакансії · скор
              </th>
            </tr>
          </thead>
          <tbody>
            {topics.map((topic) => (
              <tr key={topic.id} className="border-b border-border align-top last:border-b-0">
                <td className="min-w-0 p-3">
                  <TitleLink topic={topic} />
                  <Meta topic={topic} />
                </td>
                <td className="p-3">
                  <Progress topic={topic} />
                </td>
                <td className="p-3 text-caption text-muted-foreground">{deadlineText(topic.deadline)}</td>
                <td className="p-3">
                  <Jobs topic={topic} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <ul aria-label="Список тем">
          {topics.map((topic) => (
            <li key={topic.id} className="flex min-w-0 flex-col gap-3 border-b border-border p-3.5 last:border-b-0">
              <div className="min-w-0">
                <TitleLink topic={topic} />
                <Meta topic={topic} />
              </div>
              <Progress topic={topic} />
              <p className="text-caption text-muted-foreground">Дедлайн · {deadlineText(topic.deadline)}</p>
              <Jobs topic={topic} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function TitleLink({ topic }: { topic: TopicRow }) {
  return (
    <Link to={`/prep/${topic.id}`} className={cn(LINK, "font-semibold hover:underline")}>
      {topic.title}
    </Link>
  );
}

function Meta({ topic }: { topic: TopicRow }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-caption text-muted-foreground">{KIND_LABELS[topic.kind]}</span>
      <TopicBadge status={topic.status} />
    </div>
  );
}

function Progress({ topic }: { topic: TopicRow }) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-baseline gap-2">
        <span className="sr-count">{topic.percent}%</span>
        <span className="text-caption text-muted-foreground">· {progressText(topic)}</span>
      </div>
      <ProgressBar percent={topic.percent} label={topic.title} />
      <p className="text-caption text-muted-foreground">{remainingText(topic)}</p>
    </div>
  );
}

function Jobs({ topic }: { topic: TopicRow }) {
  return (
    <div className="flex flex-col items-start">
      {topic.jobs.map((job) => (
        <Link key={job.jobId} to={`/vacancies/${job.jobId}`} className={cn(LINK, "hover:underline")}>
          {jobLabel(job)} <span className="sr-count">{job.score}</span>
        </Link>
      ))}
    </div>
  );
}
