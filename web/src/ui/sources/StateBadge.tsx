import { sourceState, STATE_LABELS, type Source, type SourceState } from "../../domain/sources";
import { Badge } from "../components/badge";

const TONES: Record<SourceState, "success" | "danger" | "neutral"> = { ok: "success", error: "danger", pending: "neutral", disabled: "neutral" };

/** Стан джерела: текст завжди є, колір його лише підсилює. */
export function StateBadge({ source }: { source: Source }) {
  const state = sourceState(source);
  return <Badge tone={TONES[state]}>{STATE_LABELS[state]}</Badge>;
}
