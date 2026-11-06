import { useCallback, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router";

import { Button } from "../components/button";
import { Skeleton } from "../components/skeleton";
import { usePageTitle } from "../lib/usePageTitle";
import { usePrepServices } from "./PrepServices";
import { problemText } from "./texts";
import { TopicView } from "./TopicView";
import { useLoaded } from "./useLoaded";

const ALERT = "flex flex-col items-start gap-3 rounded-xl border border-border bg-status-danger p-4 text-status-danger-foreground";
const POSITIVE_INTEGER = /^[1-9]\d*$/;

/** `/prep/{n}`: сторінка теми. Не число в адресі — те саме, що теми нема, без запиту до API. */
export function TopicPage() {
  const { topicId = "" } = useParams();
  return POSITIVE_INTEGER.test(topicId) ? <TopicLoader key={topicId} topicId={Number(topicId)} /> : <TopicMissing />;
}

function TopicLoader({ topicId }: { topicId: number }) {
  const services = usePrepServices();
  const load = useCallback(async () => {
    const outcome = await services.topic(topicId);
    return outcome.ok ? { ok: true as const, value: outcome.topic } : outcome;
  }, [services, topicId]);
  const { state, reload, set } = useLoaded(load);
  // Повідомлення живе тут, а не в TopicView: перезавантаження теми (крок зник) його не губить.
  const [message, setMessage] = useState("");

  if (state.status === "loading") {
    return (
      <Pending>
        <div role="status" aria-label="Завантажуємо тему" className="flex flex-col gap-3">
          <Skeleton className="h-8 w-2/3" />
          <Skeleton className="h-24" />
          <Skeleton className="h-16" />
          <Skeleton className="h-16" />
        </div>
      </Pending>
    );
  }
  if (state.status === "error") {
    if (state.problem === "not-found") {
      return <TopicMissing />;
    }
    return (
      <Pending>
        <div role="alert" className={ALERT}>
          <p className="text-nav font-medium">{problemText(state.problem, "побачити тему", "Не вдалося завантажити тему")}</p>
          {state.problem === "unavailable" ? (
            <>
              <p className="text-caption">Перевір з’єднання й повтори спробу.</p>
              <Button type="button" variant="secondary" onClick={reload}>
                Спробувати ще раз
              </Button>
            </>
          ) : null}
        </div>
      </Pending>
    );
  }
  return <TopicView topic={state.data} message={message} setMessage={setMessage} onChange={set} onGone={reload} />;
}

/** Тема ще вантажиться чи не вантажиться: заголовок вкладки — розділ. */
function Pending({ children }: { children: ReactNode }) {
  usePageTitle("Підготовка");
  return children;
}

function TopicMissing() {
  usePageTitle("Тему не знайдено");
  return (
    <div className="flex flex-col items-center gap-3 rounded-xl border border-border bg-card px-4 py-12 text-center">
      <h1 className="text-page-title font-semibold tracking-tight">Тему не знайдено</h1>
      <p className="text-caption text-muted-foreground">Її могло вже не бути в реєстрі або номер в адресі хибний.</p>
      <Button asChild variant="secondary">
        <Link to="/prep">Усі теми</Link>
      </Button>
    </div>
  );
}
