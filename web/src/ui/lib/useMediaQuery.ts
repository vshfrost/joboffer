import { useCallback, useSyncExternalStore } from "react";

/** Чи збігається медіа-запит. Без `matchMedia` (старі середовища, тести) — `fallback`. */
export function useMediaQuery(query: string, fallback: boolean): boolean {
  const subscribe = useCallback(
    (notify: () => void) => {
      if (typeof window.matchMedia !== "function") {
        return () => {};
      }
      const list = window.matchMedia(query);
      list.addEventListener("change", notify);
      return () => list.removeEventListener("change", notify);
    },
    [query],
  );
  const snapshot = () => (typeof window.matchMedia === "function" ? window.matchMedia(query).matches : fallback);
  return useSyncExternalStore(subscribe, snapshot, () => fallback);
}
