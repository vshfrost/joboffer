import { STATUS_LABELS, type TopicStatus } from "../../domain/prep";
import { Badge } from "../components/badge";

const TONES: Record<TopicStatus, "neutral" | "info" | "success"> = { new: "neutral", planned: "neutral", learning: "neutral", practicing: "info", ready: "success" };

/** Статус теми: текст завжди є, колір його лише підсилює. */
export function TopicBadge({ status }: { status: TopicStatus }) {
  return <Badge tone={TONES[status]}>{STATUS_LABELS[status]}</Badge>;
}
