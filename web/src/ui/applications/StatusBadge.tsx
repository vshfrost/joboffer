import { STATUS_LABELS, STATUS_TONES, type ApplicationStatus } from "../../domain/applications";
import { Badge } from "../components/badge";

/** Статус подачі: завжди текстом, колір лише підсилює. */
export function StatusBadge({ status }: { status: ApplicationStatus }) {
  return <Badge tone={STATUS_TONES[status]}>{STATUS_LABELS[status]}</Badge>;
}
