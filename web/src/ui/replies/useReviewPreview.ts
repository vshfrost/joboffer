import { useEffect, useState } from "react";

import type { ReplyType, ReviewEffect } from "../../domain/replies";
import { useRepliesServices } from "./RepliesServices";

/** `none` — вакансії не вибрано, превʼю не потрібне. */
export type PreviewState = { status: "none" } | { status: "loading" } | { status: "error" } | { status: "ready"; effect: ReviewEffect };

/** Ефект розбору на подачу вибраної вакансії; зміна типу чи вакансії скидає превʼю в «рахуємо», а застарілу відповідь відкидає. */
export function useReviewPreview(replyId: number, type: ReplyType, jobId: number | null): PreviewState {
  const services = useRepliesServices();
  const key = `${type}:${jobId}`;
  const [result, setResult] = useState<{ key: string; state: PreviewState } | null>(null);

  useEffect(() => {
    if (jobId === null) {
      return;
    }
    let cancelled = false;
    void services.preview(replyId, type, jobId).then((outcome) => {
      if (!cancelled) {
        setResult({ key, state: outcome.ok ? { status: "ready", effect: outcome.effect } : { status: "error" } });
      }
    });
    return () => {
      cancelled = true;
    };
  }, [services, replyId, type, jobId, key]);

  if (jobId === null) {
    return { status: "none" };
  }
  return result !== null && result.key === key ? result.state : { status: "loading" };
}
