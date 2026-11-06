import { ChevronDown, ChevronUp } from "lucide-react";
import { Fragment, type ReactNode } from "react";

import { importedText, platformLabel, sourceCountText, type Source, type SourcesTab } from "../../domain/sources";
import { madridDay, madridTime } from "../../domain/mail";
import { useMediaQuery } from "../lib/useMediaQuery";
import { cn } from "../lib/cn";
import { detailsId, SourceDetails } from "./SourceDetails";
import { StateBadge } from "./StateBadge";

/** Від цієї ширини (40rem, `sm`) реєстр — таблиця, нижче — картки. */
const TABLE = "(min-width: 40rem)";

interface SourceRegisterProps {
  sources: readonly Source[];
  tab: SourcesTab;
  /** id розгорнутого джерела; порожній рядок — жодне. */
  openId: string;
  /** Джерело, стан якого зараз змінюється. */
  busyId: string;
  onOpen(source: Source): void;
  onToggle(source: Source): void;
  onRemove(source: Source): void;
}

/** Реєстр джерел: таблиця на широкому екрані, список карток на вузькому — той самий зміст, один DOM. */
export function SourceRegister({ sources, tab, openId, busyId, onOpen, onToggle, onRemove }: SourceRegisterProps) {
  const table = useMediaQuery(TABLE, true);
  const details = (source: Source) => (
    <SourceDetails source={source} busy={busyId === source.id} onToggle={() => onToggle(source)} onRemove={() => onRemove(source)} />
  );
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card">
      {table ? (
        <table aria-label="Список джерел" className="w-full table-fixed border-collapse text-nav">
          <thead>
            <tr className="bg-muted text-left text-caption font-medium text-muted-foreground">
              <th scope="col" className="w-[37%] p-3">
                Джерело
              </th>
              <th scope="col" className="w-[20%] p-3">
                Стан
              </th>
              <th scope="col" className="w-[27%] p-3">
                Оновлення · Мадрид
              </th>
              <th scope="col" className="w-[16%] p-3">
                Імпортовано
              </th>
            </tr>
          </thead>
          <tbody>
            {sources.map((source) => (
              <Fragment key={source.id}>
                <tr className="border-b border-border last:border-b-0">
                  <td className="min-w-0 p-3 align-middle">
                    <NameButton source={source} open={openId === source.id} onOpen={() => onOpen(source)} />
                    <span className="block text-caption text-muted-foreground">{platformLabel(source.platform)}</span>
                  </td>
                  <td className="p-3 align-middle">
                    <StateBadge source={source} />
                  </td>
                  <td className="p-3 align-middle">
                    <Updated source={source} />
                  </td>
                  <td className="p-3 align-middle">
                    <Imported source={source} />
                  </td>
                </tr>
                {openId === source.id ? (
                  <tr className="border-b border-border bg-background last:border-b-0">
                    <td colSpan={4}>{details(source)}</td>
                  </tr>
                ) : null}
              </Fragment>
            ))}
          </tbody>
        </table>
      ) : (
        <ul aria-label="Список джерел">
          {sources.map((source) => (
            <li key={source.id} className={cn("min-w-0 border-b border-border last:border-b-0", openId === source.id && "bg-background")}>
              <div className="grid min-w-0 grid-cols-2 gap-x-3 gap-y-2 p-3.5">
                <div className="col-span-2 min-w-0">
                  <NameButton source={source} open={openId === source.id} onOpen={() => onOpen(source)} />
                  <span className="block text-caption text-muted-foreground">{platformLabel(source.platform)}</span>
                </div>
                <div>
                  <StateBadge source={source} />
                </div>
                <div className="text-right">
                  <span className="text-caption text-muted-foreground">Імпортовано · </span>
                  <Imported source={source} />
                </div>
                <div className="col-span-2">
                  <Updated source={source} />
                </div>
              </div>
              {openId === source.id ? details(source) : null}
            </li>
          ))}
        </ul>
      )}
      <p className="border-t border-border p-3 text-caption text-muted-foreground">{`${sourceCountText(tab, sources.length)} · подробиці — за натисканням назви`}</p>
    </div>
  );
}

function NameButton({ source, open, onOpen }: { source: Source; open: boolean; onOpen(): void }) {
  const Chevron = open ? ChevronUp : ChevronDown;
  return (
    <button
      type="button"
      aria-expanded={open}
      aria-controls={open ? detailsId(source) : undefined}
      onClick={onOpen}
      className="inline-flex max-w-full items-center gap-1 text-left font-semibold text-primary [overflow-wrap:anywhere] hover:underline pointer-coarse:min-h-11"
    >
      {source.name}
      <Chevron aria-hidden="true" className="size-4 shrink-0" />
    </button>
  );
}

function Updated({ source }: { source: Source }): ReactNode {
  const run = source.lastRun;
  if (run === null) {
    return <span className="text-caption text-muted-foreground">Ще не було</span>;
  }
  return (
    <span className="flex flex-col text-caption text-muted-foreground">
      <span>{madridDay(run.ranAt)}</span>
      <span>{madridTime(run.ranAt)}</span>
    </span>
  );
}

function Imported({ source }: { source: Source }) {
  return <span className="sr-count text-section">{importedText(source)}</span>;
}
